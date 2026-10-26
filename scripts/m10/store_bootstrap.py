"""Configure only the explicitly owned fresh M10 shop using the existing bootstrap.

Secrets must already exist. Their values never enter this process or its output.
The bootstrap inserts the pre-generated REST pair into WooCommerce; it does not
replace credentials or reset an existing shop.
"""
import argparse
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
TARGET = 'urumi-m10'
SALTS = ('AUTH_KEY', 'SECURE_AUTH_KEY', 'LOGGED_IN_KEY', 'NONCE_KEY',
         'AUTH_SALT', 'SECURE_AUTH_SALT', 'LOGGED_IN_SALT', 'NONCE_SALT')


def build_job(image, name, target=TARGET):
    """Reuse the M2 bootstrap and exact mounted-file contract, without new PHP."""
    if target not in ('urumi-m10', 'urumi-m10-clean') or not image or not name.startswith(target + '-setup-'):
        raise ValueError('An explicit store image and owned setup Job name are required.')
    volumes = [{'name': 'content', 'persistentVolumeClaim': {
        'claimName': target + '-wordpress-content'}}]
    mounts = [{'name': 'content', 'mountPath': '/var/www/html'}]
    volumes.append({'name': 'store-theme', 'configMap': {'name': target + '-store-theme'}})
    mounts.append({'name': 'store-theme', 'mountPath': '/var/www/html/wp-content/themes/urumi-shop',
                   'readOnly': True})
    for group, suffix in [('database', 'store-db'), ('admin', 'store-admin'),
                          ('salts', 'store-salts'), ('rest', 'woocommerce-rest')]:
        volume = {'name': group, 'secret': {'secretName': target + '-' + suffix}}
        if group == 'database':
            volume['secret']['items'] = [{'key': 'database-password', 'path': 'database-password'}]
        volumes.append(volume)
        mounts.append({'name': group, 'mountPath': '/run/urumi/' + group, 'readOnly': True})
    environment = [{'name': 'WORDPRESS_DB_PASSWORD_FILE',
                    'value': '/run/urumi/database/database-password'}]
    environment += [{'name': 'WORDPRESS_' + key + '_FILE', 'value': '/run/urumi/salts/' + key}
                    for key in SALTS]
    container = {
        'name': 'setup', 'image': image, 'imagePullPolicy': 'IfNotPresent',
        'workingDir': '/var/www/html', 'envFrom': [{'configMapRef': {'name': target + '-store'}}],
        'env': environment, 'volumeMounts': mounts,
        'securityContext': {'allowPrivilegeEscalation': False,
                            'capabilities': {'drop': ['ALL']},
                            'seccompProfile': {'type': 'RuntimeDefault'}},
        'resources': {'requests': {'cpu': '100m', 'memory': '128Mi'},
                      'limits': {'cpu': '500m', 'memory': '512Mi'}},
        'command': ['bash', '-c', 'set -e; for n in $(seq 1 60); do test -f wp-config.php '
                    '&& break; sleep 2; done; test -f wp-config.php; '
                    'wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress; '
                    'wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress; '
                    'wp theme activate urumi-shop'],
    }
    return {'apiVersion': 'batch/v1', 'kind': 'Job',
            'metadata': {'name': name, 'namespace': target,
                         'labels': {'urumi.dev/module': 'm10', 'urumi.dev/task': 'store-bootstrap'}},
            'spec': {'backoffLimit': 0, 'activeDeadlineSeconds': 300,
                     'template': {'metadata': {'labels': {'app.kubernetes.io/instance': target,
                                                         'urumi-m2-access': 'setup'}},
                                  'spec': {'automountServiceAccountToken': False,
                                           'restartPolicy': 'Never',
                                           'securityContext': {'runAsUser': 33, 'runAsGroup': 33,
                                                               'fsGroup': 33},
                                           'volumes': volumes, 'containers': [container]}}}}


