"""Restart only explicitly owned fresh M10 Pods and retain safe persistence evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

NS = 'urumi-m10'
COMPONENTS = ['wordpress', 'mariadb', 'backend', 'platform-db']

class Check:
    def __init__(self):
        self.base = ['kubectl', '--kubeconfig', '.tools/m1/kubeconfig.yaml', '--context', 'k3d-urumi']
        self.commands = []
        self.namespace_uid = None

    def command(self, args, payload=None, timeout=60, decode=True):
        result = subprocess.run(self.base + args, input=payload, capture_output=True,
            text=True, timeout=timeout)
        self.commands.append({'command': self.base + args, 'exit_code': result.returncode})
        if result.returncode:
            raise RuntimeError('Scoped command failed; raw output intentionally withheld.')
        return json.loads(result.stdout) if decode else result.stdout.strip()

    def guard(self):
        n = self.command(['get', 'namespace', NS, '-o', 'json'])
        assert n['metadata'].get('labels', {}).get('urumi.dev/module') == 'm10'
        uid = n['metadata']['uid']
        assert self.namespace_uid in (None, uid)
        self.namespace_uid = uid
        return uid

    def pod(self, component, ready=True):
        self.guard()
        selector = 'app.kubernetes.io/instance=' + NS + ',app.kubernetes.io/component=' + component
        pods = self.command(['-n', NS, 'get', 'pods', '-l', selector, '-o', 'json'])['items']
        pods = [p for p in pods if not p['metadata'].get('deletionTimestamp')]
        assert len(pods) == 1
        p = pods[0]
        assert p['metadata']['namespace'] == NS
        labels = p['metadata']['labels']
        assert labels['app.kubernetes.io/instance'] == NS
        assert labels['app.kubernetes.io/component'] == component
        owner = p['metadata']['ownerReferences'][0]
        if component == 'mariadb':
            assert owner['kind'] == 'StatefulSet' and owner['name'] == NS + '-mariadb'
            controller = self.command(['-n', NS, 'get', 'statefulset', owner['name'], '-o', 'json'])
            assert controller['metadata']['uid'] == owner['uid']
        else:
            assert owner['kind'] == 'ReplicaSet' and owner['name'].startswith(NS + '-' + component + '-')
            rs = self.command(['-n', NS, 'get', 'replicaset', owner['name'], '-o', 'json'])
            assert rs['metadata']['uid'] == owner['uid']
            deployment_owner = rs['metadata']['ownerReferences'][0]
            assert deployment_owner['kind'] == 'Deployment' and deployment_owner['name'] == NS + '-' + component
            controller = self.command(['-n', NS, 'get', 'deployment', deployment_owner['name'], '-o', 'json'])
            assert controller['metadata']['uid'] == deployment_owner['uid']
        assert controller['spec']['template']['metadata']['labels']['app.kubernetes.io/instance'] == NS
        assert controller['spec']['template']['metadata']['labels']['app.kubernetes.io/component'] == component
        if ready:
            assert any(c['type'] == 'Ready' and c['status'] == 'True' for c in p['status']['conditions'])
        return p

    def snapshot(self):
        self.guard()
        claims = self.command(['-n', NS, 'get', 'pvc', '-o', 'json'])['items']
        assert len(claims) == 3 and all(p['status']['phase'] == 'Bound' for p in claims)
        php = """$out=['products'=>[],'orders'=>[]];foreach([12,18] as $id){$p=wc_get_product($id);if(!$p){throw new Exception('missing product');}$out['products'][]=['id'=>$p->get_id(),'name'=>$p->get_name(),'price'=>$p->get_price(),'sku'=>$p->get_sku()];}foreach([16,19] as $id){$o=wc_get_order($id);if(!$o){throw new Exception('missing order');}$out['orders'][]=['id'=>$o->get_id(),'status'=>$o->get_status(),'total'=>$o->get_total(),'items'=>array_values(array_map(function($i){return ['product_id'=>$i->get_product_id(),'quantity'=>$i->get_quantity()];},$o->get_items()))];}$f=get_attached_file(13);if(!$f||!is_file($f)){throw new Exception('missing content');}$out['attachment']=['id'=>13,'sha256'=>hash_file('sha256',$f),'bytes'=>filesize($f)];echo json_encode($out);"""
        wp = self.pod('wordpress')['metadata']['name']
        store = self.command(['-n', NS, 'exec', wp, '--', 'wp', '--allow-root', 'eval', php])
        sql = """SELECT json_build_object('users',(SELECT json_agg(x ORDER BY id) FROM (SELECT id,role FROM users) x),'keys',(SELECT json_agg(x ORDER BY id) FROM (SELECT id,user_id,revoked_at IS NOT NULL AS revoked FROM api_keys) x),'servers',(SELECT json_agg(x ORDER BY id) FROM (SELECT id,slug,enabled FROM servers) x),'audits',(SELECT json_agg(x ORDER BY audit_id) FROM (SELECT audit_id,user_id,key_id,server_id,public_tool_name,outcome FROM audit_records) x),'builtin',(SELECT json_agg(x ORDER BY name) FROM (SELECT name,server_id FROM builtin_initializations) x));"""
        pg = self.pod('platform-db')['metadata']['name']
        platform = self.command(['-n', NS, 'exec', pg, '--', 'psql', '-X', '-A', '-t', '-U', 'urumi', '-d', 'urumi', '-c', sql])
        return {'observed_utc': datetime.now(timezone.utc).isoformat(),
            'pvcs': sorted([{'name':p['metadata']['name'],'uid':p['metadata']['uid'],'phase':p['status']['phase']} for p in claims],key=lambda p:p['name']),
            'store':store,'platform':platform}

    def retained_unchanged(self):
        baseline = json.loads(Path('.tools/m10/retained-before.json').read_text(encoding='utf-8-sig'))
        objects = self.command(['-n', 'urumi', 'get', 'pods,pvc,services', '-o', 'json'])['items']
        current = {(o['kind'], o['metadata']['name']): o['metadata']['uid'] for o in objects}
        comparison = [{'kind': o['kind'], 'name': o['name'], 'uid': o['uid'],
            'unchanged': current.get((o['kind'], o['name'])) == o['uid']} for o in baseline['resources']]
        assert len(comparison) == 7 and all(o['unchanged'] for o in comparison)
        return comparison

    def wait_all(self):
        start = time.monotonic()
        components = COMPONENTS + ['dashboard', 'woocommerce-mcp', 'inventory-mcp']
        while time.monotonic() - start < 240:
            try:
                for component in components: self.pod(component)
                return {'ready_components': components, 'seconds': round(time.monotonic()-start, 2)}
            except (AssertionError, RuntimeError):
                time.sleep(2)
        raise RuntimeError('Full release did not recover Ready before deadline.')

    def restart(self, component):
        p = self.pod(component)
        meta = p['metadata']; name, uid = meta['name'], meta['uid']
        payload = json.dumps({'apiVersion':'v1','kind':'DeleteOptions','preconditions':{'uid':uid}})
        self.command(['delete','--raw','/api/v1/namespaces/'+NS+'/pods/'+name,'-f','-'],payload=payload)
        start = time.monotonic()
        while time.monotonic()-start < 240:
            try:
                current = self.pod(component)
                if current['metadata']['uid'] != uid:
                    return {'component':component,'old_name':name,'old_uid':uid,
                        'new_name':current['metadata']['name'],'new_uid':current['metadata']['uid'],
                        'new_ready':True,'recovery_seconds':round(time.monotonic()-start,2),
                        'delete_uid_precondition':True}
            except (AssertionError,RuntimeError):
                pass
            time.sleep(2)
        raise RuntimeError('Replacement did not become Ready before recovery deadline.')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--restart-owned-demo',action='store_true')
    parser.add_argument('--output',type=Path,default=Path('docs/evidence/m10/persistence.json'))
    args=parser.parse_args()
    check=Check()
    evidence={'status':'FAIL','scope':'Only fresh urumi-m10; exact namespace and Pod/controller ownership guards; no Secret values; no restore claim.','restarts':[]}
    try:
        for component in COMPONENTS: check.pod(component)
        evidence['namespace_uid']=check.namespace_uid
        evidence['retained_before'] = check.retained_unchanged()
        evidence['before']=check.snapshot()
        if not args.restart_owned_demo:
            evidence['status']='PRECHECK_ONLY'
        else:
            for component in COMPONENTS:
                evidence['restarts'].append(check.restart(component))
                evidence['restarts'][-1]['release_recovery'] = check.wait_all()
                # Every replacement must recover application data before the next fault.
                current=check.snapshot()
                assert current['pvcs']==evidence['before']['pvcs']
                assert current['store']==evidence['before']['store']
                assert current['platform']==evidence['before']['platform']
                evidence['restarts'][-1]['data_unchanged']=True
            evidence['after']=check.snapshot()
            evidence['retained_after'] = check.retained_unchanged()
            evidence['status']='PASS'
    except Exception as exc:
        evidence['error_type']=type(exc).__name__
        raise
    finally:
        evidence['commands']=check.commands
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'status':evidence['status'],'restart_count':len(evidence['restarts']),'output':str(args.output)}))

if __name__=='__main__':main()
