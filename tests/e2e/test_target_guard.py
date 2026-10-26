import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.m10.target import inventory, summarize, validate_target


@pytest.mark.parametrize('namespace,release', [
    ('urumi', 'urumi'), ('default', 'urumi-m10'), ('kube-system', 'urumi-m10'),
    ('urumi-m10', 'other'), ('urumi-m10-', 'urumi-m10'), ('urumi-m10/../urumi', 'urumi-m10')])
def test_rejects_ambiguous_or_retained_targets(tmp_path, namespace, release):
    config = tmp_path / 'config'; config.touch()
    with pytest.raises(ValueError):
        validate_target('explicit', config, namespace, release)


def test_requires_explicit_context_and_kubeconfig(tmp_path):
    with pytest.raises(ValueError):
        validate_target('explicit', tmp_path / 'missing', 'urumi-m10', 'urumi-m10')
    config = tmp_path / 'config'; config.touch()
    with pytest.raises(ValueError):
        validate_target('', config, 'urumi-m10', 'urumi-m10')


def test_refuses_unowned_namespace_before_resource_query(tmp_path, monkeypatch):
    config = tmp_path / 'config'; config.touch(); calls = []
    def read(command, **options):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout=json.dumps({'metadata': {'labels': {}}}))
    monkeypatch.setattr('scripts.m10.target.subprocess.run', read)
    with pytest.raises(ValueError, match='ownership'):
        inventory('explicit', config, 'urumi-m10', 'urumi-m10')
    assert len(calls) == 1 and 'namespace' in calls[0]


def test_inventory_outputs_allowlisted_metadata_only(tmp_path, monkeypatch):
    config = tmp_path / 'config'; config.touch(); calls = []
    pod = {'kind': 'Pod', 'metadata': {'name': 'backend', 'uid': 'pod-id',
           'labels': {'app.kubernetes.io/instance': 'urumi-m10'}, 'annotations': {'private': 'hidden'}},
           'spec': {'containers': [{'env': [{'value': 'private-value'}]}]},
           'status': {'phase': 'Running', 'containerStatuses': [{'name': 'backend', 'ready': True,
                      'restartCount': 0, 'image': 'image', 'imageID': 'sha256:observed'}]}}
    def read(command, **options):
        calls.append(command)
        body = {'metadata': {'uid': 'ns-id', 'labels': {'urumi.dev/module': 'm10'}}} if len(calls) == 1 else {'items': [pod]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(body))
    monkeypatch.setattr('scripts.m10.target.subprocess.run', read)
    result = inventory('explicit', config, 'urumi-m10', 'urumi-m10')
    text = json.dumps(result)
    assert 'private-value' not in text and 'hidden' not in text
    assert result['resources'][0]['containers'][0]['imageID'] == 'sha256:observed'
    assert all('get' in command for command in calls)
    assert not any(word in command for command in calls for word in ['secrets', 'configmaps', 'apply', 'delete'])


def test_unrelated_release_not_included():
    assert summarize({'items': [{'kind': 'Pod', 'metadata': {'labels': {'app.kubernetes.io/instance': 'urumi'}}}]}, 'urumi-m10') == []


def test_controlled_runner_strips_live_database_opt_in(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[2] / 'scripts/m10/check-m10.py'
    spec = importlib.util.spec_from_file_location('m10_controlled_checker', path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    monkeypatch.setattr(checker, 'ROOT', tmp_path)
    monkeypatch.setenv('URUMI_M10_TEST_DSN', 'must-not-reach-controlled-subprocess')
    monkeypatch.setenv('M10_TEST_KEEP_ENV', 'preserved')
    monkeypatch.setattr('sys.argv', ['check-m10.py', '--mode', 'controlled', '--output',
                                   str(tmp_path / '.tools/m10/control')])
    calls = []
    def run(command, **options):
        calls.append(options)
        return SimpleNamespace(returncode=0, stdout='controlled stub', stderr='')
    monkeypatch.setattr(checker.subprocess, 'run', run)
    assert checker.main() == 0
    assert len(calls) == 1
    assert 'URUMI_M10_TEST_DSN' not in calls[0]['env']
    assert calls[0]['env']['M10_TEST_KEEP_ENV'] == 'preserved'
