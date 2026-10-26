"""Prepare only the owned disposable M6 namespace and random fixture credentials."""
import json
from pathlib import Path
import secrets
import subprocess


ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = 'urumi-m6-check'


def kubectl(*args, document=None, check=True):
    result = subprocess.run(['kubectl', '--kubeconfig', str(ROOT / '.tools/m1/kubeconfig.yaml'),
        '--context', 'k3d-urumi', *args], input=json.dumps(document) if document else None,
        capture_output=True, text=True, timeout=30)
    if check and result.returncode:
        raise RuntimeError('Isolated Kubernetes operation failed.')
    return result


def prepare():
    existing = kubectl('get', 'namespace', NAMESPACE, '-o', 'json', check=False)
    if existing.returncode == 0:
        labels = json.loads(existing.stdout)['metadata'].get('labels', {})
        if labels.get('urumi.dev/module') != 'm6-check':
            raise RuntimeError('Refusing an unowned namespace.')
    else:
        kubectl('create', '-f', '-', document={'apiVersion': 'v1', 'kind': 'Namespace',
            'metadata': {'name': NAMESPACE, 'labels': {'urumi.dev/module': 'm6-check'}}})
    path = ROOT / '.tools/m6/access.json'
    if path.exists():
        tokens = json.loads(path.read_text())
    else:
        tokens = {name: secrets.token_urlsafe(32) for name in
                  ('key-a', 'key-b', 'session-a', 'session-b', 'bearer-token', 'header-token')}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tokens), encoding='utf-8')
    kubectl('apply', '-f', '-', document={'apiVersion': 'v1', 'kind': 'Secret',
        'metadata': {'name': 'urumi-m6-check-access', 'namespace': NAMESPACE,
                     'labels': {'urumi.dev/module': 'm6-check'}}, 'type': 'Opaque', 'stringData': tokens})
    print('Owned M6 namespace and random fixture credentials prepared; values omitted.')


if __name__ == '__main__':
    prepare()
