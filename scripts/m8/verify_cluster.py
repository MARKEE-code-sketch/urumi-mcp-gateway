"""Inspect an existing M8 runtime without changing it."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
NAMESPACE = 'urumi-m8-check'


def verify_runtime(resources, identities):
    items = resources['items']
    pods = [item for item in items if item['kind'] == 'Pod']
    deployments = [item for item in items if item['kind'] == 'Deployment']
    assert len(pods) == len(deployments) == 2, 'Expected dashboard and fixture only.'
    for deployment in deployments:
        assert deployment['status'].get('availableReplicas') == 1
    proof = []
    for pod in pods:
        spec, status = pod['spec'], pod['status']
        assert spec['automountServiceAccountToken'] is False
        assert spec['securityContext']['runAsNonRoot'] is True
        assert spec['securityContext']['seccompProfile']['type'] == 'RuntimeDefault'
        assert len(spec['containers']) == len(status['containerStatuses']) == 1
        assert not any('secret' in volume or 'persistentVolumeClaim' in volume for volume in spec.get('volumes', []))
        container, observed = spec['containers'][0], status['containerStatuses'][0]
        assert observed['ready'] and observed['restartCount'] == 0
        security = container['securityContext']
        assert security['readOnlyRootFilesystem'] and security['allowPrivilegeEscalation'] is False
        assert security['capabilities']['drop'] == ['ALL']
        assert container['readinessProbe']['httpGet']['path'] == '/readyz'
        assert container['livenessProbe']['httpGet']['path'] == '/livez'
        for part in ['requests', 'limits']:
            assert {'cpu', 'memory'} <= container['resources'][part].keys()
        assert not any('secretKeyRef' in env.get('valueFrom', {}) for env in container.get('env', []))
        image = container['image']
        expected = identities[image]['config_digest']
        assert observed['imageID'].endswith(expected), (image, observed['imageID'], expected)
        proof.append({'pod': pod['metadata']['name'], 'uid': pod['metadata']['uid'],
                      'image': image, 'image_id': observed['imageID'], 'verified_config_digest': expected,
                      'ready': True, 'restart_count': 0, 'resources': container['resources'],
                      'security_context': security, 'probes': {key: container[key] for key in ['readinessProbe', 'livenessProbe']}})
    return proof


def inspect(context='k3d-urumi', kubeconfig=None):
    prefix = ['kubectl', '--context', context]
    if kubeconfig:
        prefix += ['--kubeconfig', str(kubeconfig)]
    namespace = json.loads(subprocess.check_output(prefix + ['get', 'namespace', NAMESPACE, '-o', 'json'], text=True))
    if namespace['metadata'].get('labels', {}).get('urumi.dev/module') != 'm8-check':
        raise RuntimeError('Wrong namespace ownership.')
    return json.loads(subprocess.check_output(prefix + ['-n', NAMESPACE, 'get', 'pods,deployments,services', '-o', 'json'], text=True))


if __name__ == '__main__':
    print(json.dumps(inspect(kubeconfig=ROOT / '.tools/m1/kubeconfig.yaml'), indent=2))
