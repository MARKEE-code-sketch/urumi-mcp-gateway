"""Recovery cryptography, target isolation and data checks without live operations."""
import io
import json
import tarfile

import pytest
from cryptography.exceptions import InvalidTag

from scripts.m10 import recovery


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as target:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            info.mode, info.uid, info.gid = 0o640, 33, 33
            info.type = kind
            if kind == tarfile.REGTYPE:
                info.size = len(data)
                target.addfile(info, io.BytesIO(data))
            else:
                info.linkname = '/sensitive'
                target.addfile(info)
    return stream.getvalue()


def test_authenticated_encryption_roundtrip_and_tamper_rejection():
    files = {name: ('private-' + name).encode() for name in recovery.MEMBERS}
    cipher, wrapped = recovery.encrypt_files(files, wrap=lambda key: b'test-wrap:' + key)
    assert all(value not in cipher for value in files.values())
    assert recovery.decrypt_files(cipher, wrapped, unwrap=lambda value: value[10:]) == files
    tampered = cipher[:-1] + bytes([cipher[-1] ^ 1])
    with pytest.raises(InvalidTag):
        recovery.decrypt_files(tampered, wrapped, unwrap=lambda value: value[10:])


def test_archive_members_are_fixed():
    with pytest.raises(ValueError, match='exactly'):
        recovery.encrypt_files({'unexpected': b'not allowed'}, wrap=lambda key: key)


@pytest.mark.parametrize('name,kind', [('../escape', tarfile.REGTYPE),
    ('/absolute', tarfile.REGTYPE), ('link', tarfile.SYMTYPE), ('hardlink', tarfile.LNKTYPE),
    ('fifo', tarfile.FIFOTYPE), ('device', tarfile.CHRTYPE)])
def test_content_archive_rejects_unsafe_paths_and_links(name, kind):
    data = archive([('./wp-config.php', b'private', tarfile.REGTYPE), (name, b'bad', kind)])
    with pytest.raises(ValueError, match='unsafe'):
        recovery.content_fingerprint(data)


def test_content_archive_rejects_duplicate_paths():
    data = archive([('./wp-config.php', b'first', tarfile.REGTYPE),
                    ('wp-config.php', b'replacement', tarfile.REGTYPE)])
    with pytest.raises(ValueError, match='duplicate'):
        recovery.content_fingerprint(data)


def test_content_fingerprint_preserves_mode_ownership_and_data_digest():
    data = archive([('./wp-config.php', b'private', tarfile.REGTYPE)])
    result = recovery.content_fingerprint(data)
    assert result == {'./wp-config.php': {'mode': 0o640, 'uid': 33, 'gid': 33,
                                         'sha256': recovery.digest(b'private')}}
    assert 'private' not in json.dumps(result)


class MaintenanceCluster:
    def __init__(self, *, owned=True, replicas=0, pods=None):
        self.owned, self.replicas, self.pods = owned, replicas, pods or []
        self.calls = []

    def read(self, namespace, arguments):
        self.calls.append((namespace, arguments))
        if arguments[0] == 'namespace':
            return {'metadata': {'labels': {'urumi.dev/module': 'm10' if self.owned else 'other'}}}
        if arguments[0] == 'deployment':
            return {'spec': {'replicas': self.replicas}}
        return {'items': self.pods}


@pytest.mark.parametrize('settings', [{'owned': False}, {'replicas': 1},
    {'pods': [{'metadata': {'deletionTimestamp': 'terminating'}}]}])
def test_capture_refuses_unowned_or_active_source(settings):
    cluster = MaintenanceCluster(**settings)
    with pytest.raises(ValueError):
        recovery.assert_maintenance(cluster)
    assert all(namespace in [None, 'urumi-m10'] for namespace, _ in cluster.calls)


def test_maintenance_checks_all_three_writer_components():
    cluster = MaintenanceCluster()
    recovery.assert_maintenance(cluster)
    names = [arguments[1] for _, arguments in cluster.calls if arguments[0] == 'deployment']
    assert names == ['urumi-m10-' + component for component in recovery.PAUSED]


def test_rehearsal_pods_have_disposable_storage_and_no_network_service():
    namespace = 'urumi-m10-recovery-test'
    pods = [recovery.database_pod(namespace, 'postgres', 'pg:reviewed', postgres=True),
            recovery.database_pod(namespace, 'mariadb', 'maria:reviewed'),
            recovery.content_pod(namespace, 'content', 'wp:reviewed')]
    for pod in pods:
        assert pod['kind'] == 'Pod'
        assert pod['metadata']['namespace'] == namespace
        assert pod['spec']['automountServiceAccountToken'] is False
        assert not any('persistentVolumeClaim' in v for v in pod['spec']['volumes'])
        assert any('emptyDir' in v for v in pod['spec']['volumes'])
        assert pod['spec']['containers'][0]['imagePullPolicy'] == 'IfNotPresent'
    source = recovery.content_pod('urumi-m10', 'unique-reader', 'wp:reviewed', source=True)
    assert source['spec']['volumes'][0]['persistentVolumeClaim']['readOnly'] is True
    assert source['spec']['containers'][0]['volumeMounts'][0]['readOnly'] is True


