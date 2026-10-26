"""Encrypted fresh-M10 backup and isolated restore rehearsal.

Root must first pause backend, WordPress and Woo MCP and verify the maintenance
window. No source scaling, password rotation, production cutover or retained-shop
operation is performed here. Dumps and Secret values exist only in memory and
encrypted private files. Windows DPAPI binds the key to this Windows user/machine;
this rehearsal is not an off-machine disaster-recovery backup.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import uuid
import zipfile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / '.tools/operator/m10/recovery'
SOURCE = 'urumi-m10'
DYNAMIC = SOURCE + '-secrets'
PAUSED = ('backend', 'wordpress', 'woocommerce-mcp')
AAD = b'urumi-m10-recovery-v1'
MEMBERS = {'postgres.dump', 'mariadb.sql', 'wordpress.tar', 'state.json'}


class RecoveryFailure(RuntimeError):
    def __init__(self, code, exit_code=None, signals=()):
        super().__init__(code)
        self.code, self.exit_code = code, exit_code
        self.signals = list(signals)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def protect_key(data, *, decrypt=False):
    """DPAPI current-user scope, with UI forbidden and LocalMachine flag absent."""
    if os.name != 'nt':
        raise RuntimeError('This private recovery helper requires Windows DPAPI.')

    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.restype = wintypes.BOOL
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise RuntimeError('DPAPI key operation failed; no private diagnostics exported.')
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def encrypt_files(files, wrap=protect_key):
    if set(files) != MEMBERS:
        raise ValueError('Recovery archive requires exactly the reviewed four members.')
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as target:
        for name, data in files.items():
            target.writestr(name, data)
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    return nonce + AESGCM(key).encrypt(nonce, archive.getvalue(), AAD), wrap(key)


def decrypt_files(ciphertext, wrapped_key, unwrap=None):
    unwrap = unwrap or (lambda value: protect_key(value, decrypt=True))
    plain = AESGCM(unwrap(wrapped_key)).decrypt(ciphertext[:12], ciphertext[12:], AAD)
    with zipfile.ZipFile(io.BytesIO(plain)) as archive:
        if set(archive.namelist()) != MEMBERS or len(archive.namelist()) != len(MEMBERS):
            raise ValueError('Unexpected or duplicate recovery archive member.')
        return {name: archive.read(name) for name in MEMBERS}


def private_directory(directory):
    directory = directory.resolve()
    if not directory.is_relative_to(PRIVATE.resolve()) or directory == PRIVATE.resolve() or directory.exists():
        raise ValueError('Use a new snapshot directory below the private M10 recovery root.')
    directory.mkdir(parents=True, mode=0o700)
    process = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                              '[Security.Principal.WindowsIdentity]::GetCurrent().User.Value'],
                             capture_output=True, text=True, timeout=15)
    sid = process.stdout.strip()
    if process.returncode or not re.fullmatch(r'S-1-[0-9-]+', sid):
        raise RuntimeError('Could not determine the current Windows identity for private backup ACL.')
    process = subprocess.run(['icacls.exe', str(directory), '/inheritance:r', '/grant:r',
                              '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'],
                             capture_output=True, timeout=15)
    if process.returncode:
        raise RuntimeError('Could not restrict backup directory access; no snapshot written.')


class Cluster:
    def __init__(self, context, kubeconfig):
        if context != 'k3d-urumi' or not Path(kubeconfig).is_file():
            raise ValueError('Explicit k3d-urumi context and existing kubeconfig required.')
        self.base = ['kubectl', '--context', context, '--kubeconfig', str(kubeconfig)]
        self.stage = 'VALIDATE_TARGET'
        self.failure_stage = None
        self.failure_diagnostics = []

    def call(self, namespace, arguments, data=None, timeout=90):
        command = self.base + (['-n', namespace] if namespace else []) + arguments
        process = subprocess.run(command, input=data, capture_output=True, timeout=timeout)
        if process.returncode:
            known = {'OPERATION_NOT_PERMITTED': b'Operation not permitted',
                     'PERMISSION_DENIED': b'Permission denied', 'UNRECOGNIZED_OPTION': b'unrecognized option',
                     'NO_SPACE': b'No space left on device', 'CANNOT_OPEN': b'Cannot open',
                     'CANNOT_MKDIR': b'Cannot mkdir', 'CANNOT_UTIME': b'Cannot utime',
                     'CANNOT_CHMOD': b'Cannot change mode', 'READ_ONLY_FILESYSTEM': b'Read-only file system'}
            raise RecoveryFailure('KUBERNETES_COMMAND_FAILED', process.returncode,
                                  [name for name, token in known.items() if token in process.stderr])
        return process.stdout

    def read(self, namespace, arguments):
        return json.loads(self.call(namespace, ['get', *arguments, '-o', 'json']))

    def create(self, namespace, resource):
        return json.loads(self.call(namespace, ['create', '-f', '-', '-o', 'json'], json.dumps(resource).encode()))

    def delete_owned(self, kind, name, uid, namespace=None):
        if kind == 'pod':
            if namespace != SOURCE or not re.fullmatch(r'm10-backup-content-[0-9a-f]{8}', name):
                raise ValueError('Only our exact fresh-source content reader can be removed.')
            uri = '/api/v1/namespaces/' + namespace + '/pods/' + name
        elif kind == 'namespace':
            if namespace is not None or not re.fullmatch(r'urumi-m10-recovery-[0-9a-f]{8}(?:-secrets)?', name):
                raise ValueError('Only an isolated rehearsal namespace can be removed.')
            uri = '/api/v1/namespaces/' + name
        else:
            raise ValueError('Unsupported recovery cleanup resource.')
        if not uid:
            raise ValueError('Cleanup requires the UID returned when this object was created.')
        # The API applies this precondition atomically; a name reused by another
        # object after our metadata read cannot be deleted by this cleanup.
        options = {'apiVersion': 'v1', 'kind': 'DeleteOptions',
                   'preconditions': {'uid': uid}, 'propagationPolicy': 'Foreground'}
        self.call(None, ['delete', '--raw', uri, '-f', '-'], json.dumps(options).encode())
        self.call(namespace, ['wait', '--for=delete', kind + '/' + name, '--timeout=120s'], timeout=140)

    def execute(self, namespace, pod, command, data=None, timeout=90):
        return self.call(namespace, ['exec', '-i', pod, '--', *command], data, timeout)


def assert_maintenance(cluster):
    ns = cluster.read(None, ['namespace', SOURCE])
    if ns['metadata'].get('labels', {}).get('urumi.dev/module') != 'm10':
        raise ValueError('Source namespace lacks exact M10 ownership label.')
    for component in PAUSED:
        workload = cluster.read(SOURCE, ['deployment', SOURCE + '-' + component])
        if workload['spec'].get('replicas', 1) != 0:
            raise ValueError('Maintenance requires backend, WordPress and Woo MCP scaled to zero by root.')
        pods = cluster.read(SOURCE, ['pods', '-l',
            'app.kubernetes.io/instance=' + SOURCE + ',app.kubernetes.io/component=' + component])
        if pods['items']:
            raise ValueError('Maintenance requires all writer Pods gone, including terminating Pods.')


def source_pod(cluster, component):
    pods = cluster.read(SOURCE, ['pods', '-l',
        'app.kubernetes.io/instance=' + SOURCE + ',app.kubernetes.io/component=' + component])['items']
    if len(pods) != 1 or pods[0].get('status', {}).get('phase') != 'Running':
        raise ValueError('Expected one running source database Pod.')
    return pods[0]


def mariadb_script(command):
    # No password in command arguments, process logs, host files, or shell history.
    return ['sh', '-ec', 'umask 077; f=$(mktemp); trap \'rm -f "$f"\' EXIT; '
        '{ printf "[client]\\nuser=root\\npassword="; cat /run/urumi/database/root-password; '
        'printf "\\n"; } >"$f"; ' + command.replace('{options}', '--defaults-extra-file="$f"')]


def pg_fingerprint(cluster, namespace, pod):
    tables = cluster.execute(namespace, pod, ['psql', '-U', 'urumi', '-d', 'urumi', '-At', '-c',
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"]).decode().splitlines()
    result = {}
    for table in tables:
        if not re.fullmatch(r'[a-z_]+', table):
            raise ValueError('Unexpected table name in controlled platform schema.')
        contents = cluster.execute(namespace, pod, ['psql', '-U', 'urumi', '-d', 'urumi', '-c',
            f'COPY (SELECT row_to_json(t)::text FROM "{table}" t ORDER BY row_to_json(t)::text) TO STDOUT'])
        result[table] = {'rows': len(contents.splitlines()), 'sha256': digest(contents)}
    if not {'installation', 'users', 'api_keys', 'servers', 'audit_records'} <= set(result):
        raise ValueError('Platform schema incomplete for recovery rehearsal.')
    return result


def credential_consistency(cluster, namespace, pod, dynamic_secrets):
    query = "SELECT json_build_object('installation',(SELECT id FROM installation)," \
        "'pending',(SELECT count(*) FROM secret_operations),'references'," \
        "(SELECT coalesce(json_agg(json_build_object('id',id,'name',secret_name)), '[]'::json) " \
        "FROM servers WHERE secret_name IS NOT NULL))"
    state = json.loads(cluster.execute(namespace, pod,
        ['psql', '-U', 'urumi', '-d', 'urumi', '-At', '-c', query]))
    if not state['installation'] or state['pending'] != 0:
        raise ValueError('Recovery requires installed identity and completed credential operations.')
    indexed = {secret['metadata']['name']: secret for secret in dynamic_secrets}
    for reference in state['references']:
        secret = indexed.get(reference['name'])
        if not secret or secret['metadata'].get('labels', {}).get('urumi-owner') != state['installation']:
            raise ValueError('Registry credential reference or installation ownership is inconsistent.')
        if (secret['metadata']['labels'].get('urumi-server') != reference['id'] or
                secret['metadata']['labels'].get('urumi-module') != 'm5' or
                not secret.get('immutable') or 'value' not in secret.get('data', {})):
            raise ValueError('Registry credential reference does not match its owned immutable Secret.')
    return len(state['references'])


MARIA_DATA = 'mariadb-dump {options} --skip-comments --skip-dump-date --order-by-primary --skip-add-locks --skip-extended-insert --no-create-info --skip-disable-keys woocommerce'


def content_fingerprint(archive):
    files = {}
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as tar:
        for item in tar:
            normalized = str(Path(item.name))
            if (item.name.startswith('/') or '..' in Path(item.name).parts or
                    not (item.isfile() or item.isdir()) or normalized in seen):
                raise ValueError('Unexpected unsafe content archive path, special entry or duplicate.')
            seen.add(normalized)
            if item.isfile():
                files[item.name] = {'sha256': digest(tar.extractfile(item).read()),
                                    'mode': item.mode, 'uid': item.uid, 'gid': item.gid}
    if not any(name.endswith('/wp-config.php') or name == 'wp-config.php' for name in files):
        raise ValueError('Content snapshot lacks installed WordPress configuration.')
    return files


def content_pod(namespace, name, image, *, source=False):
    volume = {'name': 'content', 'persistentVolumeClaim': {
        'claimName': SOURCE + '-wordpress-content', 'readOnly': True}} if source else {
        'name': 'content', 'emptyDir': {}}
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace,
        'labels': {'urumi.dev/recovery': 'm10'}}, 'spec': {
        'automountServiceAccountToken': False, 'restartPolicy': 'Never',
        'securityContext': {'runAsUser': 33, 'runAsGroup': 33, **({} if source else {'fsGroup': 33})},
        'containers': [{'name': 'content', 'image': image, 'imagePullPolicy': 'IfNotPresent',
            'command': ['sleep', '3600'], 'securityContext': {'allowPrivilegeEscalation': False,
                'capabilities': {'drop': ['ALL']}, 'seccompProfile': {'type': 'RuntimeDefault'}},
            'readinessProbe': {'exec': {'command': ['test', '-d', '/content']}, 'periodSeconds': 3},
            'livenessProbe': {'exec': {'command': ['test', '-d', '/content']}, 'periodSeconds': 10},
            'resources': {'requests': {'cpu': '25m', 'memory': '32Mi'},
                          'limits': {'cpu': '250m', 'memory': '256Mi'}},
            'volumeMounts': [{'name': 'content', 'mountPath': '/content', 'readOnly': source}]}],
        'volumes': [volume]}}


def capture(cluster, directory):
    assert_maintenance(cluster)
    private_directory(directory)
    postgres, maria = source_pod(cluster, 'platform-db'), source_pod(cluster, 'mariadb')
    wp = cluster.read(SOURCE, ['deployment', SOURCE + '-wordpress'])
    image = wp['spec']['template']['spec']['containers'][0]['image']
    reader = 'm10-backup-content-' + uuid.uuid4().hex[:8]
    created_reader = cluster.create(SOURCE, content_pod(SOURCE, reader, image, source=True))
    try:
        cluster.call(SOURCE, ['wait', '--for=condition=Ready', 'pod/' + reader, '--timeout=90s'], timeout=100)
        pg_name, maria_name = postgres['metadata']['name'], maria['metadata']['name']
        engines = cluster.execute(SOURCE, maria_name, mariadb_script(
            'mariadb {options} -N -e "SELECT COUNT(*) FROM information_schema.tables '
            "WHERE table_schema='woocommerce' AND table_type='BASE TABLE' AND engine <> 'InnoDB'\""))
        if engines.strip() != b'0':
            raise ValueError('Transactional dump requires all WooCommerce tables to be InnoDB.')
        pg_dump = cluster.execute(SOURCE, pg_name, ['pg_dump', '-U', 'urumi', '-d', 'urumi', '-Fc'], timeout=180)
        maria_dump = cluster.execute(SOURCE, maria_name, mariadb_script(
            'mariadb-dump {options} --single-transaction --skip-lock-tables --hex-blob woocommerce'), timeout=180)
        content = cluster.execute(SOURCE, reader, ['tar', '-C', '/content', '-cf', '-', '.'], timeout=180)
        # Matching credential-reference state must be inside the same encrypted archive.
        static = cluster.read(SOURCE, ['secrets'])['items']
        dynamic = cluster.read(DYNAMIC, ['secrets'])['items']
        static = [s for s in static if s['metadata']['name'].startswith(SOURCE + '-')]
        if not static:
            raise ValueError('No matching static Secret state captured.')
        state = {'source': SOURCE, 'dynamic_namespace': DYNAMIC,
                 'captured_at': datetime.now(timezone.utc).isoformat(),
                 'static_secrets': static, 'dynamic_secrets': dynamic,
                 'configmaps': cluster.read(SOURCE, ['configmaps'])['items'],
                 'workloads': cluster.read(SOURCE, ['deployments,statefulsets'])['items'],
                 'operator_values': (PRIVATE.parent / 'merged-values.yaml').read_text(encoding='utf-8'),
                 'chart_metadata': (ROOT / 'deploy/charts/urumi/Chart.yaml').read_text(encoding='utf-8'),
                 'images': {'postgres': postgres['spec']['containers'][0]['image'],
                            'mariadb': maria['spec']['containers'][0]['image'], 'wordpress': image},
                 'postgres_fingerprint': pg_fingerprint(cluster, SOURCE, pg_name),
                 'credential_reference_count': credential_consistency(cluster, SOURCE, pg_name, dynamic),
                 'mariadb_data_sha256': digest(cluster.execute(SOURCE, maria_name, mariadb_script(MARIA_DATA))),
                 'content_fingerprint': content_fingerprint(content)}
        # Recheck after reads so a resumed writer cannot produce a valid snapshot.
        assert_maintenance(cluster)
        files = {'postgres.dump': pg_dump, 'mariadb.sql': maria_dump, 'wordpress.tar': content,
                 'state.json': json.dumps(state).encode()}
        encrypted, wrapped = encrypt_files(files)
        for filename, data in [('snapshot.aesgcm', encrypted), ('key.dpapi', wrapped)]:
            with (directory / filename).open('xb') as stream:
                stream.write(data)
        return {'status': 'ENCRYPTED_SNAPSHOT_CAPTURED', 'source': SOURCE,
                'ciphertext_sha256': digest(encrypted), 'postgres_tables': len(state['postgres_fingerprint']),
                'content_files': len(state['content_fingerprint']), 'static_secret_count': len(static),
                'dynamic_secret_count': len(dynamic), 'off_machine_backup': False,
                'key_scope': 'Windows DPAPI current user and machine'}
    finally:
        cluster.delete_owned('pod', reader, created_reader['metadata']['uid'], SOURCE)


def restore_secret(secret, namespace):
    return {'apiVersion': 'v1', 'kind': 'Secret', 'type': secret.get('type', 'Opaque'),
            'metadata': {'name': secret['metadata']['name'], 'namespace': namespace,
                         'labels': {**secret['metadata'].get('labels', {}), 'urumi.dev/recovery': 'm10'},
                         'annotations': secret['metadata'].get('annotations', {})},
            'data': secret.get('data', {}), **({'immutable': True} if secret.get('immutable') else {})}


def database_pod(namespace, name, image, *, postgres=False):
    if postgres:
        env = [{'name': 'POSTGRES_DB', 'value': 'urumi'}, {'name': 'POSTGRES_USER', 'value': 'urumi'},
               {'name': 'POSTGRES_PASSWORD', 'valueFrom': {'secretKeyRef': {
                   'name': SOURCE + '-platform-db', 'key': 'password'}}}]
        mounts = [{'name': 'data', 'mountPath': '/var/lib/postgresql/data'}]
        volumes = [{'name': 'data', 'emptyDir': {}}]
        probe = ['pg_isready', '-U', 'urumi', '-d', 'urumi']
    else:
        env = [{'name': 'MARIADB_DATABASE', 'value': 'woocommerce'},
               {'name': 'MARIADB_ROOT_PASSWORD_FILE', 'value': '/run/urumi/database/root-password'}]
        mounts = [{'name': 'data', 'mountPath': '/var/lib/mysql'},
                  {'name': 'database', 'mountPath': '/run/urumi/database', 'readOnly': True}]
        volumes = [{'name': 'data', 'emptyDir': {}}, {'name': 'database', 'secret': {
            'secretName': SOURCE + '-store-db'}}]
        probe = ['healthcheck.sh', '--connect', '--innodb_initialized']
    return {'apiVersion': 'v1', 'kind': 'Pod', 'metadata': {'name': name, 'namespace': namespace,
        'labels': {'urumi.dev/recovery': 'm10'}}, 'spec': {
        'restartPolicy': 'Never', 'automountServiceAccountToken': False,
        'containers': [{'name': name, 'image': image, 'imagePullPolicy': 'IfNotPresent',
            'env': env, 'volumeMounts': mounts,
            'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                          'limits': {'cpu': '500m', 'memory': '512Mi'}},
            'startupProbe': {'exec': {'command': probe}, 'periodSeconds': 2, 'failureThreshold': 90},
            'readinessProbe': {'exec': {'command': probe}, 'periodSeconds': 3},
            'livenessProbe': {'exec': {'command': probe}, 'periodSeconds': 10}}], 'volumes': volumes}}


def restore(cluster, directory):
    cluster.stage = 'DECRYPT_SNAPSHOT'
    directory = directory.resolve()
    if not directory.is_relative_to(PRIVATE.resolve()):
        raise ValueError('Only the private M10 recovery root may supply snapshots.')
    files = decrypt_files((directory / 'snapshot.aesgcm').read_bytes(), (directory / 'key.dpapi').read_bytes())
    state = json.loads(files['state.json'])
    if state['source'] != SOURCE or state['dynamic_namespace'] != DYNAMIC:
        raise ValueError('Snapshot is not from the fresh owned M10 installation.')
    namespace = SOURCE + '-recovery-' + uuid.uuid4().hex[:8]
    dynamic_namespace = namespace + '-secrets'
    created = []
    try:
        cluster.stage = 'CREATE_ISOLATED_NAMESPACES'
        for target in [namespace, dynamic_namespace]:
            created_namespace = cluster.create(None, {'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {
                'name': target, 'labels': {'urumi.dev/module': 'm10-recovery',
                                          'urumi.dev/recovery-run': namespace}}})
            created.append((target, created_namespace['metadata']['uid']))
            cluster.create(target, {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy',
                'metadata': {'name': 'deny-all', 'namespace': target}, 'spec': {
                    'podSelector': {}, 'policyTypes': ['Ingress', 'Egress'], 'ingress': [], 'egress': []}})
        for secret in state['static_secrets']:
            cluster.create(namespace, restore_secret(secret, namespace))
        for secret in state['dynamic_secrets']:
            cluster.create(dynamic_namespace, restore_secret(secret, dynamic_namespace))
        cluster.stage = 'CREATE_RESTORE_PODS'
        cluster.create(namespace, database_pod(namespace, 'postgres', state['images']['postgres'], postgres=True))
        cluster.create(namespace, database_pod(namespace, 'mariadb', state['images']['mariadb']))
        cluster.create(namespace, content_pod(namespace, 'content', state['images']['wordpress']))
        for name in ['postgres', 'mariadb', 'content']:
            cluster.stage = 'WAIT_RESTORE_' + name.upper()
            cluster.call(namespace, ['wait', '--for=condition=Ready', 'pod/' + name,
                                     '--timeout=180s'], timeout=200)
        cluster.stage = 'RESTORE_POSTGRES'
        cluster.execute(namespace, 'postgres', ['pg_restore', '-U', 'urumi', '-d', 'urumi',
                                                '--exit-on-error', '--no-owner'], files['postgres.dump'], timeout=180)
        cluster.stage = 'RESTORE_MARIADB'
        cluster.execute(namespace, 'mariadb', mariadb_script('mariadb {options} woocommerce'),
                        files['mariadb.sql'], timeout=180)
        # Archive paths were checked before capture and are checked again before extraction.
        cluster.stage = 'RESTORE_CONTENT'
        if content_fingerprint(files['wordpress.tar']) != state['content_fingerprint']:
            raise ValueError('Content manifest differs from encrypted snapshot.')
        # Kubernetes owns the emptyDir mount root. Extract into a directory made
        # by UID33 so tar can restore the archived root's mode without privilege.
        cluster.execute(namespace, 'content', ['mkdir', '-m', '0755', '/content/site'])
        cluster.execute(namespace, 'content', ['tar', '-C', '/content/site', '--no-same-owner',
                                              '--no-overwrite-dir', '-xf', '-'],
                        files['wordpress.tar'], timeout=180)
        cluster.stage = 'VERIFY_DATABASE_AND_CONTENT'
        restored_pg = pg_fingerprint(cluster, namespace, 'postgres')
        restored_maria = digest(cluster.execute(namespace, 'mariadb', mariadb_script(MARIA_DATA)))
        restored_content = content_fingerprint(cluster.execute(namespace, 'content',
            ['tar', '-C', '/content/site', '-cf', '-', '.'], timeout=180))
        if (restored_pg != state['postgres_fingerprint'] or
                restored_maria != state['mariadb_data_sha256'] or
                restored_content != state['content_fingerprint']):
            raise RuntimeError('Isolated restore data or file verification mismatch.')
        # Compare full Secret data/ownership, retaining no values in the public result.
        cluster.stage = 'VERIFY_SECRET_STATE'
        for target, source_key in [(namespace, 'static_secrets'), (dynamic_namespace, 'dynamic_secrets')]:
            actual = cluster.read(target, ['secrets'])['items']
            expected = {s['metadata']['name']: s.get('data', {}) for s in state[source_key]}
            observed = {s['metadata']['name']: s.get('data', {}) for s in actual}
            if expected != observed:
                raise RuntimeError('Restored Secret state differs from snapshot.')
        restored_references = credential_consistency(cluster, namespace, 'postgres',
                                                     cluster.read(dynamic_namespace, ['secrets'])['items'])
        if restored_references != state['credential_reference_count']:
            raise RuntimeError('Restored registry credential references differ from snapshot.')
        return {'status': 'PASS_ISOLATED_RESTORE', 'source': SOURCE, 'restore_namespace': namespace,
                'postgres_tables_match': len(restored_pg), 'postgres_row_counts': {
                    table: value['rows'] for table, value in restored_pg.items()},
                'mariadb_data_match': True, 'wordpress_files_match': len(restored_content),
                'secret_state_match': True, 'credential_references_verified': restored_references,
                'public_services_created': False,
                'backend_or_provider_started': False, 'storage': 'disposable emptyDir only',
                'cleanup': 'Both uniquely owned rehearsal namespaces removed in finally',
                'limitation': 'Data/credential/file restore, not a running restored application or VPS proof.'}
    except Exception:
        cluster.failure_stage = cluster.stage
        # Fixed enums and numeric status only; never logs/messages/env/Secret data.
        try:
            pods = cluster.read(namespace, ['pods'])['items']
            allowed = {'Pending', 'Running', 'Failed', 'Succeeded', 'Unknown',
                       'ContainerCreating', 'CrashLoopBackOff', 'ImagePullBackOff',
                       'ErrImagePull', 'Error', 'Completed', 'OOMKilled'}
            for pod in pods:
                row = {'pod': pod['metadata']['name'], 'phase': pod.get('status', {}).get('phase')}
                row['containers'] = []
                for item in pod.get('status', {}).get('containerStatuses', []):
                    detail = {'ready': item.get('ready'), 'restarts': item.get('restartCount')}
                    for status in ['waiting', 'terminated']:
                        current = item.get('state', {}).get(status, {})
                        if current.get('reason') in allowed:
                            detail['reason'] = current['reason']
                        if 'exitCode' in current:
                            detail['exit_code'] = current['exitCode']
                    row['containers'].append(detail)
                cluster.failure_diagnostics.append(row)
        except Exception:
            pass
        raise
    finally:
        cluster.stage = 'CLEANUP_ISOLATED_NAMESPACES'
        for target, uid in reversed(created):
            observed = cluster.read(None, ['namespace', target])
            if observed['metadata'].get('labels', {}).get('urumi.dev/recovery-run') != namespace:
                raise RuntimeError('Cleanup ownership check failed; no namespace deleted.')
            cluster.delete_owned('namespace', target, uid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['capture', 'restore'])
    parser.add_argument('--context', required=True)
    parser.add_argument('--kubeconfig', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'docs/evidence/m10'):
        parser.error('Only sanitized evidence output under docs/evidence/m10 is allowed.')
    cluster = None
    try:
        cluster = Cluster(args.context, args.kubeconfig)
        result = capture(cluster, args.directory.resolve()) if args.mode == 'capture' else restore(cluster, args.directory)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    except Exception as error:
        result = {'status': 'FAIL_RECOVERY_OPERATION', 'mode': args.mode,
                  'stage': getattr(cluster, 'failure_stage', None) or getattr(cluster, 'stage', 'SETUP'),
                  'exception_type': type(error).__name__,
                  'error_code': error.code if isinstance(error, RecoveryFailure) else 'RECOVERY_CHECK_FAILED',
                  'exit_code': error.exit_code if isinstance(error, RecoveryFailure) else None,
                  'known_error_signals': error.signals if isinstance(error, RecoveryFailure) else [],
                  'safe_pod_status': getattr(cluster, 'failure_diagnostics', []),
                  'private_diagnostics_exported': False}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        parser.exit(1, 'M10 recovery operation failed; private values and diagnostics were not exported.\n')
    print(result['status'])


if __name__ == '__main__':
    main()
