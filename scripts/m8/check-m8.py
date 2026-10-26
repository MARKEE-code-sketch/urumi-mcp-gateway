"""Guarded independent M8 runtime check; no real backend/provider is mounted."""
import argparse
import hashlib
import json
import os
import socket
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen
from verify_cluster import verify_runtime

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'docs/evidence/m8'
NAMESPACE='urumi-m8-check'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cluster',action='store_true',required=True)
    parser.add_argument('--context',default='k3d-urumi')
    parser.add_argument('--cleanup',action='store_true')
    parser.add_argument('--kubeconfig',type=Path,default=ROOT/'.tools/m1/kubeconfig.yaml')
    parser.add_argument('--helm',type=Path,default=ROOT/'.tools/m1/helm.exe')
    args=parser.parse_args()
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    commands=[]
    def run(argv,check=True):
        result=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True)
        commands.append({'argv':argv,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
        (EVIDENCE/'cluster-commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
        if check and result.returncode:raise RuntimeError('Command failed: '+argv[0])
        return result
    kube=['kubectl','--context',args.context,'--kubeconfig',str(args.kubeconfig)]
    identities={}
    for label in ['dashboard','fixture']:
        identity=json.loads((EVIDENCE/('image-identity-'+label+'.json')).read_text(encoding='utf-8-sig'))
        identities[identity['image']]=identity
    def retained():
        data=json.loads(run(kube+['-n','urumi','get','pods,pvc,services','-o','json']).stdout)
        return {i['kind']+'/'+i['metadata']['name']:i['metadata']['uid'] for i in data['items']}
    before=retained()
    try:
        occupied=socket.create_connection(('127.0.0.1',18080),timeout=1)
    except OSError:
        occupied=None
    if occupied:
        occupied.close()
        raise RuntimeError('Loopback port 18080 is already occupied; refusing an ambiguous test origin.')
    existing=run(kube+['get','namespace',NAMESPACE,'-o','json'],False)
    if existing.returncode==0:raise RuntimeError('Refusing existing M8 namespace; inspect previous resources explicitly.')
    run(kube+['create','namespace',NAMESPACE])
    run(kube+['label','namespace',NAMESPACE,'urumi.dev/module=m8-check'])
    forward=None
    passed=False
    try:
        helm=str(args.helm)
        run([helm,'upgrade','--install',NAMESPACE,'deploy/charts/urumi','--kube-context',args.context,'--kubeconfig',str(args.kubeconfig),'--namespace',NAMESPACE,'-f','tests/dashboard/values-check.yaml','--wait','--timeout','180s'])
        resources=json.loads(run(kube+['-n',NAMESPACE,'get','pods,deployments,services,configmaps','-o','json']).stdout)
        (EVIDENCE/'cluster-resources.json').write_text(json.dumps(resources,indent=2),encoding='utf-8')
        proof=verify_runtime(resources,identities)
        (EVIDENCE/'runtime-verification.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
        expected={p.relative_to(ROOT/'frontend/dist').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()}
        if not expected or any(name.endswith('.map') for name in expected):
            raise RuntimeError('A built, source-map-free frontend is required.')
        asset_code='''import hashlib,json,sys,httpx
expected=json.loads(sys.argv[1]); proof={}
with httpx.Client(base_url="http://urumi-m8-check-dashboard",trust_env=False,timeout=5,follow_redirects=False) as client:
 for name,digest in expected.items():
  response=client.get("/"+name); assert response.status_code==200
  actual=hashlib.sha256(response.content).hexdigest(); assert actual==digest,name
  proof[name]={"sha256":actual,"bytes":len(response.content)}
 html=client.get("/index.html")
 assert html.headers["x-content-type-options"]=="nosniff"
 assert html.headers["referrer-policy"]=="no-referrer"
 assert "frame-ancestors 'none'" in html.headers["content-security-policy"]
 assert html.headers["cache-control"]=="no-store"
 for path in ["/livez","/readyz"]: assert client.get(path).status_code==200
 for path in ["/api/v1/auth/me","/mcp","/assets/missing.js"]: assert client.get(path).status_code==404
print(json.dumps({"assets":proof,"headers_health_and_missing_routes_verified":True}))'''
        asset_result=run(kube+['-n',NAMESPACE,'exec','deployment/'+NAMESPACE+'-dashboard-fixture','--',
                               'python','-c',asset_code,json.dumps(expected)])
        (EVIDENCE/'runtime-asset-check.json').write_text(json.dumps(json.loads(asset_result.stdout),indent=2),encoding='utf-8')
        forward=subprocess.Popen(kube+['-n',NAMESPACE,'port-forward','service/'+NAMESPACE+'-dashboard-fixture','18080:8000','--address','127.0.0.1'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(60):
            if forward.poll() is not None:
                raise RuntimeError('Fixture port-forward exited before readiness.')
            try:
                with urlopen('http://127.0.0.1:18080/readyz',timeout=1) as r:
                    if r.status==200:break
            except Exception:time.sleep(.25)
        else:raise RuntimeError('Fixture port-forward never became ready.')
        if forward.poll() is not None:raise RuntimeError('Fixture port-forward is not running.')
        env=dict(os.environ,M8_BASE_URL='http://127.0.0.1:18080')
        result=subprocess.run(['npm.cmd','--prefix','frontend','run','test:browser'],cwd=ROOT,env=env,text=True,capture_output=True)
        (EVIDENCE/'cluster-browser-output.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
        if result.returncode:raise RuntimeError('Cluster browser check failed.')
        after=retained()
        if before!=after:raise RuntimeError('Original shop resource identities changed.')
        passed=True
    finally:
        if forward:
            forward.terminate()
            try:forward.wait(timeout=5)
            except subprocess.TimeoutExpired:forward.kill()
        removed=False
        if passed and args.cleanup:
            namespace=json.loads(run(kube+['get','namespace',NAMESPACE,'-o','json']).stdout)
            if namespace['metadata'].get('labels',{}).get('urumi.dev/module')!='m8-check':raise RuntimeError('Namespace ownership changed; cleanup refused.')
            run(kube+['delete','namespace',NAMESPACE,'--wait=true','--timeout=120s'])
            removed=True
        (EVIDENCE/'cluster-results.json').write_text(json.dumps({'status':'PASS_RUNTIME_REVIEW_PENDING' if passed else 'FAIL','fixture_only':True,'retained_identities_unchanged':retained()==before,'owned_namespace_removed':removed,'runtime_identity_and_security_verified':passed},indent=2),encoding='utf-8')
    print('M8 isolated cluster/browser PASS; final M10 integration remains untested.')


if __name__=='__main__':main()
