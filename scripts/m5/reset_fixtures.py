"""Reset only owned isolated host fixtures before a fresh live acceptance bootstrap."""
import json
import subprocess
from pathlib import Path

import psycopg

from backend.db.database import Database


def main():
    namespace='urumi-m5-check'
    kube=['kubectl','--kubeconfig','.tools/m1/kubeconfig.yaml','--context','k3d-urumi','-n',namespace]
    resource=subprocess.run(kube+['get','namespace',namespace,'-o','json'],text=True,capture_output=True)
    if resource.returncode:
        raise RuntimeError('Owned isolated namespace was not found.')
    labels=json.loads(resource.stdout)['metadata'].get('labels',{})
    if labels.get('urumi-module')!='m5' or labels.get('urumi-owner')!=namespace:
        raise RuntimeError('Namespace ownership guard failed.')
    observed=subprocess.run(kube+['exec','deployment/urumi-m5-check-platform-db','--','psql','-U','urumi','-d','urumi','-Atqc','SELECT id FROM installation'],text=True,capture_output=True)
    if observed.returncode:
        raise RuntimeError('Isolated database identity could not be verified.')
    password=json.loads(Path('.tools/m5/db.json').read_text())['password']
    db=Database(psycopg.conninfo.make_conninfo(host='127.0.0.1',port=15435,user='urumi',dbname='urumi',password=password))
    db.acquire_owner()
    try:
        with db.transaction() as c:
            local=str(c.execute('SELECT id FROM installation').fetchone()['id'])
            if local!=observed.stdout.strip():
                raise RuntimeError('Port forward does not match the owned isolated database.')
            c.execute('TRUNCATE users,invitations,sessions,api_keys,servers,secret_operations,canceled_secret_names,audit_records CASCADE')
        print('PASS: only verified owned M5 fixture records reset; schema/installation/PVC retained.')
    finally:
        db.close()


if __name__=='__main__':
    try:
        main()
    except Exception:
        print('FAIL: isolated fixture reset refused or failed; sensitive output suppressed.')
        raise SystemExit(1) from None
