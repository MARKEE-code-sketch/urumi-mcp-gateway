"""Read image/resource state and prove network isolation in the owned M6 harness."""
import json
from pathlib import Path
import subprocess

kube = ['kubectl', '--kubeconfig', '.tools/m1/kubeconfig.yaml', '--context', 'k3d-urumi']
def run(*args):
    return subprocess.run(kube + list(args), text=True, capture_output=True, check=True, timeout=30).stdout

namespace = json.loads(run('get', 'namespace', 'urumi-m6-check', '-o', 'json'))
assert namespace['metadata'].get('labels', {}).get('urumi.dev/module') == 'm6-check'
resources = json.loads(run('-n', 'urumi-m6-check', 'get', 'pods,services,deployments,networkpolicies', '-o', 'json'))
Path('docs/evidence/m6/cluster-resources-before.json').write_text(json.dumps(resources, indent=2)+'\n')
digest = json.loads(Path('docs/evidence/m6/image-identity.json').read_text())['config_digest']
pods = [p for p in resources['items'] if p['kind'] == 'Pod']
assert len(pods) == 4
observed = []
for pod in pods:
    status = pod['status']['containerStatuses'][0]
    assert status['ready'] and status['imageID'] == digest
    observed.append({'name': pod['metadata']['name'], 'uid': pod['metadata']['uid'], 'image_id': status['imageID']})
Path('docs/evidence/m6/runtime-image-check.json').write_text(json.dumps({'status':'PASS', 'pods':observed}, indent=2)+'\n')
service = json.loads(run('-n','urumi-m6-check','get','service','urumi-m6-check-bearer','-o','json'))
target = service['spec']['clusterIP']
probe = '''import httpx,json,sys,time
started=time.monotonic()
try:
 r=httpx.get('http://'+sys.argv[1]+':8000/readyz',timeout=2,trust_env=False)
 print(json.dumps({'status':'ALLOWED','http_status':r.status_code}))
except (httpx.ConnectTimeout,httpx.ConnectError) as error:
 print(json.dumps({'status':'DENIED','blocked':True,'exception_type':type(error).__name__,'seconds':round(time.monotonic()-started,3)}))
'''
allowed_before = json.loads(run('-n','urumi-m6-check','exec','deploy/urumi-m6-check-gateway','--','python','-c',probe,target))
assert allowed_before.get('http_status') == 200
result = json.loads(run('-n','urumi-m6-check','exec','deploy/urumi-m6-check-none','--','python','-c',probe,target))
assert result['status'] == 'DENIED'
allowed_after = json.loads(run('-n','urumi-m6-check','exec','deploy/urumi-m6-check-gateway','--','python','-c',probe,target))
assert allowed_after.get('http_status') == 200
result.update(status='PASS',allowed_before=allowed_before,allowed_after=allowed_after)
result.update(source='none fixture',destination='bearer fixture Service IP',boundary='actual fixture egress-deny policy')
Path('docs/evidence/m6/network-denial.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS: four deployed image identities match; actual fixture-to-fixture egress denied.')
