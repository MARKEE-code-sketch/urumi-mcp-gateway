import copy
from pathlib import Path
import pytest
from scripts.m9.preflight import CHART,load_values,required_secrets,validate


@pytest.mark.parametrize('profile',['local','prod'])
def test_examples_render_but_fail_deploy(profile,tmp_path):
    values=load_values(CHART/f'values-{profile}.yaml')
    assert validate(values)==[]
    errors=validate(values,'deploy',root=tmp_path)
    assert 'M10_BACKEND_ENTRYPOINT_MISSING' in errors
    assert 'IMAGE_DIGEST_REQUIRED:backend' in errors
    assert 'NAMES_ONLY_INVENTORY_REQUIRED' in errors


@pytest.fixture
def ready(tmp_path):
    values=load_values(CHART/'values-prod.yaml')
    for name in ['store','woocommerceMcp','inventoryMcp','backend','dashboard']:
        values[name]['image'].update(repository='registry.acme.test/'+{'woocommerceMcp':'woocommerce-mcp','inventoryMcp':'inventory-mcp'}.get(name,name),tag='release1',digest='sha256:'+'a'*64)
    values['store'].update(canonicalUrl='https://shop.acme.test',databaseImage='mariadb@sha256:'+'b'*64)
    values['store']['ingress']['host']='shop.acme.test'
    values['woocommerceMcp'].update(canonicalOrigin='https://shop.acme.test',transportOrigin='https://shop.acme.test',hostAliases=[{'ip':'10.43.0.50','hostnames':['shop.acme.test']}])
    values['dashboard']['ingress']['host']='dashboard.acme.test';values['backend']['origin']='https://dashboard.acme.test'
    values['backend']['networkPolicy']['apiServerCidrs']=['10.0.0.5/32'];values['release']['provenance']='fixture-only-version'
    inventory={'secrets':required_secrets(values),'certificates':[{'host':h,'trusted':True} for h in ['shop.acme.test','dashboard.acme.test']], 'storageClasses':['local-path'],'ingress':{'namespace':'kube-system','podLabels':values['networking']['ingressPodLabels'],'tlsTargetPort':8443,'serviceIP':'10.43.0.50'},'apiServerCidrs':['10.0.0.5/32'],'runtimeImageVerified':True,'wooProxyVerified':True}
    (tmp_path/'backend').mkdir();[(tmp_path/'backend'/name).write_text('# fixture only') for name in ['main.py','orchestrator.py']]
    return values,inventory,tmp_path


def test_operator_metadata_fixture_passes(ready):
    v,i,r=ready
    assert validate(v,'deploy',i,r)==[]


@pytest.mark.parametrize('field,reason',[
 ('secret_value','INVENTORY_SECRET_VALUES_FORBIDDEN'),
 ('missing_secret','SECRET_METADATA_REQUIRED'),
 ('certificate','TLS_HOST_TRUST_REQUIRED'),
 ('storage','STORAGE_CLASS_VERIFICATION_REQUIRED'),
 ('proxy','WOO_PROXY_VERIFICATION_REQUIRED'),
 ('api','API_ENDPOINT_VERIFICATION_REQUIRED'),
 ('image','M10_RUNTIME_IMAGE_VERIFICATION_REQUIRED'),
 ('ingress','INGRESS_ENDPOINT_VERIFICATION_REQUIRED'),
 ('unknown','INVENTORY_UNKNOWN_FIELDS'),
])
def test_inventory_negatives(ready,field,reason):
    v,i,r=ready
    if field=='secret_value':i['secrets'][0]['data']={'password':'NOT-A-CREDENTIAL'}
    elif field=='missing_secret':i['secrets']=[]
    elif field=='certificate':i['certificates']=[]
    elif field=='storage':i['storageClasses']=[]
    elif field=='proxy':i['wooProxyVerified']=False
    elif field=='api':i['apiServerCidrs']=[]
    elif field=='image':i['runtimeImageVerified']=False
    elif field=='ingress':i['ingress']['tlsTargetPort']=443
    else:i['unexpected']='bad'
    assert any(e.startswith(reason) for e in validate(v,'deploy',i,r))


@pytest.mark.parametrize('cidr',['0.0.0.0/0','10.0.0.0/8','not-an-ip'])
def test_api_endpoint_cannot_allow_entire_network(cidr):
    v=load_values(CHART/'values-local.yaml');v['backend']['networkPolicy']['apiServerCidrs']=[cidr]
    assert 'API_ENDPOINT_HOST_CIDR_REQUIRED' in validate(v)


@pytest.mark.parametrize('bad',[None,[],{'secrets':[None]},{'secrets':[],'ingress':[]}])
def test_malformed_inventory_fails_safely(ready,bad):
    v,i,r=ready
    assert validate(v,'deploy',bad,r)


def test_empty_production_alias_fails_safely(ready):
    v,i,r=ready;v['woocommerceMcp']['hostAliases']=[]
    assert 'WOO_HOST_ALIAS_REQUIRED' in validate(v,'deploy',i,r)


def test_bad_database_digest_rejected(ready):
    v,i,r=ready;v['store']['databaseImage']='mariadb@sha256:garbage'
    assert 'DATABASE_IMAGE_DIGEST_REQUIRED' in validate(v,'deploy',i,r)


@pytest.mark.parametrize('repository',['registry.test/UpperCase','https://registry.test/backend','registry.test/with space'])
def test_invalid_repository_names(repository):
    v=load_values(CHART/'values-local.yaml');v['backend']['image']['repository']=repository
    assert validate(v)[0].startswith('VALUES_SCHEMA:')


def test_proxy_confirmation_requires_boolean_true(ready):
    v,i,r=ready;i['wooProxyVerified']='false'
    assert 'WOO_PROXY_VERIFICATION_REQUIRED' in validate(v,'deploy',i,r)