def safe_result(logs):
    """Extract only the bootstrap's fixed public result, never arbitrary logs."""
    expected = {'product_id', 'attachment_id', 'key_id', 'currency', 'timezone'}
    for line in reversed(logs.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(result, dict) or set(result) != expected:
            continue
        if any(type(result[key]) is not int or result[key] <= 0
               for key in ['product_id', 'attachment_id', 'key_id']):
            continue
        if result['currency'] == 'INR' and result['timezone'] == 'Asia/Kolkata':
            return result
    raise RuntimeError('Setup returned no valid safe result; raw logs were not exported.')


def bootstrap(context, kubeconfig, kubectl='kubectl', target=TARGET):
    if target not in ('urumi-m10', 'urumi-m10-clean') or context != 'k3d-urumi' or not Path(kubeconfig).is_file():
        raise ValueError('Fresh shop setup requires explicit k3d-urumi context and existing kubeconfig.')
    base = [str(kubectl), '--context', context, '--kubeconfig', str(kubeconfig)]

    def command(arguments, payload=None, timeout=40):
        process = subprocess.run(base + arguments, input=payload, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=timeout)
        if process.returncode:
            raise RuntimeError('Scoped M10 setup command failed; raw diagnostics were not exported.')
        return process.stdout

    ns = json.loads(command(['get', 'namespace', target, '-o', 'json']))
    if ns['metadata'].get('labels', {}).get('urumi.dev/module') != 'm10':
        raise ValueError('Fresh target namespace must carry urumi.dev/module=m10.')
    scoped = ['-n', target]
    deployment = json.loads(command(scoped + ['get', 'deployment', target + '-wordpress', '-o', 'json']))
    labels = deployment['spec']['template']['metadata']['labels']
    if labels.get('app.kubernetes.io/instance') != target or labels.get('app.kubernetes.io/component') != 'wordpress':
        raise ValueError('Selected WordPress workload does not belong to the fresh M10 release.')
    container = next(c for c in deployment['spec']['template']['spec']['containers'] if c['name'] == 'wordpress')
    # Read only Secret key names. Secret data is never retrieved into Python.
    required = {'store-db': {'database-password'}, 'store-admin': {'username', 'password', 'email'},
                'store-salts': set(SALTS), 'woocommerce-rest': {'consumer-key', 'consumer-secret'}}
    for suffix, keys in required.items():
        names = command(scoped + ['get', 'secret', target + '-' + suffix,
                                  '-o', 'go-template={{range $k,$v := .data}}{{$k}}{{"\\n"}}{{end}}'])
        if not keys <= set(names.split()):
            raise ValueError('Required fresh-store Secret key names are missing.')
    job_name = target + '-setup-' + uuid.uuid4().hex[:8]
    job = build_job(container['image'], job_name, target)
    command(scoped + ['create', '-f', '-'], json.dumps(job))
    command(scoped + ['wait', '--for=condition=complete', 'job/' + job_name, '--timeout=320s'], timeout=340)
    result = safe_result(command(scoped + ['logs', 'job/' + job_name]))
    # Delete only our unique completed Job, never Pods, PVCs, or retained shop resources.
    command(scoped + ['delete', 'job', job_name, '--wait=true'], timeout=90)
    return {'namespace': target, 'release': target, 'setup_job': job_name,
            'status': 'STORE_BOOTSTRAP_COMPLETE', 'completed_job_removed': True, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', required=True)
    parser.add_argument('--kubeconfig', type=Path, required=True)
    parser.add_argument('--kubectl', default='kubectl')
    parser.add_argument('--namespace', choices=['urumi-m10', 'urumi-m10-clean'], default=TARGET)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not any(output.is_relative_to(ROOT / base) for base in ['.tools/m10', 'docs/evidence/m10']):
        parser.error('Output must be inside .tools/m10 or docs/evidence/m10.')
    try:
        result = bootstrap(args.context, args.kubeconfig, args.kubectl, args.namespace)
    except (ValueError, RuntimeError, KeyError, StopIteration, subprocess.TimeoutExpired, json.JSONDecodeError):
        parser.exit(1, 'Fresh M10 store setup failed; no raw logs or Secret values were exported.\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Fresh M10 shop configured; safe result saved. Credentials were not printed.')


if __name__ == '__main__':
    main()