def test_restore_secret_strips_original_identity_and_preserves_matching_values():
    original = {'metadata': {'name': 'credential-name', 'namespace': 'urumi-m10-secrets',
                'uid': 'source-id', 'resourceVersion': '123', 'ownerReferences': [{'uid': 'source-owner'}],
                'labels': {'installation': 'matching-installation'}},
                'data': {'credential': 'cHJpdmF0ZQ=='}, 'immutable': True}
    result = recovery.restore_secret(original, 'urumi-m10-recovery-test-secrets')
    assert result['data'] == original['data']
    assert result['immutable'] is True
    assert result['metadata']['namespace'] == 'urumi-m10-recovery-test-secrets'
    assert 'uid' not in result['metadata'] and 'ownerReferences' not in result['metadata']
    assert result['metadata']['labels']['installation'] == 'matching-installation'


def test_database_password_is_read_from_mounted_file_without_argument_value():
    command = recovery.mariadb_script('mariadb-dump {options} woocommerce')
    assert '/run/urumi/database/root-password' in command[2]
    assert '--defaults-extra-file="$f"' in command[2]
    assert '--password=' not in command[2]
    assert 'trap' in command[2] and 'umask 077' in command[2]


@pytest.mark.parametrize('invalid', [None, 'owner', 'server', 'pending'])
def test_credential_references_require_matching_installation_and_server(invalid):
    class Cluster:
        def execute(self, *args):
            return json.dumps({'installation': 'installation-id',
                'pending': 1 if invalid == 'pending' else 0,
                'references': [{'id': 'server-id', 'name': 'secret-name'}]}).encode()

    secret = {'metadata': {'name': 'secret-name', 'labels': {'urumi-module': 'm5',
        'urumi-owner': 'wrong' if invalid == 'owner' else 'installation-id',
        'urumi-server': 'wrong' if invalid == 'server' else 'server-id'}},
        'immutable': True, 'data': {'value': 'cHJpdmF0ZQ=='}}
    if invalid:
        with pytest.raises(ValueError):
            recovery.credential_consistency(Cluster(), 'isolated', 'postgres', [secret])
    else:
        assert recovery.credential_consistency(Cluster(), 'isolated', 'postgres', [secret]) == 1


def test_cleanup_delete_uses_atomic_uid_preconditions():
    cluster = object.__new__(recovery.Cluster)
    calls = []
    cluster.call = lambda namespace, args, data=None, **kwargs: calls.append((namespace, args, data))
    cluster.delete_owned('namespace', 'urumi-m10-recovery-0123abcd', 'created-uid')
    namespace, args, data = calls[0]
    assert namespace is None and args[:2] == ['delete', '--raw']
    assert args[2] == '/api/v1/namespaces/urumi-m10-recovery-0123abcd'
    assert json.loads(data)['preconditions'] == {'uid': 'created-uid'}
    assert calls[1][1][:2] == ['wait', '--for=delete']
    calls.clear()
    with pytest.raises(ValueError):
        cluster.delete_owned('namespace', 'urumi', 'retained-uid')
    assert calls == []


def test_restore_extracts_into_uid_owned_child_and_verifies_that_same_tree(monkeypatch):
    content = archive([('./wp-config.php', b'private', tarfile.REGTYPE)])
    state = {'source': recovery.SOURCE, 'dynamic_namespace': recovery.DYNAMIC,
        'static_secrets': [], 'dynamic_secrets': [], 'images': {
            'postgres': 'pg:reviewed', 'mariadb': 'maria:reviewed', 'wordpress': 'wp:reviewed'},
        'content_fingerprint': recovery.content_fingerprint(content),
        'postgres_fingerprint': {'users': {'rows': 1}},
        'mariadb_data_sha256': recovery.digest(b'matching-data'), 'credential_reference_count': 0}
    files = {'state.json': json.dumps(state).encode(), 'postgres.dump': b'pg',
             'mariadb.sql': b'maria', 'wordpress.tar': content}
    monkeypatch.setattr(recovery.Path, 'read_bytes', lambda self: b'encrypted-placeholder')
    monkeypatch.setattr(recovery, 'decrypt_files', lambda *args: files)
    monkeypatch.setattr(recovery, 'pg_fingerprint', lambda *args: state['postgres_fingerprint'])
    monkeypatch.setattr(recovery, 'credential_consistency', lambda *args: 0)

    class Cluster:
        stage = None
        def __init__(self):
            self.made_owned_child = False
            self.verified_owned_child = False
            self.run = None
            self.deleted = []
        def create(self, namespace, resource):
            if resource['kind'] == 'Namespace':
                self.run = resource['metadata']['labels']['urumi.dev/recovery-run']
            return {'metadata': {'uid': 'created-uid'}}
        def call(self, *args, **kwargs):
            return b''
        def read(self, namespace, arguments):
            if arguments[0] == 'namespace':
                return {'metadata': {'labels': {'urumi.dev/recovery-run': self.run}}}
            return {'items': []}
        def execute(self, namespace, pod, command, data=None, **kwargs):
            if command[0] == 'mkdir':
                assert command == ['mkdir', '-m', '0755', '/content/site']
                self.made_owned_child = True
            elif command[0] == 'tar':
                assert self.made_owned_child and command[2] == '/content/site'
                if '-cf' in command:
                    self.verified_owned_child = True
                    return content
            elif pod == 'mariadb' and data is None:
                return b'matching-data'
            return b''
        def delete_owned(self, kind, target, uid):
            assert kind == 'namespace' and uid == 'created-uid'
            self.deleted.append(target)

    cluster = Cluster()
    result = recovery.restore(cluster, recovery.PRIVATE / 'test-snapshot')
    assert result['status'] == 'PASS_ISOLATED_RESTORE'
    assert cluster.made_owned_child and cluster.verified_owned_child
    assert len(cluster.deleted) == 2
