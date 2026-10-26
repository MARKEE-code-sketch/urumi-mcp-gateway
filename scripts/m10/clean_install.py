"""Disposable source-package installation; exact owned target, no provider calls.

Tool paths, reviewed immutable image values, kubeconfig and local CA are explicit
operator inputs outside the source package. Raw command/HTTP errors are suppressed.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import httpx
import psycopg
import yaml
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from backend.db.database import Database
from scripts.m5.operator import bootstrap as admin_bootstrap
from scripts.m9.preflight import load_values, merge, required_secrets, validate
from scripts.m10.store_bootstrap import bootstrap as store_bootstrap, SALTS
from scripts.m10.live_checks import gateway, wait_tools, result_data

NS = 'urumi-m10-clean'
HOST = 'dashboard-m10-clean.urumi.test'
SHOP = 'shop-m10-clean.urumi.test'


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def run(args, data=None, timeout=60):
    process = subprocess.run([str(x) for x in args], input=json.dumps(data) if data else None,
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout,
        cwd=ROOT)
    require(process.returncode == 0, 'scoped_command')
    return process.stdout


def leaf(certificate, key, directory):
    ca = x509.load_pem_x509_certificate(certificate.read_bytes())
    ca_key = serialization.load_pem_private_key(key.read_bytes(), password=None)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)]))
        .issuer_name(ca.subject).public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
        .not_valid_after(now+timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST),x509.DNSName(SHOP)]),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
        .sign(ca_key,hashes.SHA256()))
    cert_text = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_text = leaf_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    (directory/'tls.crt').write_text(cert_text)
    (directory/'tls.key').write_text(key_text)
    return cert_text, key_text


def execute(args, evidence):
    private = args.private_dir.resolve()
    require(private.is_dir() and not (private/'access.json').exists(), 'fresh_private_inputs')
    with socket.socket() as check:
        check.bind(('127.0.0.1',15442))
    kube = [args.kubectl,'--kubeconfig',args.kubeconfig,'--context',args.context]
    def k(command, data=None, timeout=60):
        return run(kube+command,data,timeout)
    def obj(command):
        return json.loads(k(command))
    for name in [NS,NS+'-secrets']:
        require(not k(['get','namespace',name,'--ignore-not-found','-o','name']).strip(), 'target_exists')
    access = {name:secrets.token_urlsafe(32) for name in
        ['admin_password','store_password','database_password','root_password','platform_password']}
    access.update(admin_email='clean-admin@example.test',store_username='cleanadmin',store_email='clean-admin@example.test',
        consumer_key='ck_'+secrets.token_hex(20),consumer_secret='cs_'+secrets.token_hex(20),
        salts={name:secrets.token_urlsafe(48) for name in SALTS})
    (private/'access.json').write_text(json.dumps(access,indent=2))
    cert, cert_key = leaf(args.ca_cert,args.ca_key,private)
    values = load_values(args.input_values)
    values = merge(values, {'release':{'provenance':'m10-clean-staged-source'},
        'store':{'canonicalUrl':'http://'+SHOP,'ingress':{'host':SHOP},'secrets':{
            'database':NS+'-store-db','admin':NS+'-store-admin','salts':NS+'-store-salts','rest':NS+'-woocommerce-rest'}},
        'woocommerceMcp':{'canonicalOrigin':'http://'+SHOP,'transportOrigin':f'http://{NS}-wordpress.{NS}.svc.cluster.local',
            'existingSecret':NS+'-woocommerce-rest','networkPolicy':{'shopNamespace':NS,'shopLabels':{
                'app.kubernetes.io/name':'urumi','app.kubernetes.io/instance':NS,'app.kubernetes.io/component':'wordpress'}}},
        'platformDb':{'existingSecret':NS+'-platform-db'},
        'platformAccess':{'secretNamespace':NS+'-secrets','serviceAccount':NS+'-backend'},
        'backend':{'origin':'https://'+HOST,'existingProviderSecret':NS+'-groq'},
        'dashboard':{'ingress':{'host':HOST,'tlsSecret':NS+'-dashboard-tls'}}})
    supplied = json.loads(args.inventory.read_text())
    supplied['secrets'] = required_secrets(values)
    supplied['certificates'] = [{'host':HOST,'trusted':True}]
    require(not validate(values,'deploy',supplied,root=ROOT,namespace=NS), 'deploy_preflight')
    values_path = private/'values.yaml'
    values_path.write_text(yaml.safe_dump(values,sort_keys=False))
    chart = ROOT/'deploy/charts/urumi'
    run([args.helm,'lint',chart,'-f',values_path])
    run([args.helm,'template',NS,chart,'--namespace',NS,'-f',values_path])
    evidence['checks'].append('staged_chart_lint_render_deploy_preflight')
    k(['create','-f','-'],{'apiVersion':'v1','kind':'Namespace','metadata':{'name':NS,
        'labels':{'urumi.dev/module':'m10','urumi.dev/task':'clean-rehearsal'}}})
    uid = obj(['get','namespace',NS,'-o','json'])['metadata']['uid']
    evidence['namespace_uid'] = uid
    evidence['namespace'] = NS
    # Persist ownership before creating workloads so interrupted runs can be inspected safely.
    (private/'ownership.json').write_text(json.dumps({'namespace':NS,'uid':uid}))
    groups = {'store-db':{'database-password':access['database_password'],'root-password':access['root_password']},
        'store-admin':{'username':access['store_username'],'email':access['store_email'],'password':access['store_password']},
        'store-salts':access['salts'],'woocommerce-rest':{'consumer-key':access['consumer_key'],'consumer-secret':access['consumer_secret']},
        'platform-db':{'password':access['platform_password']},'groq':{'api-key':'gsk_CLEAN_REHEARSAL_NO_PROVIDER_CALL'},
        'dashboard-tls':{'tls.crt':cert,'tls.key':cert_key}}
    for suffix,data in groups.items():
        k(['-n',NS,'create','-f','-'],{'apiVersion':'v1','kind':'Secret','metadata':{'name':NS+'-'+suffix,'namespace':NS,
            'labels':{'urumi.dev/module':'m10'}},'type':'kubernetes.io/tls' if suffix=='dashboard-tls' else 'Opaque','stringData':data})
    run([args.helm,'install',NS,chart,'--namespace',NS,'--kube-context',args.context,'--kubeconfig',args.kubeconfig,'-f',values_path],timeout=90)
    secret_ns=obj(['get','namespace',NS+'-secrets','-o','json'])
    require(secret_ns['metadata']['labels'].get('urumi-owner')==NS,'secret_namespace_owner')
    (private/'ownership.json').write_text(json.dumps({'namespace':NS,'uid':uid,
        'secret_namespace_uid':secret_ns['metadata']['uid']}))
    # WordPress readiness deliberately fails until the store has been installed.
    for kind,name in [('statefulset','mariadb')]:
        k(['-n',NS,'rollout','status',kind+'/'+NS+'-'+name,'--timeout=300s'],timeout=320)
    k(['-n',NS,'wait','--for=jsonpath={.status.phase}=Running','pods','-l',
       'app.kubernetes.io/component=wordpress','--timeout=180s'],timeout=200)
    evidence['store_bootstrap'] = store_bootstrap(args.context,args.kubeconfig,args.kubectl,target=NS)
    k(['-n',NS,'scale','deployment/'+NS+'-backend','--replicas=0'])
    deadline=time.monotonic()+60
    while obj(['-n',NS,'get','pods','-l','app.kubernetes.io/component=backend','-o','json'])['items']:
        require(time.monotonic()<deadline,'backend_stop'); time.sleep(.5)
    name=NS+'-admin-bootstrap'
    k(['-n',NS,'create','-f','-'],{'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':NS},
        'stringData':{'email':access['admin_email'],'password':access['admin_password']}})
    forward=subprocess.Popen([str(x) for x in kube+['-n',NS,'port-forward','--address','127.0.0.1','service/'+NS+'-platform-db','15442:5432']],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    db=None
    try:
        dsn=psycopg.conninfo.make_conninfo(host='127.0.0.1',port=15442,user='urumi',dbname='urumi',password=access['platform_password'])
        deadline=time.monotonic()+30
        while True:
            require(forward.poll() is None,'database_forward')
            try: db=Database(dsn); db.acquire_owner(); break
            except Exception:
                require(time.monotonic()<deadline,'database_owner'); time.sleep(.4)
        evidence['admin_user_id']=str(admin_bootstrap(db,name,NS,str(args.kubeconfig),args.context))
        db.close(); db=None
        k(['-n',NS,'scale','deployment/'+NS+'-backend','--replicas=1'])
        runtime_checks(args,evidence,k,obj,access,dsn)
    finally:
        if db: db.close()
        forward.terminate()
        try: forward.wait(timeout=5)
        except subprocess.TimeoutExpired: forward.kill(); forward.wait()
        k(['-n',NS,'scale','deployment/'+NS+'-backend','--replicas=1'])
    evidence['status']='PASS_RUNTIME_CLEANUP_PENDING'


def runtime_checks(args,evidence,k,obj,access,dsn):
    private=args.private_dir.resolve()
    for kind,component in [('statefulset','mariadb'),('deployment','platform-db')]+[('deployment',x) for x in
            ['wordpress','woocommerce-mcp','inventory-mcp','backend','dashboard']]:
        k(['-n',NS,'rollout','status',kind+'/'+NS+'-'+component,'--timeout=240s'],timeout=260)
    pods=obj(['-n',NS,'get','pods','-l','app.kubernetes.io/instance='+NS,'-o','json'])['items']
    pvcs=[obj(['-n',NS,'get','pvc',NS+'-'+suffix,'-o','json']) for suffix in
        ['mariadb-data','wordpress-content','platform-data']]
    require(all(p['metadata'].get('annotations',{}).get('meta.helm.sh/release-name')==NS and
        p['metadata'].get('annotations',{}).get('meta.helm.sh/release-namespace')==NS for p in pvcs),'pvc_helm_owners')
    require(len(pods)==7 and all(any(c.get('type')=='Ready' and c.get('status')=='True' for c in p['status'].get('conditions',[])) for p in pods),'seven_ready')
    require(len(pvcs)==3 and all(p['status']['phase']=='Bound' for p in pvcs),'three_bound')
    evidence['pods']=[{'name':p['metadata']['name'],'uid':p['metadata']['uid'],'containers':[
        {key:c.get(key) for key in ['name','image','imageID','ready','restartCount']} for c in p['status']['containerStatuses']]} for p in pods]
    evidence['pvcs']=[{'name':p['metadata']['name'],'uid':p['metadata']['uid']} for p in pvcs]
    (private/'owned-pvcs.json').write_text(json.dumps(evidence['pvcs']))
    evidence['checks'].append('seven_ready_three_new_bound_pvcs')
    # Override resolution only for this process; original Host and TLS SNI remain intact.
    original=socket.getaddrinfo
    socket.getaddrinfo=lambda host,*a,**kw: original('127.0.0.1' if
        (host.decode() if isinstance(host,bytes) else host) in [HOST,SHOP] else host,*a,**kw)
    try:
        context=ssl.create_default_context(cafile=str(args.ca_cert))
        with httpx.Client(base_url='https://'+HOST,verify=context,trust_env=False,timeout=40) as client:
            require(client.get('/').status_code==200,'https_shell')
            response=client.post('/api/v1/auth/login',headers={'Origin':'https://'+HOST},json={'email':access['admin_email'],'password':access['admin_password']})
            require(response.status_code==200,'admin_login')
            csrf=response.json()['csrf_token']; headers={'Origin':'https://'+HOST,'X-CSRF-Token':csrf}
            def api(method,path,data=None):
                deadline=time.monotonic()+30
                while True:
                    reply=client.request(method,'/api/v1'+path,headers=headers,json=data)
                    if method!='GET' or reply.status_code!=503 or time.monotonic()>=deadline: break
                    time.sleep(.5)
                require(reply.status_code in [200,201,204],'api_'+str(reply.status_code))
                return reply.json() if reply.content else None
            def builtin(): return [s for s in api('GET','/servers')['items'] if s['slug']=='woocommerce']
            initial=builtin(); require(len(initial)==1,'one_builtin')
            identifier=initial[0]['id']; evidence['builtin_server_id']=identifier
            def restart():
                k(['-n',NS,'rollout','restart','deployment/'+NS+'-backend'])
                k(['-n',NS,'rollout','status','deployment/'+NS+'-backend','--timeout=180s'],timeout=200)
            if args.action=='finish-builtin':
                prior=json.loads(args.output.read_text())
                require(prior.get('builtin_server_id')==identifier and prior.get('fresh_products_count')==1 and
                    initial[0]['name']=='Clean edited WooCommerce' and initial[0]['enabled'] is False,'resume_edited_state')
                old=[p['uid'] for p in prior['pods'] if '-backend-' in p['name']]
                new=[p['metadata']['uid'] for p in pods if '-backend-' in p['metadata']['name']]
                require(len(old)==len(new)==1 and old!=new,'resume_restart_observed')
                evidence['fresh_products_count']=prior['fresh_products_count']
                evidence['prior_mcp_read_evidence']='runtime-before-builtin-finish.json'
            else:
                user_id=response.json()['user']['id']
                key=api('POST','/members/'+user_id+'/keys',{'label':'Clean rehearsal read only'})
                async def read_products():
                    async with gateway('https://'+HOST,context,key['raw_key']) as session:
                        names=await wait_tools(session,['woocommerce'])
                        require('woocommerce__list_products' in names,'woo_discovered')
                        products=result_data(await session.call_tool('woocommerce__list_products',{'page':1,'per_page':10}))
                        require(bool(products.get('items')),'fresh_product_present')
                        return len(products['items'])
                try: evidence['fresh_products_count']=asyncio.run(read_products())
                finally: api('DELETE','/members/'+user_id+'/keys/'+key['id'])
                evidence['checks'].append('fresh_store_rest_credentials_gateway_mcp_product_read_key_revoked')
                api('PATCH','/servers/'+identifier,{'name':'Clean edited WooCommerce','enabled':False})
                restart()
            edited=builtin(); require(len(edited)==1 and edited[0]['id']==identifier and edited[0]['name']=='Clean edited WooCommerce' and edited[0]['enabled'] is False,'edited_survives')
            evidence['checks'].append('builtin_edit_disable_survives_restart_same_id')
            api('DELETE','/servers/'+identifier)
            restart(); require(not builtin(),'deleted_stays_absent')
            with psycopg.connect(dsn) as connection:
                markers=connection.execute("SELECT server_id FROM builtin_initializations WHERE name='woocommerce'").fetchall()
            require(len(markers)==1 and str(markers[0][0])==identifier,'durable_marker')
            evidence['checks']+=['trusted_https_shell_and_real_admin_login','builtin_delete_survives_restart_marker_retained']
    finally: socket.getaddrinfo=original


def cleanup(args, evidence):
    """Delete only the recorded, independently owned clean-release objects."""
    private=args.private_dir.resolve()
    ownership=json.loads((private/'ownership.json').read_text())
    kube=[args.kubectl,'--kubeconfig',args.kubeconfig,'--context',args.context]
    def read(command): return json.loads(run(kube+command))
    ns=read(['get','namespace',NS,'-o','json'])
    require(ownership['namespace']==NS and ns['metadata']['uid']==ownership['uid'] and
        ns['metadata']['labels'].get('urumi.dev/task')=='clean-rehearsal','namespace_cleanup_guard')
    secret_ns=read(['get','namespace',NS+'-secrets','-o','json'])
    require(secret_ns['metadata']['uid']==ownership['secret_namespace_uid'] and
        secret_ns['metadata']['labels'].get('urumi-owner')==NS,'secret_namespace_cleanup_guard')
    pvcs=json.loads((private/'owned-pvcs.json').read_text())
    require({p['name'] for p in pvcs}=={NS+'-'+suffix for suffix in
        ['mariadb-data','wordpress-content','platform-data']},'pvc_names_cleanup_guard')
    for claim in pvcs:
        live=read(['-n',NS,'get','pvc',claim['name'],'-o','json'])
        require(live['metadata']['uid']==claim['uid'] and
            live['metadata'].get('annotations',{}).get('meta.helm.sh/release-name')==NS and
            live['metadata'].get('annotations',{}).get('meta.helm.sh/release-namespace')==NS,'pvc_uid_cleanup_guard')
    run([args.helm,'uninstall',NS,'--namespace',NS,'--kube-context',args.context,'--kubeconfig',args.kubeconfig],timeout=120)
    for claim in pvcs:
        run(kube+['delete','--raw',f"/api/v1/namespaces/{NS}/persistentvolumeclaims/{claim['name']}",'-f','-'],
            {'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':claim['uid']}})
    for name,uid in [(NS+'-secrets',ownership['secret_namespace_uid']),(NS,ownership['uid'])]:
        run(kube+['delete','--raw','/api/v1/namespaces/'+name,'-f','-'],
            {'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':uid}})
        run(kube+['wait','--for=delete','namespace/'+name,'--timeout=180s'],timeout=200)
        require(not run(kube+['get','namespace',name,'--ignore-not-found','-o','name']).strip(),'namespace_absence')
    evidence.update(status='PASS',namespace=NS,removed_owned_pvcs=3,
        checks=['exact_namespace_owner_and_uid','all_three_pvc_owners_and_uids',
                'scoped_helm_uninstall','uid_precondition_deletes','both_owned_namespaces_absent'])


def resume(args,evidence):
    """Continue checks after successful bootstrap; never replay provisioning writes."""
    private=args.private_dir.resolve()
    ownership=json.loads((private/'ownership.json').read_text())
    access=json.loads((private/'access.json').read_text())
    kube=[args.kubectl,'--kubeconfig',args.kubeconfig,'--context',args.context]
    def k(command,data=None,timeout=60): return run(kube+command,data,timeout)
    def obj(command): return json.loads(k(command))
    namespace=obj(['get','namespace',NS,'-o','json'])
    require(namespace['metadata']['uid']==ownership['uid'] and namespace['metadata']['labels'].get('urumi.dev/task')=='clean-rehearsal','resume_owner')
    with socket.socket() as check: check.bind(('127.0.0.1',15442))
    forward=subprocess.Popen([str(x) for x in kube+['-n',NS,'port-forward','--address','127.0.0.1','service/'+NS+'-platform-db','15442:5432']],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        dsn=psycopg.conninfo.make_conninfo(host='127.0.0.1',port=15442,user='urumi',dbname='urumi',password=access['platform_password'])
        deadline=time.monotonic()+30
        while True:
            require(forward.poll() is None,'resume_forward')
            try:
                with psycopg.connect(dsn) as connection: connection.execute('SELECT 1')
                break
            except Exception:
                require(time.monotonic()<deadline,'resume_db_connect');time.sleep(.4)
        runtime_checks(args,evidence,k,obj,access,dsn)
        evidence['status']='PASS_RUNTIME_CLEANUP_PENDING'
    finally:
        forward.terminate()
        try: forward.wait(timeout=5)
        except subprocess.TimeoutExpired: forward.kill();forward.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['private-dir','kubeconfig','helm','input-values','inventory','ca-cert','ca-key','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--kubectl',default='kubectl')
    parser.add_argument('--context',choices=['k3d-urumi'],required=True)
    parser.add_argument('--action',choices=['install','resume','finish-builtin','cleanup'],default='install')
    args=parser.parse_args()
    evidence={'checked_at':datetime.now(timezone.utc).isoformat(),'checks':[],'provider_calls':0,
        'scope':'staged source chart/helpers; explicit cached immutable image inputs and private operator inputs'}
    try:
        if args.action=='cleanup': cleanup(args,evidence)
        elif args.action in ['resume','finish-builtin']: resume(args,evidence)
        else: execute(args,evidence)
    except Exception as error:
        evidence['status']='FAILED_REVIEW_REQUIRED'; evidence['failure_phase']='after_'+str(len(evidence['checks']))+'_completed_checks'
        evidence['failure_type']=type(error).__name__
        if type(error) is RuntimeError: evidence['failure_code']=str(error)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'status':evidence['status'],'checks':len(evidence['checks'])}))
    return evidence['status']=='FAILED_REVIEW_REQUIRED'


if __name__=='__main__': raise SystemExit(main())
