"""Structural checks on complete Helm output, not live enforcement claims."""
from __future__ import annotations
import json
import ipaddress
import re
from pathlib import Path
import yaml

COMPONENTS = {'wordpress','mariadb','woocommerce-mcp','inventory-mcp','platform-db','backend','dashboard'}


def selected(labels, selector):
    return all(labels.get(key) == value for key, value in selector.items())


def allows(policy, direction, namespace, labels, port, protocol='TCP', address=None, policy_namespace='urumi'):
    """Evaluate the chart's exact matchLabels/ipBlock subset; not a CNI simulator."""
    for rule in policy.get(direction, []):
        if not any(p.get('protocol','TCP') == protocol and p['port'] == port for p in rule.get('ports',[])):
            continue
        for peer in rule.get('from' if direction=='ingress' else 'to',[]):
            if 'ipBlock' in peer:
                if address is None: continue
                ip=ipaddress.ip_address(address); block=peer['ipBlock']
                if ip in ipaddress.ip_network(block['cidr']) and not any(ip in ipaddress.ip_network(c) for c in block.get('except',[])): return True
            else:
                ns=peer.get('namespaceSelector',{}).get('matchLabels',{}).get('kubernetes.io/metadata.name',policy_namespace)
                if namespace == ns and selected(labels,peer.get('podSelector',{}).get('matchLabels',{})): return True
    return False


