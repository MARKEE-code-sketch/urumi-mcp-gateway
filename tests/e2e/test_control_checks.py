"""Controlled safety contracts for the explicit live control runner."""
import asyncio

import pytest

from scripts.m10 import control_checks as controls
from scripts.m10.live_checks import CheckFailed


def owned_meta(name='urumi-m10-inventory-mcp-abc-def'):
    return {'name': name, 'namespace': controls.NS, 'uid': 'original-uid',
            'resourceVersion': '17', 'labels': dict(controls.LABELS)}


def test_control_runner_requires_explicit_mutation_flag():
    with pytest.raises(CheckFailed, match='explicit_mutation_flag_required'):
        asyncio.run(controls.run_control_checks({}))


@pytest.mark.parametrize('override', [{'namespace': 'urumi'}, {'release': 'urumi'},
    {'context': 'other-cluster'}])
def test_target_is_exact_not_a_user_selected_namespace(monkeypatch, override):
    monkeypatch.setattr(controls.Path, 'is_file', lambda path: True)
    with pytest.raises(CheckFailed):
        controls.OwnedInventory({'kubeconfig': '.tools/m10/test-only-placeholder', **override})


def test_pod_delete_uses_atomic_uid_precondition_and_exact_raw_path():
    kube = object.__new__(controls.OwnedInventory)
    calls = []
    async def guard():
        calls.append('ownership_guard')
    async def kubectl(args, input_document=None):
        calls.append((args, input_document))
        return {}
    kube.guard, kube.kubectl = guard, kubectl
    result = asyncio.run(kube.delete_pod({'metadata': owned_meta()}))
    args, body = calls[1]
    assert calls[0] == 'ownership_guard'
    assert args == ['delete', '--raw', '/api/v1/namespaces/urumi-m10/pods/urumi-m10-inventory-mcp-abc-def', '-f', '-']
    assert body['preconditions'] == {'uid': 'original-uid'}
    assert result['atomic_uid_precondition'] is True


def test_unowned_pod_is_never_deleted():
    kube = object.__new__(controls.OwnedInventory)
    async def guard():
        pass
    async def forbidden(*args):
        pytest.fail('No deletion may be attempted.')
    kube.guard, kube.kubectl = guard, forbidden
    metadata = owned_meta()
    metadata['labels']['app.kubernetes.io/component'] = 'wordpress'
    with pytest.raises(CheckFailed, match='inventory_ownership'):
        asyncio.run(kube.delete_pod({'metadata': metadata}))


def test_scale_patch_tests_uid_version_and_original_replicas():
    import json
    kube = object.__new__(controls.OwnedInventory)
    calls = []
    async def deployment():
        return {'metadata': owned_meta(controls.DEPLOY), 'spec': {'replicas': 1}}
    async def kubectl(args):
        calls.append(args)
    kube.deployment, kube.kubectl = deployment, kubectl
    asyncio.run(kube.scale(0))
    patch = json.loads(calls[0][calls[0].index('-p') + 1])
    assert patch[:3] == [
        {'op': 'test', 'path': '/metadata/uid', 'value': 'original-uid'},
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': '17'},
        {'op': 'test', 'path': '/spec/replicas', 'value': 1}]
    assert patch[3] == {'op': 'replace', 'path': '/spec/replicas', 'value': 0}


@pytest.mark.parametrize('release_name,release_namespace,accepted', [
    ('urumi-m10', 'urumi-m10', True), ('urumi', 'urumi-m10', False),
    ('urumi-m10', 'urumi', False)])
def test_deployment_guard_uses_helm_annotations_and_template_labels(release_name, release_namespace, accepted):
    kube = object.__new__(controls.OwnedInventory)
    deployment = {'metadata': {'name': controls.DEPLOY, 'namespace': controls.NS,
        'labels': {'app.kubernetes.io/managed-by': 'Helm'}, 'annotations': {
            'meta.helm.sh/release-name': release_name,
            'meta.helm.sh/release-namespace': release_namespace}},
        'spec': {'template': {'metadata': {'labels': dict(controls.LABELS)}}}}
    async def guard():
        pass
    async def kubectl(args):
        assert args == ['-n', controls.NS, 'get', 'deployment', controls.DEPLOY, '-o', 'json']
        return deployment
    kube.guard, kube.kubectl = guard, kubectl
    if accepted:
        assert asyncio.run(kube.deployment()) is deployment
    else:
        with pytest.raises(CheckFailed, match='inventory_deployment_ownership'):
            asyncio.run(kube.deployment())


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_mid_check_failure_revokes_only_owned_keys_and_never_returns_pass(monkeypatch, cleanup_fails):
    issued, revoked, closed = [], [], []
    class FakeBrowser:
        def __init__(self, *args):
            self.user = None
        async def login(self, email, password):
            self.user = {'id': email.split('@')[0], 'role': email.split('@')[0]}
        async def request(self, method, path, data=None, expected=200):
            if method == 'POST' and path.endswith('/keys'):
                key = {'id': self.user['id'] + '-owned-key', 'raw_key': 'private-key-' + self.user['id']}
                issued.append(key['id'])
                return key
            if method == 'DELETE':
                revoked.append(path.rsplit('/', 1)[-1])
                if cleanup_fails:
                    raise RuntimeError('private-error-must-not-be-recorded')
                return None
            raise CheckFailed('injected_before_cluster_mutation')
        async def close(self):
            closed.append(self.user['id'])
    monkeypatch.setattr(controls, 'Browser', FakeBrowser)
    monkeypatch.setattr(controls, 'tls_context', lambda path: object())
    monkeypatch.setattr(controls, 'OwnedInventory', lambda config: object())
    config = {'origin': 'https://dashboard.test', 'ca_path': 'unused',
        'admin_email': 'admin@example.test', 'member_email': 'member@example.test',
        'admin_password': 'private-admin', 'member_password': 'private-member'}
    evidence = asyncio.run(controls.run_control_checks(config, run_owned_demo=True))
    assert evidence['status'] == 'FAIL'
    assert set(issued) == set(revoked) == {'admin-owned-key', 'member-owned-key'}
    assert set(closed) == {'admin', 'member'}
    assert 'private-' not in str(evidence)
    assert evidence['failure_check'] == 'injected_before_cluster_mutation'
    assert set(evidence['cleanup'].values()) == ({'CLEANUP_FAILED'} if cleanup_fails else {'REVOKED'})


