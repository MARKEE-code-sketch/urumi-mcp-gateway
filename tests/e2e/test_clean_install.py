"""Clean rehearsal cleanup guards, with no Kubernetes or Helm operations."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.m10 import clean_install


def cleanup_fixture(monkeypatch):
    namespace = clean_install.NS
    names = [namespace + '-' + suffix for suffix in
             ['mariadb-data', 'wordpress-content', 'platform-data']]
    ownership = {'namespace': namespace, 'uid': 'app-namespace-uid',
                 'secret_namespace_uid': 'secret-namespace-uid'}
    claims = [{'name': name, 'uid': 'claim-' + str(index)} for index, name in enumerate(names)]
    resources = {
        namespace: {'metadata': {'uid': ownership['uid'],
            'labels': {'urumi.dev/task': 'clean-rehearsal'}}},
        namespace + '-secrets': {'metadata': {'uid': ownership['secret_namespace_uid'],
            'labels': {'urumi-owner': namespace}}},
    }
    for claim in claims:
        # The real platform PVC deliberately has no instance/component labels.
        # Ownership is established by its exact name, UID and Helm annotations.
        resources[claim['name']] = {'metadata': {'uid': claim['uid'], 'annotations': {
            'meta.helm.sh/release-name': namespace, 'meta.helm.sh/release-namespace': namespace}}}
    calls = []

    def private_read(path, *args, **kwargs):
        if path.name == 'ownership.json':
            return json.dumps(ownership)
        if path.name == 'owned-pvcs.json':
            return json.dumps(claims)
        pytest.fail('Unexpected private-file read')

    def run(arguments, data=None, timeout=60):
        command = [str(item) for item in arguments]
        calls.append((command, copy.deepcopy(data)))
        if '--ignore-not-found' in command:
            return ''
        if 'get' in command:
            index = command.index('get')
            return json.dumps(resources[command[index + 2]])
        return ''

    monkeypatch.setattr(Path, 'read_text', private_read)
    monkeypatch.setattr(clean_install, 'run', run)
    args = SimpleNamespace(private_dir=Path('unused-private-directory'), kubectl='kubectl',
                           kubeconfig=Path('explicit-kubeconfig'), context='k3d-urumi', helm='helm')
    return args, ownership, claims, resources, calls


@pytest.mark.parametrize('mismatch', [
    'namespace_uid', 'namespace_task', 'ownership_namespace',
    'dynamic_uid', 'dynamic_owner', 'pvc_uid', 'pvc_release_name',
    'pvc_release_namespace', 'recorded_pvc_names',
])
def test_cleanup_mismatch_prevents_every_uninstall_and_delete(monkeypatch, mismatch):
    args, ownership, claims, resources, calls = cleanup_fixture(monkeypatch)
    namespace = clean_install.NS
    if mismatch == 'namespace_uid':
        resources[namespace]['metadata']['uid'] = 'different-object'
    elif mismatch == 'namespace_task':
        resources[namespace]['metadata']['labels']['urumi.dev/task'] = 'other-task'
    elif mismatch == 'ownership_namespace':
        ownership['namespace'] = 'urumi'
    elif mismatch == 'dynamic_uid':
        resources[namespace + '-secrets']['metadata']['uid'] = 'different-object'
    elif mismatch == 'dynamic_owner':
        resources[namespace + '-secrets']['metadata']['labels']['urumi-owner'] = 'urumi'
    elif mismatch == 'pvc_uid':
        resources[claims[-1]['name']]['metadata']['uid'] = 'different-disk'
    elif mismatch == 'pvc_release_name':
        resources[claims[-1]['name']]['metadata']['annotations']['meta.helm.sh/release-name'] = 'urumi'
    elif mismatch == 'pvc_release_namespace':
        resources[claims[-1]['name']]['metadata']['annotations']['meta.helm.sh/release-namespace'] = 'urumi'
    else:
        claims[-1]['name'] = 'urumi-platform-data'
    with pytest.raises(RuntimeError):
        clean_install.cleanup(args, {})
    assert not any(command[0] == 'helm' or 'delete' in command for command, _ in calls)


def test_cleanup_accepts_all_three_exact_pvcs_without_labels_and_uses_atomic_uids(monkeypatch):
    args, ownership, claims, resources, calls = cleanup_fixture(monkeypatch)
    assert all('labels' not in resources[claim['name']]['metadata'] for claim in claims)
    evidence = {}
    clean_install.cleanup(args, evidence)
    mutations = [(command, data) for command, data in calls
                 if command[0] == 'helm' or 'delete' in command]
    assert len(mutations) == 6
    uninstall, _ = mutations[0]
    assert uninstall[:3] == ['helm', 'uninstall', clean_install.NS]
    assert uninstall[uninstall.index('--namespace') + 1] == clean_install.NS
    expected = {
        '/api/v1/namespaces/' + clean_install.NS + '/persistentvolumeclaims/' + claim['name']: claim['uid']
        for claim in claims}
    expected.update({
        '/api/v1/namespaces/' + clean_install.NS + '-secrets': ownership['secret_namespace_uid'],
        '/api/v1/namespaces/' + clean_install.NS: ownership['uid']})
    actual = {}
    for command, data in mutations[1:]:
        assert command[0] == 'kubectl' and '--raw' in command and command[-2:] == ['-f', '-']
        assert data['apiVersion'] == 'v1' and data['kind'] == 'DeleteOptions'
        actual[command[command.index('--raw') + 1]] = data['preconditions']['uid']
    assert actual == expected
    assert evidence['status'] == 'PASS' and evidence['removed_owned_pvcs'] == 3
    assert 'all_three_pvc_owners_and_uids' in evidence['checks']