def inspect_render(text, release='urumi', namespace='urumi'):
    objects = [o for o in yaml.safe_load_all(text) if o]
    by_kind = {}
    for obj in objects:
        key = (obj['kind'],obj['metadata']['name'])
        assert key not in by_kind, ('duplicate object',key)
        by_kind[key] = obj
    workloads = [o for o in objects if o['kind'] in {'Deployment','StatefulSet'}]
    components = {o['spec']['template']['metadata']['labels']['app.kubernetes.io/component'] for o in workloads}
    assert components == COMPONENTS, components
    summary = {'workloads':[],'services':[],'ingresses':[],'pvcs':[],'secret_references':[],'policies':[],'rbac':[]}
    for obj in workloads:
        pod = obj['spec']['template']['spec']; labels = obj['spec']['template']['metadata']['labels']
        assert selected(labels,obj['spec']['selector']['matchLabels'])
        assert labels['app.kubernetes.io/instance'] == release
        component = labels['app.kubernetes.io/component']
        if component == 'backend':
            assert obj['spec']['replicas'] == 1 and obj['spec']['strategy']['type'] == 'Recreate'
            assert pod['containers'][0]['command'] == ['python','-m','backend.main']
            assert labels['urumi.dev/gateway'] == 'true' and pod['automountServiceAccountToken'] is True
            assert ('ServiceAccount',pod['serviceAccountName']) in by_kind
        else: assert pod['automountServiceAccountToken'] is False
        for c in pod['containers']:
            assert {'startupProbe','readinessProbe','livenessProbe'} <= c.keys(), component
            assert all({'cpu','memory'} <= c['resources'][part].keys() for part in ['requests','limits'])
            assert c['image'] and 'harness' not in c['image']
            for env in c.get('env',[]):
                ref = env.get('valueFrom',{}).get('secretKeyRef')
                if ref: summary['secret_references'].append(ref)
            for env in c.get('envFrom',[]):
                if 'configMapRef' in env: assert ('ConfigMap',env['configMapRef']['name']) in by_kind
        volumes = {v['name']:v for v in pod.get('volumes',[])}
        for c in pod['containers']:
            for mount in c.get('volumeMounts',[]):
                assert mount['name'] in volumes
                v = volumes[mount['name']]
                if 'persistentVolumeClaim' in v: assert ('PersistentVolumeClaim',v['persistentVolumeClaim']['claimName']) in by_kind
                if 'configMap' in v: assert ('ConfigMap',v['configMap']['name']) in by_kind
                if 'secret' in v: summary['secret_references'].append({'name':v['secret']['secretName'],'keys':'mounted'})
        summary['workloads'].append({'name':obj['metadata']['name'],'component':component,'containers':[{'image':c['image'],'probes':[c[k] for k in ['startupProbe','readinessProbe','livenessProbe']],'resources':c['resources']} for c in pod['containers']],'mounts':[m for c in pod['containers'] for m in c.get('volumeMounts',[])]})
    for obj in objects:
        name = obj['metadata']['name']; spec=obj.get('spec',{})
        if obj['kind'] == 'Service':
            assert spec.get('type','ClusterIP') == 'ClusterIP'
            matches = [w for w in workloads if selected(w['spec']['template']['metadata']['labels'],spec['selector'])]
            assert len(matches) == 1
            ports=matches[0]['spec']['template']['spec']['containers'][0]['ports']
            for p in spec['ports']:
                target=p.get('targetPort',p['port'])
                assert any(target in [p2.get('name'),p2['containerPort']] for p2 in ports)
            summary['services'].append({'name':name,'ports':spec['ports'],'selector':spec['selector']})
        if obj['kind'] == 'Ingress':
            paths=[]
            for rule in spec['rules']:
                for p in rule['http']['paths']:
                    svc=p['backend']['service']; assert ('Service',svc['name']) in by_kind
                    assert svc['port']['number'] in [q['port'] for q in by_kind[('Service',svc['name'])]['spec']['ports']]
                    paths.append({'host':rule['host'],'path':p['path'],'service':svc['name']})
            summary['ingresses'].append({'name':name,'paths':paths,'tls':spec.get('tls',[])})
        if obj['kind'] == 'PersistentVolumeClaim':
            assert obj['metadata']['annotations']['helm.sh/resource-policy'] == 'keep'
            summary['pvcs'].append({'name':name,'storageClassName':spec.get('storageClassName'),'storage':spec['resources']['requests']['storage']})
        if obj['kind'] == 'NetworkPolicy':
            assert any(selected(w['spec']['template']['metadata']['labels'],spec['podSelector']['matchLabels']) for w in workloads)
            summary['policies'].append({'name':name,'spec':spec})
        if obj['kind'] in {'Role','RoleBinding','ServiceAccount','Namespace'}: summary['rbac'].append(obj)
    assert {p['name'] for p in summary['pvcs']} == {release+'-'+s for s in ['mariadb-data','wordpress-content','platform-data']}
    ingress = by_kind[('Ingress',release+'-dashboard')]['spec']
    assert {p['path'] for p in ingress['rules'][0]['http']['paths']} == {'/','/api/v1','/mcp'}
    assert ingress['tls'][0]['secretName']
    assert {p['backend']['service']['name'] for p in ingress['rules'][0]['http']['paths']} == {release+'-backend',release+'-dashboard'}
    assert len(summary['ingresses']) == 2
    for component in ['woocommerce-mcp','inventory-mcp']:
        policy=by_kind[('NetworkPolicy',release+'-'+component)]['spec']
        caller=policy['ingress'][0]['from'][0]['podSelector']['matchLabels']
        backend=by_kind[('Deployment',release+'-backend')]['spec']['template']['metadata']['labels']
        assert selected(backend,caller) and caller['urumi.dev/gateway'] == 'true'
    dashboard=by_kind[('Deployment',release+'-dashboard')]['spec']['template']
    assert 'urumi.dev/gateway' not in dashboard['metadata']['labels']
    assert not any(e.get('valueFrom',{}).get('secretKeyRef') for c in dashboard['spec']['containers'] for e in c.get('env',[]))
    backend_config=by_kind[('ConfigMap',release+'-backend')]['data']
    internal=json.loads(backend_config['URUMI_INTERNAL_URLS'])
    assert internal == [f'http://{release}-{s}.{namespace}.svc.cluster.local:8000/mcp' for s in ['woocommerce-mcp','inventory-mcp']]
    assert json.loads(backend_config['URUMI_ALLOWED_HOSTS'])[:4] == [ingress['rules'][0]['host'],f'{release}-backend',f'{release}-backend.{namespace}.svc',f'{release}-backend.{namespace}.svc.cluster.local']
    secret_ns=backend_config['URUMI_SECRET_NAMESPACE']
    assert secret_ns != namespace
    ns=by_kind[('Namespace',secret_ns)];assert ns['metadata']['annotations']['helm.sh/resource-policy'] == 'keep'
    role=by_kind[('Role',release+'-upstream-secrets')]
    assert role['metadata']['namespace'] == secret_ns
    assert role['rules'] == [{'apiGroups':[''],'resources':['secrets'],'verbs':['get','create','update','delete']}]
    binding=by_kind[('RoleBinding',release+'-upstream-secrets')]
    assert binding['subjects'][0]['namespace'] == namespace
    assert not any(o['kind'] in {'ClusterRole','ClusterRoleBinding','Secret'} for o in objects)
    policies={o['metadata']['name']:o['spec'] for o in objects if o['kind']=='NetworkPolicy'}
    labels={w['spec']['template']['metadata']['labels']['app.kubernetes.io/component']:w['spec']['template']['metadata']['labels'] for w in workloads}
    backend_policy=policies[release+'-backend']
    ingress_peer=backend_policy['ingress'][0]['from'][0]
    ingress_ns=ingress_peer['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name']
    ingress_labels=ingress_peer['podSelector']['matchLabels']
    paths=[]
    def expect(name,direction,ns,pod,port,expected=True,protocol='TCP',address=None):
        actual=allows(policies[release+'-'+name],direction,ns,pod,port,protocol,address,namespace)
        assert actual is expected,(name,direction,ns,pod,port,address,expected)
        paths.append({'policy':name,'direction':direction,'peer_namespace':ns,'peer_labels':pod,'port':port,'protocol':protocol,'address':address,'allowed':actual})
    for name,port in [('backend',8000),('dashboard',8080),('wordpress',80)]:
        expect(name,'ingress',ingress_ns,ingress_labels,port)
        expect(name,'ingress',namespace,{'app.kubernetes.io/component':'arbitrary'},port,False)
    for name,port in [('platform-db',5432),('woocommerce-mcp',8000),('inventory-mcp',8000)]:
        expect('backend','egress',namespace,labels[name],port)
        expect(name,'ingress',namespace,labels['backend'],port)
        expect(name,'ingress',namespace,labels['dashboard'],port,False)
    expect('wordpress','egress',namespace,labels['mariadb'],3306)
    expect('store-database','ingress',namespace,labels['wordpress'],3306)
    for protocol in ['TCP','UDP']:
        expect('backend','egress','kube-system',{'k8s-app':'kube-dns'},53,protocol=protocol)
        expect('woocommerce-mcp','egress','kube-system',{'k8s-app':'kube-dns'},53,protocol=protocol)
    expect('backend','egress','',{},443,address='8.8.8.8')
    for ip in ['127.0.0.1','10.2.3.4','169.254.169.254','192.0.2.10','224.0.0.1']:
        expect('backend','egress','',{},443,False,address=ip)
    for rule in backend_policy['egress']:
        if rule.get('ports')==[{'protocol':'TCP','port':443}]:continue
        for peer in rule['to']:
            if 'ipBlock' in peer:
                net=ipaddress.ip_network(peer['ipBlock']['cidr']);assert net.prefixlen==net.max_prefixlen
                expect('backend','egress','',{},rule['ports'][0]['port'],address=str(net.network_address))
    woo_env={e['name']:e.get('value') for e in by_kind[('Deployment',release+'-woocommerce-mcp')]['spec']['template']['spec']['containers'][0]['env']}
    production=woo_env['WOO_CANONICAL_ORIGIN'].startswith('https://')
    if production:
        woo_policy=policies[release+'-woocommerce-mcp']
        tlsport=woo_policy['egress'][1]['ports'][0]['port']
        expect('woocommerce-mcp','egress',ingress_ns,ingress_labels,tlsport)
        expect('woocommerce-mcp','egress',namespace,labels['wordpress'],80,False)
        expect('wordpress','ingress',namespace,labels['woocommerce-mcp'],80,False)
        assert woo_env['WOO_TRANSPORT_ORIGIN']==woo_env['WOO_CANONICAL_ORIGIN']
    else:
        expect('woocommerce-mcp','egress',namespace,labels['wordpress'],80)
        expect('wordpress','ingress',namespace,labels['woocommerce-mcp'],80)
        assert woo_env['WOO_TRANSPORT_ORIGIN']==f'http://{release}-wordpress.{namespace}.svc.cluster.local'
    assert policies[release+'-dashboard']['egress']==[]
    assert policies[release+'-inventory-mcp']['egress']==[]
    summary['policy_paths']=paths
    return summary


DOCS = ['README.md','docs/operations.md','docs/system-design.md','docs/threat-model.md','docs/optional-items.md']


def inspect_docs(root):
    checked=[]
    for name in DOCS:
        path=root/name; text=path.read_text(encoding='utf-8')
        assert text.count('```') % 2 == 0, name
        for target in re.findall(r'\]\(([^)]+)\)',text):
            if '://' in target or target.startswith('#'): continue
            assert (path.parent/target.split('#')[0]).exists(), (name,target)
        checked.append(name)
    return checked
