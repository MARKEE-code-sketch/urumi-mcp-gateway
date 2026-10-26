"""Fresh-store setup target and private-output boundaries, without Kubernetes."""
import json
from types import SimpleNamespace

import pytest

from scripts.m10 import store_bootstrap as setup


def test_setup_reuses_existing_bootstrap_with_fresh_named_mounts():
    job = setup.build_job('urumi/wordpress:m2', 'urumi-m10-setup-12345678')
    pod = job['spec']['template']['spec']
    container = pod['containers'][0]
    assert job['metadata']['namespace'] == 'urumi-m10'
    assert pod['automountServiceAccountToken'] is False
    assert container['command'][2].count('wp eval-file /opt/urumi-store/bootstrap.php') == 2
    assert pod['volumes'][0]['persistentVolumeClaim']['claimName'] == 'urumi-m10-wordpress-content'
    assert {v['secret']['secretName'] for v in pod['volumes'] if 'secret' in v} == {
        'urumi-m10-store-db', 'urumi-m10-store-admin', 'urumi-m10-store-salts',
        'urumi-m10-woocommerce-rest'}
    assert job['spec']['backoffLimit'] == 0


def test_clean_install_target_is_separate_and_other_names_are_rejected():
    job = setup.build_job('urumi/wordpress@sha256:' + 'a' * 64,
                          'urumi-m10-clean-setup-12345678', 'urumi-m10-clean')
    assert job['metadata']['namespace'] == 'urumi-m10-clean'
    pod = job['spec']['template']['spec']
    assert pod['volumes'][0]['persistentVolumeClaim']['claimName'] == 'urumi-m10-clean-wordpress-content'
    assert all(v['secret']['secretName'].startswith('urumi-m10-clean-')
               for v in pod['volumes'] if 'secret' in v)
    with pytest.raises(ValueError):
        setup.build_job('image', 'urumi-setup-12345678', 'urumi')


@pytest.mark.parametrize('target', ['urumi-m10', 'urumi-m10-clean'])
def test_fresh_setup_mounts_release_theme_read_only_and_activates_after_bootstrap(target):
    job = setup.build_job('urumi/wordpress:m2', target + '-setup-12345678', target)
    pod = job['spec']['template']['spec']
    container = pod['containers'][0]
    assert {'name': 'store-theme', 'configMap': {'name': target + '-store-theme'}} in pod['volumes']
    assert {'name': 'store-theme', 'mountPath': '/var/www/html/wp-content/themes/urumi-shop',
            'readOnly': True} in container['volumeMounts']
    commands = container['command'][2]
    assert commands.endswith('wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress; '
                             'wp theme activate urumi-shop')
    assert commands.count('wp theme activate urumi-shop') == 1


def test_module_setup_has_same_theme_mount_and_activation_contract():
    script = (setup.ROOT / 'scripts/store-setup.ps1').read_text(encoding='utf-8')
    assert "configMap=@{name='urumi-store-theme'}" in script
    assert "mountPath='/var/www/html/wp-content/themes/urumi-shop';readOnly=$true" in script
    assert script.count('wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress') == 2
    assert 'wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress; wp theme activate urumi-shop' in script


@pytest.mark.parametrize('logs', [
    '{"consumer-secret":"DO_NOT_EXPORT"}',
    '{"product_id":true,"attachment_id":1,"key_id":2,"currency":"INR","timezone":"Asia/Kolkata"}',
    '{"product_id":1,"attachment_id":1,"key_id":2,"currency":"USD","timezone":"Asia/Kolkata"}',
])
def test_arbitrary_logs_are_not_returned(logs):
    with pytest.raises(RuntimeError, match='no valid safe result'):
        setup.safe_result(logs)


def test_safe_result_extracts_only_fixed_public_fields():
    expected = {'product_id': 1, 'attachment_id': 2, 'key_id': 3,
                'currency': 'INR', 'timezone': 'Asia/Kolkata'}
    assert setup.safe_result('private diagnostic never returned\n' + json.dumps(expected)) == expected


def test_namespace_ownership_rejected_before_any_mutation(monkeypatch):
    kubeconfig = setup.ROOT / '.tools/m1/kubeconfig.yaml'
    monkeypatch.setattr(setup.Path, 'is_file', lambda self: True)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'metadata': {'labels': {}}}))

    monkeypatch.setattr(setup.subprocess, 'run', run)
    with pytest.raises(ValueError, match='namespace must carry'):
        setup.bootstrap('k3d-urumi', kubeconfig)
    assert len(calls) == 1
    assert 'get' in calls[0] and 'create' not in calls[0]


def test_wrong_cluster_rejected_before_subprocess(monkeypatch):
    kubeconfig = setup.ROOT / '.tools/m1/kubeconfig.yaml'
    monkeypatch.setattr(setup.subprocess, 'run', lambda *a, **kw: pytest.fail('Unexpected command'))
    with pytest.raises(ValueError, match='explicit k3d-urumi'):
        setup.bootstrap('other-cluster', kubeconfig)


def test_success_reads_only_secret_key_names_and_deletes_only_own_job(monkeypatch):
    calls = []
    public_result = {'product_id': 1, 'attachment_id': 2, 'key_id': 3,
                     'currency': 'INR', 'timezone': 'Asia/Kolkata'}
    monkeypatch.setattr(setup.Path, 'is_file', lambda self: True)

    def run(command, **kwargs):
        calls.append((command, kwargs.get('input')))
        if 'namespace' in command:
            body = json.dumps({'metadata': {'labels': {'urumi.dev/module': 'm10'}}})
        elif 'deployment' in command:
            body = json.dumps({'spec': {'template': {
                'metadata': {'labels': {'app.kubernetes.io/instance': 'urumi-m10',
                                        'app.kubernetes.io/component': 'wordpress'}},
                'spec': {'containers': [{'name': 'wordpress', 'image': 'urumi/wordpress:m2'}]}}}})
        elif 'secret' in command:
            assert any(part.startswith('go-template=') for part in command)
            body = '\n'.join([*setup.SALTS, 'database-password', 'username', 'email',
                              'password', 'consumer-key', 'consumer-secret'])
        elif 'logs' in command:
            body = json.dumps(public_result)
        else:
            body = ''
        return SimpleNamespace(returncode=0, stdout=body)

    monkeypatch.setattr(setup.subprocess, 'run', run)
    result = setup.bootstrap('k3d-urumi', setup.ROOT / '.tools/m1/kubeconfig.yaml')
    created = next(json.loads(payload) for command, payload in calls if 'create' in command)
    deleted = [command for command, _ in calls if 'delete' in command]
    assert len(deleted) == 1
    assert deleted[0][-2] == created['metadata']['name'] == result['setup_job']
    assert all('urumi-m10' in command or 'namespace' in command for command, _ in calls)
    assert result['status'] == 'STORE_BOOTSTRAP_COMPLETE'
    assert all(result[key] == value for key, value in public_result.items())