@pytest.mark.parametrize('mode,status', [('normal', 401), ('async', 401), ('async', 503)])
def test_revoked_sdk_task_group_exit_does_not_skip_independent_http_check(monkeypatch, mode, status):
    from contextlib import asynccontextmanager
    import httpx
    from types import SimpleNamespace
    calls = []
    class FakeBrowser:
        def __init__(self, *args):
            self.user = None
            self.client = self
        async def login(self, email, password):
            self.user = {'id': email.split('@')[0], 'role': email.split('@')[0]}
        async def request(self, method, path, data=None, expected=200):
            if method == 'POST' and path.endswith('/keys'):
                return {'id': self.user['id'] + '-key', 'raw_key': self.user['id'] + '-private'}
            if method == 'DELETE':
                return None
            if path.startswith('/api/v1/servers?'):
                return {'items': [{'id': 'inventory-id', 'slug': 'inventory', 'enabled': True, 'url': 'http://inventory/mcp'}]}
            return {'enabled': True}
        async def post(self, path, **kwargs):
            calls.append('independent_raw_check')
            assert kwargs['headers']['Accept'] == 'application/json, text/event-stream'
            return httpx.Response(401, json={'error': {'code': 'KEY_REVOKED'}})
        async def close(self):
            pass
    class Selected:
        count = 0
        async def call_tool(self, *args):
            self.count += 1
            if self.count > 1:
                if mode == 'async':
                    raise asyncio.CancelledError()
                raise httpx.HTTPStatusError('private-response-detail',
                    request=httpx.Request('POST', 'https://dashboard.test/mcp'), response=httpx.Response(401))
            return SimpleNamespace(isError=False)
    @asynccontextmanager
    async def fake_gateway(origin, context, key):
        if key.startswith('admin'):
            raise CheckFailed('stop_before_control_calls')
        try:
            yield Selected()
        finally:
            if mode == 'async':
                raise ExceptionGroup('private-sdk-detail', [httpx.HTTPStatusError('private-response-detail',
                    request=httpx.Request('POST', 'https://dashboard.test/mcp'), response=httpx.Response(status))])
            raise ExceptionGroup('private-sdk-detail', [RuntimeError('private-transport-detail')])
    async def no_wait(*args):
        return []
    monkeypatch.setattr(controls, 'Browser', FakeBrowser)
    monkeypatch.setattr(controls, 'gateway', fake_gateway)
    monkeypatch.setattr(controls, 'wait_tools', no_wait)
    monkeypatch.setattr(controls, 'result_data', lambda value: {})
    monkeypatch.setattr(controls, 'tls_context', lambda path: object())
    monkeypatch.setattr(controls, 'OwnedInventory', lambda config: object())
    evidence = asyncio.run(controls.run_control_checks({'origin': 'https://dashboard.test', 'ca_path': 'unused',
        'admin_email': 'admin@example.test', 'member_email': 'member@example.test',
        'admin_password': 'private-admin', 'member_password': 'private-member',
        'inventory_url': 'http://inventory/mcp'}, run_owned_demo=True))
    if status == 401:
        assert calls == ['independent_raw_check']
        assert evidence['failure_stage'] == 'independent_control_key'
        assert evidence['failure_check'] == 'stop_before_control_calls'
        assert evidence['revoked_session_transport_exit']['exception_types'] == [
            'ExceptionGroup', 'RuntimeError' if mode == 'normal' else 'HTTPStatusError']
    else:
        assert calls == []
        assert evidence['failure_stage'] == 'open_session_next_call'
        assert 'revoked_session_transport_exit' not in evidence
    assert evidence['status'] == 'FAIL'
    assert 'private-' not in str(evidence)
