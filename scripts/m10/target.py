"""Read-only, narrowly scoped runtime inventory without environment or Secret values."""
import json
from pathlib import Path
import re
import subprocess


def validate_target(context, kubeconfig, namespace, release):
    if not context or context.startswith('-'):
        raise ValueError('An explicit Kubernetes context is required.')
    if not Path(kubeconfig).is_file():
        raise ValueError('An explicit existing kubeconfig file is required.')
    pattern = r'urumi-m10(?:-[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)?'
    if not all(re.fullmatch(pattern, value) and len(value) <= 53 for value in [namespace, release]):
        raise ValueError('Inventory is restricted to explicitly named urumi-m10 targets.')


def summarize(resources, release):
    result = []
    for item in resources['items']:
        metadata = item['metadata']
        if metadata.get('labels', {}).get('app.kubernetes.io/instance') != release:
            continue
        row = {'kind': item['kind'], 'name': metadata['name'], 'uid': metadata['uid']}
        status = item.get('status', {})
        if item['kind'] == 'Pod':
            row['phase'] = status.get('phase')
            row['containers'] = [{key: c.get(key) for key in ['name', 'ready', 'restartCount', 'image', 'imageID']}
                                 for c in status.get('containerStatuses', [])]
            row['ready'] = any(c.get('type') == 'Ready' and c.get('status') == 'True'
                               for c in status.get('conditions', []))
        elif item['kind'] == 'PersistentVolumeClaim':
            row.update(phase=status.get('phase'), volume=item.get('spec', {}).get('volumeName'))
        elif item['kind'] == 'Service':
            row.update(type=item['spec'].get('type'), ports=[
                {key: p.get(key) for key in ['name', 'port', 'targetPort']} for p in item['spec'].get('ports', [])])
        else:
            row.update(replicas=item.get('spec', {}).get('replicas'), readyReplicas=status.get('readyReplicas', 0))
        result.append(row)
    return sorted(result, key=lambda row: (row['kind'], row['name']))


def inventory(context, kubeconfig, namespace, release):
    validate_target(context, kubeconfig, namespace, release)
    kube = ['kubectl', '--context', context, '--kubeconfig', str(kubeconfig)]

    def read(arguments):
        completed = subprocess.run(kube + arguments, capture_output=True, text=True, timeout=30)
        if completed.returncode:
            raise RuntimeError('Scoped Kubernetes read failed; inspect private operator diagnostics.')
        return json.loads(completed.stdout)

    ns = read(['get', 'namespace', namespace, '-o', 'json'])
    if ns['metadata'].get('labels', {}).get('urumi.dev/module') != 'm10':
        raise ValueError('Target namespace lacks the reviewed urumi.dev/module=m10 ownership label.')
    resources = read(['-n', namespace, 'get', 'pods,pvc,services,deployments,statefulsets',
                      '-l', 'app.kubernetes.io/instance=' + release, '-o', 'json'])
    return {'scope': 'read-only selected runtime metadata; no Secrets, ConfigMaps, env, args or logs',
            'context': context, 'namespace': namespace, 'release': release,
            'namespace_uid': ns['metadata']['uid'], 'resources': summarize(resources, release),
            'acceptance_status': 'OBSERVATION_ONLY; does not establish C10 acceptance'}
