"""Validate examples separately from operator deployment readiness; never call Kubernetes."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[2]
CHART = ROOT / "deploy/charts/urumi"


def merge(base, overrides):
    result = dict(base)
    for key, value in overrides.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
    return result


def load_values(path):
    return merge(yaml.safe_load((CHART / "values.yaml").read_text()), yaml.safe_load(Path(path).read_text()))


def required_secrets(v):
    """Names, types and keys only. Values are deliberately outside this contract."""
    entries = [
        (v['store']['secrets']['database'], 'Opaque', ['database-password', 'root-password']),
        (v['store']['secrets']['salts'], 'Opaque', ['AUTH_KEY','SECURE_AUTH_KEY','LOGGED_IN_KEY','NONCE_KEY','AUTH_SALT','SECURE_AUTH_SALT','LOGGED_IN_SALT','NONCE_SALT']),
        (v['store']['secrets']['admin'], 'Opaque', ['username','email','password']),
        (v['woocommerceMcp']['existingSecret'], 'Opaque', ['consumer-key','consumer-secret']),
        (v['platformDb']['existingSecret'], 'Opaque', ['password']),
        (v['backend']['existingProviderSecret'], 'Opaque', ['api-key']),
        (v['dashboard']['ingress']['tlsSecret'], 'kubernetes.io/tls', ['tls.crt','tls.key']),
    ]
    if v['store']['ingress'].get('tlsSecret'):
        entries.append((v['store']['ingress']['tlsSecret'],'kubernetes.io/tls',['tls.crt','tls.key']))
    entries += [(s['name'],'kubernetes.io/dockerconfigjson',['.dockerconfigjson']) for s in v['imagePullSecrets']]
    return [{'name':n,'type':t,'keys':k} for n,t,k in entries]


def validate(v, mode='render', inventory=None, root=ROOT, namespace='urumi'):
    errors = []
    try:
        jsonschema.validate(v, json.loads((CHART / 'values.schema.json').read_text()))
    except jsonschema.ValidationError as exc:
        return ['VALUES_SCHEMA:' + '.'.join(map(str, exc.absolute_path))]
    if not v['release']['enabled']:
        return ['RELEASE_REQUIRED']
    for name in ['store','woocommerceMcp','inventoryMcp','platformDb','platformAccess','backend','dashboard']:
        if not v[name]['enabled']: errors.append('RELEASE_COMPONENT_REQUIRED:' + name)
    if any(v[name]['enabled'] for name in ['foundation','m5Harness','gatewayCheck']) or v.get('dashboardCheck',{}).get('enabled'):
        errors.append('RELEASE_HARNESS_FORBIDDEN')
    if v['backend']['replicas'] != 1 or v['backend']['workers'] != 1: errors.append('BACKEND_SINGLE_OWNER_REQUIRED')
    if v['backend']['origin'] != 'https://' + v['dashboard']['ingress']['host']: errors.append('DASHBOARD_ORIGIN_MISMATCH')
    if not v['dashboard']['ingress']['tlsSecret']: errors.append('DASHBOARD_TLS_REQUIRED')
    if v['store']['canonicalUrl'] != v['woocommerceMcp']['canonicalOrigin']: errors.append('SHOP_ORIGIN_MISMATCH')
    if urlsplit(v['store']['canonicalUrl']).hostname != v['store']['ingress']['host']: errors.append('SHOP_HOST_MISMATCH')
    if v['platformAccess']['secretNamespace'] in {namespace,'default','kube-system','kube-public','kube-node-lease'}: errors.append('DEDICATED_SECRET_NAMESPACE_REQUIRED')
    for name in ['backend','store','woocommerceMcp','inventoryMcp']:
        if not v[name]['networkPolicy']['enabled']: errors.append('RELEASE_NETWORK_POLICIES_REQUIRED:' + name)
    production = v['release']['environment'] == 'production'
    if v['store']['canonicalUrl'] != ('https://' if production else 'http://') + v['store']['ingress']['host']: errors.append('SHOP_HOST_SCHEME_MISMATCH')
    if production:
        if not (v['store']['canonicalUrl'].startswith('https://') and v['woocommerceMcp']['transportOrigin'] == v['store']['canonicalUrl'] and v['woocommerceMcp']['networkPolicy']['transportMode'] == 'ingress-https' and v['store']['ingress']['tlsSecret']): errors.append('PRODUCTION_WOO_TLS_REQUIRED')
        host = urlsplit(v['store']['canonicalUrl']).hostname
        aliases = v['woocommerceMcp']['hostAliases']
        try:
            if len(aliases) != 1 or aliases[0]['hostnames'] != [host]: raise ValueError()
            ipaddress.ip_address(aliases[0]['ip'])
        except (ValueError, KeyError, TypeError): errors.append('WOO_HOST_ALIAS_REQUIRED')
    elif v['woocommerceMcp']['networkPolicy']['transportMode'] != 'direct-http': errors.append('LOCAL_WOO_TRANSPORT_REQUIRED')
    try:
        for cidr in v['backend']['networkPolicy']['apiServerCidrs']:
            network = ipaddress.ip_network(cidr, strict=True)
            if network.prefixlen != network.max_prefixlen: raise ValueError()
    except ValueError: errors.append('API_ENDPOINT_HOST_CIDR_REQUIRED')
    if mode == 'render': return errors
    text = json.dumps(v)
    if any(token in text for token in ['example.com','replace-','m10-unavailable','192.0.2.']): errors.append('DEPLOY_PLACEHOLDERS_UNRESOLVED')
    if not all((root / 'backend' / name).is_file() for name in ['main.py','orchestrator.py']): errors.append('M10_BACKEND_ENTRYPOINT_MISSING')
    if not v['release']['provenance']: errors.append('RELEASE_PROVENANCE_REQUIRED')
    for name in ['store','woocommerceMcp','inventoryMcp','backend','dashboard']:
        if not v[name]['image']['digest']: errors.append('IMAGE_DIGEST_REQUIRED:' + name)
    if not all(re.fullmatch(r'[a-z0-9./:_-]+@sha256:[a-f0-9]{64}', image) for image in [v['store']['databaseImage'],v['platformDb']['image']]): errors.append('DATABASE_IMAGE_DIGEST_REQUIRED')
    if not v['backend']['networkPolicy']['apiServerCidrs']: errors.append('API_ENDPOINT_CIDRS_REQUIRED')
    if not inventory: return errors + ['NAMES_ONLY_INVENTORY_REQUIRED']
    if not isinstance(inventory,dict): return errors + ['INVENTORY_OBJECT_REQUIRED']
    allowed = {'secrets','certificates','storageClasses','ingress','apiServerCidrs','runtimeImageVerified','wooProxyVerified'}
    if set(inventory) - allowed: errors.append('INVENTORY_UNKNOWN_FIELDS')
    supplied = inventory.get('secrets', [])
    if not isinstance(supplied,list) or any(not isinstance(s,dict) or set(s) != {'name','type','keys'} or not isinstance(s.get('name'),str) or not isinstance(s.get('type'),str) or not isinstance(s.get('keys'),list) or not all(isinstance(k,str) for k in s['keys']) for s in supplied):
        return errors + ['INVENTORY_SECRET_VALUES_FORBIDDEN']
    if not isinstance(inventory.get('ingress',{}),dict): return errors + ['INVENTORY_INGRESS_OBJECT_REQUIRED']
    for name in ['certificates','storageClasses','apiServerCidrs']:
        if not isinstance(inventory.get(name,[]),list): return errors + ['INVENTORY_LIST_REQUIRED:' + name]
    for entry in required_secrets(v):
        if not any(s['name']==entry['name'] and s['type']==entry['type'] and set(s['keys'])==set(entry['keys']) for s in supplied): errors.append('SECRET_METADATA_REQUIRED:' + entry['name'])
    for group in ['store','platformDb']:
        if not v[group]['storage']['className'] or v[group]['storage']['className'] not in inventory.get('storageClasses',[]): errors.append('STORAGE_CLASS_VERIFICATION_REQUIRED:' + group)
    for host in [v['dashboard']['ingress']['host']] + ([v['store']['ingress']['host']] if production else []):
        if {'host':host,'trusted':True} not in inventory.get('certificates',[]): errors.append('TLS_HOST_TRUST_REQUIRED:' + host)
    expected = {'namespace':v['networking']['ingressNamespace'],'podLabels':v['networking']['ingressPodLabels'],'tlsTargetPort':v['networking']['ingressTlsTargetPort']}
    ingress = inventory.get('ingress',{})
    if any(ingress.get(k) != val for k,val in expected.items()): errors.append('INGRESS_ENDPOINT_VERIFICATION_REQUIRED')
    aliases=v['woocommerceMcp']['hostAliases']
    alias_ip=aliases[0].get('ip') if aliases and isinstance(aliases[0],dict) else None
    if production and (inventory.get('wooProxyVerified') is not True or not alias_ip or ingress.get('serviceIP') != alias_ip): errors.append('WOO_PROXY_VERIFICATION_REQUIRED')
    if inventory.get('apiServerCidrs') != v['backend']['networkPolicy']['apiServerCidrs']: errors.append('API_ENDPOINT_VERIFICATION_REQUIRED')
    if inventory.get('runtimeImageVerified') is not True: errors.append('M10_RUNTIME_IMAGE_VERIFICATION_REQUIRED')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['render','deploy'], required=True)
    parser.add_argument('--values', type=Path, required=True)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--namespace', default='urumi')
    args = parser.parse_args()
    try:
        errors = validate(load_values(args.values),args.mode,json.loads(args.inventory.read_text()) if args.inventory else None,namespace=args.namespace)
    except (ValueError, TypeError, KeyError) as exc:
        errors = ['INVALID_INPUT:' + type(exc).__name__]
    print(json.dumps({'mode':args.mode,'status':'FAIL' if errors else 'PASS','errors':errors,'scope':'metadata only; no cluster calls'},indent=2))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
