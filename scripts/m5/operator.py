"""Explicit operator commands; credentials stay in process memory and Kubernetes Secrets."""
import argparse
import base64
import json
import os
import subprocess

import psycopg

from backend.db.database import Database
from backend.identity.auth import Identity
from backend.registry.servers import Registry
from backend.registry.secret_store import SecretStore


def database():
    return Database(psycopg.conninfo.make_conninfo(host=os.environ['PGHOST'],port=os.getenv('PGPORT','5432'),
        user=os.environ['PGUSER'],dbname=os.environ['PGDATABASE'],password=os.environ['PGPASSWORD']))


def bootstrap(db,secret,namespace,kubeconfig,context):
    command=['kubectl','--kubeconfig',kubeconfig,'--context',context,'-n',namespace]
    result=subprocess.run(command+['get','secret',secret,'-o','json'],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Bootstrap Secret could not be read.')
    document=json.loads(result.stdout)
    email=base64.b64decode(document['data']['email']).decode()
    password=base64.b64decode(document['data']['password']).decode()
    db.migrate()
    user=Identity(db).bootstrap(email,password)
    # UID guard prevents deleting a recreated/different bootstrap object.
    body={'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':document['metadata']['uid']}}
    # kubectl raw sends operator DeleteOptions without exposing the Secret payload.
    result=subprocess.run(command+['delete','--raw',f'/api/v1/namespaces/{namespace}/secrets/{secret}','-f','-'],
                          input=json.dumps(body),capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError('Admin is established; bootstrap Secret cleanup requires operator retry.')
    return user['id']


def reconcile(db):
    db.migrate(); db.acquire_owner()
    try:
        with db.transaction() as c:
            owner=c.execute('SELECT id FROM installation').fetchone()['id']
        secrets=SecretStore(os.environ['M5_SECRET_NAMESPACE'],owner)
        try:
            return Registry(db,secrets,json.loads(os.getenv('M5_INTERNAL_URLS','[]'))).recover()
        finally:
            secrets.close()
    finally:
        db.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['bootstrap','reconcile'])
    parser.add_argument('--secret')
    parser.add_argument('--namespace',default='urumi')
    parser.add_argument('--kubeconfig',default='.tools/m1/kubeconfig.yaml')
    parser.add_argument('--context',default='k3d-urumi')
    args=parser.parse_args()
    try:
        db=database()
        if args.action=='bootstrap':
            if not args.secret:
                parser.error('--secret is required for bootstrap')
            bootstrap(db,args.secret,args.namespace,args.kubeconfig,args.context)
            print('PASS: admin established and original bootstrap Secret removed.')
        else:
            remaining=reconcile(db)
            print('Reconciliation pass completed; unresolved operations:',remaining)
            if remaining:
                raise SystemExit(1)
    except Exception:
        print('FAIL: operator action did not complete; sensitive dependency output suppressed.')
        raise SystemExit(1) from None


if __name__=='__main__':
    main()
