import copy
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts.m9.package_checks import inspect_render
from scripts.m9.preflight import CHART, ROOT, load_values

HELM=os.environ.get('URUMI_HELM',str(ROOT/'.tools/m1/helm.exe'))


def render(profile,release='urumi',namespace='urumi',changes=None):
    args=[HELM,'template',release,str(CHART),'--namespace',namespace,'-f',str(CHART/('values-'+profile+'.yaml'))]
    for key,value in (changes or {}).items(): args.extend(['--set',key+'='+str(value)])
    return subprocess.run(args,text=True,capture_output=True,check=False)


@pytest.mark.parametrize('profile',['local','prod'])
@pytest.mark.parametrize('names',[('urumi','urumi'),('review','other-team')])
def test_complete_profile(profile,names):
    release,namespace=names
    result=render(profile,release,namespace)
    assert result.returncode == 0,result.stderr
    inventory=inspect_render(result.stdout,release,namespace)
    assert len(inventory['workloads']) == 7
    assert len(inventory['pvcs']) == 3


@pytest.mark.parametrize('changes,reason',[
 ({'backend.replicas':2},'BACKEND_SINGLE_OWNER_REQUIRED'),
 ({'backend.resources.requests.cpu':'not-a-quantity'},'does not match pattern'),
 ({'dashboard.resources.limits.memory':'infinite'},'does not match pattern'),
 ({'store.ingress.host':'wrong.test'},'SHOP_HOST_SCHEME_MISMATCH'),
 ({'backend.workers':2},'BACKEND_SINGLE_OWNER_REQUIRED'),
 ({'backend.replicas':'wrong'},'backend/replicas'),
 ({'m5Harness.enabled':'true'},'RELEASE_HARNESS_FORBIDDEN'),
 ({'gatewayCheck.enabled':'true'},'gatewayCheck is restricted'),
 ({'foundation.enabled':'true'},'RELEASE_HARNESS_FORBIDDEN'),
 ({'inventoryMcp.enabled':'false'},'RELEASE_COMPONENT_REQUIRED'),
 ({'backend.origin':'https://wrong.test'},'DASHBOARD_ORIGIN_MISMATCH'),
 ({'dashboard.ingress.tlsSecret':''},'DASHBOARD_TLS_REQUIRED'),
 ({'backend.image.digest':'wrong'},'does not match pattern'),
 ({'backend.image.repository':''},'minLength'),
 ({'backend.image.pullPolicy':'Sometimes'},'must be one of'),
 ({'backend.networkPolicy.apiServerPort':65536},'maximum'),
 ({'backend.resources.requests.cpu':''},'minLength'),
 ({'dashboard.ingress.host':''},'minLength'),
 ({'platformAccess.secretNamespace':'urumi'},'DEDICATED_SECRET_NAMESPACE_REQUIRED'),
 ({'backend.networkPolicy.enabled':'false'},'RELEASE_NETWORK_POLICIES_REQUIRED'),
])
def test_invalid_release_values(changes,reason):
    result=render('local',changes=changes)
    assert result.returncode != 0
    assert reason in result.stderr,result.stderr


def test_production_transport_rejects_insecure_override():
    result=render('prod',changes={'woocommerceMcp.transportOrigin':'http://shop.example.com'})
    assert result.returncode != 0 and 'PRODUCTION_WOO_TLS_REQUIRED' in result.stderr


@pytest.mark.parametrize('component,flag',[('woocommerce-mcp','woocommerceMcp'),('inventory-mcp','inventoryMcp')])
def test_standalone_caller_unchanged(component,flag):
    result=subprocess.run([HELM,'template','old',str(CHART),'--set',flag+'.enabled=true'],text=True,capture_output=True)
    assert result.returncode == 0,result.stderr
    objects=list(yaml.safe_load_all(result.stdout))
    policy=next(o for o in objects if o['kind']=='NetworkPolicy')
    caller=policy['spec']['ingress'][0]['from'][0]['podSelector']['matchLabels']
    assert caller == {'app.kubernetes.io/name':'urumi','app.kubernetes.io/instance':'old','app.kubernetes.io/component':'gateway'}


@pytest.mark.parametrize('mutation',['caller','pvc','ingress','config'])
def test_structural_checks_detect_broken_references(mutation):
    result=render('local');assert result.returncode==0
    objects=list(yaml.safe_load_all(result.stdout))
    if mutation=='caller':
        policy=next(o for o in objects if o['kind']=='NetworkPolicy' and o['metadata']['name']=='urumi-inventory-mcp');policy['spec']['ingress'][0]['from'][0]['podSelector']['matchLabels']['app.kubernetes.io/component']='gateway'
    elif mutation=='pvc':
        objects=[o for o in objects if o.get('kind')!='PersistentVolumeClaim' or o['metadata']['name']!='urumi-platform-data']
    elif mutation=='ingress':
        ingress=next(o for o in objects if o['kind']=='Ingress' and o['metadata']['name']=='urumi-dashboard');ingress['spec']['rules'][0]['http']['paths'][0]['backend']['service']['name']='missing'
    else:
        config=next(o for o in objects if o['kind']=='ConfigMap' and o['metadata']['name']=='urumi-backend');config['data']['URUMI_INTERNAL_URLS']='["http://wrong"]'
    with pytest.raises(AssertionError):inspect_render(yaml.safe_dump_all(objects))


def test_build_release_fail_closed_and_checks_compatible():
    text=(ROOT/'backend/Dockerfile').read_text()
    runtime,remaining=text.split('FROM runtime AS checks')
    checks,release=remaining.split('FROM runtime AS release')
    assert 'AS runtime' in runtime and 'COPY scripts/' not in runtime
    assert 'scripts.m5.harness' in checks and 'test -f /app/backend/main.py' in release
    assert 'COPY scripts/' not in release and 'scripts.m5.harness' not in release
    assert 'test -f /app/backend/orchestrator.py' in release and 'backend.main' in release
    script=(ROOT/'scripts/build-images.ps1').read_text()
    assert script.index('M10_BACKEND_ENTRYPOINT_MISSING') < script.index('& docker')
    assert "{ 'frontend' } else { '.' }" in script
    for name in ['m5','m6']:
        assert 'docker build --target checks' in (ROOT/f'docs/evidence/{name}/runbook.md').read_text()


@pytest.mark.parametrize('profile',['local','prod'])
def test_legacy_module_profiles_remain_opt_in(profile):
    result=subprocess.run([HELM,'template','urumi',str(CHART),'-f',str(CHART/f'values-module-{profile}.yaml')],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    assert not list(yaml.safe_load_all(result.stdout))
    if profile=='local':
        result=subprocess.run([HELM,'template','urumi',str(CHART),'-f',str(CHART/'values-module-local.yaml'),'-f',str(CHART/'values-m1.yaml')],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        workloads=[o for o in yaml.safe_load_all(result.stdout) if o and o['kind']=='Deployment']
        assert len(workloads)==1 and workloads[0]['metadata']['name']=='urumi-foundation'
