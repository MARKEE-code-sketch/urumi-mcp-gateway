"""Create only the isolated, labeled M5 test namespace and throwaway DB Secret."""
import base64
import json
import secrets
import subprocess
from pathlib import Path

NAMESPACE = 'urumi-m5-check'
SECRET_NAMESPACE = 'urumi-m5-upstream-secrets-check'
KUBE = ['kubectl','--kubeconfig','.tools/m1/kubeconfig.yaml','--context','k3d-urumi']


def kubectl(*args, document=None):
    result = subprocess.run(KUBE + list(args), input=json.dumps(document) if document else None,
                            text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Kubernetes command failed; credential-bearing output suppressed.')
    return result.stdout


def main():
    for namespace in (NAMESPACE, SECRET_NAMESPACE):
        existing = subprocess.run(KUBE+['get','namespace',namespace,'-o','json'],capture_output=True,text=True)
        if existing.returncode==0:
            labels=json.loads(existing.stdout)['metadata'].get('labels',{})
            if labels.get('urumi-module')!='m5' or labels.get('urumi-owner')!=NAMESPACE:
                raise RuntimeError('Existing namespace is not owned by the isolated M5 check.')
    existing = subprocess.run(KUBE+['get','namespace',NAMESPACE,'-o','name'],capture_output=True,text=True)
    if existing.returncode:
        kubectl('create','-f','-',document={'apiVersion':'v1','kind':'Namespace','metadata':{'name':NAMESPACE,'labels':{'urumi-module':'m5','urumi-owner':NAMESPACE}}})
    path=Path('.tools/m5/db.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        password=json.loads(path.read_text())['password']
    else:
        password=secrets.token_hex(32)
        path.write_text(json.dumps({'password':password}))
    kubectl('apply','-f','-',document={'apiVersion':'v1','kind':'Secret','metadata':{'name':'urumi-m5-db','namespace':NAMESPACE},'type':'Opaque','data':{'password':base64.b64encode(password.encode()).decode()}})
    print('PASS: isolated namespace ownership checked; throwaway DB Secret prepared without disclosure.')


if __name__=='__main__':
    main()
