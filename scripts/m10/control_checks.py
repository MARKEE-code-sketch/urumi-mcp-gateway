"""Explicit revocation, disabling and owned Inventory-only failure checks."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import subprocess
import sys

import httpx
from mcp import McpError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.live_checks import (Browser, CheckFailed, gateway, origin_value, require,
                                     result_data, tls_context, wait_tools)

NS = 'urumi-m10'
DEPLOY = 'urumi-m10-inventory-mcp'
LABELS = {'app.kubernetes.io/instance': NS, 'app.kubernetes.io/component': 'inventory-mcp'}


def safe_failure(error):
    """Only fixed check labels and exception class names, including task groups."""
    pending, labels, classes = [error], [], set()
    while pending:
        item = pending.pop()
        classes.add(type(item).__name__)
        if isinstance(item, BaseExceptionGroup):
            pending.extend(item.exceptions)
        elif isinstance(item, CheckFailed):
            labels.append(str(item))
    return {'exception_types': sorted(classes), 'failed_checks': sorted(set(labels))}


class OwnedInventory:
    def __init__(self, config):
        require(config.get('namespace', NS) == NS and config.get('release', NS) == NS,
                'exact_target_required')
        kubeconfig = Path(config.get('kubeconfig', ROOT / '.tools/m1/kubeconfig.yaml')).resolve()
        require(kubeconfig.is_file(), 'kubeconfig_required')
        require(config.get('context', 'k3d-urumi') == 'k3d-urumi', 'exact_context_required')
        self.command = ['kubectl', '--context', 'k3d-urumi', '--kubeconfig', str(kubeconfig)]
        self.namespace_uid = None

    async def kubectl(self, args, input_document=None):
        completed = await asyncio.to_thread(subprocess.run, self.command + args,
            input=json.dumps(input_document) if input_document is not None else None,
            capture_output=True, text=True, timeout=35)
        require(completed.returncode == 0, 'scoped_kubectl_failed')
        return json.loads(completed.stdout)

    async def guard(self):
        ns = await self.kubectl(['get', 'namespace', NS, '-o', 'json'])
        require(ns['metadata'].get('labels', {}).get('urumi.dev/module') == 'm10', 'namespace_ownership')
        uid = ns['metadata']['uid']
        require(self.namespace_uid in (None, uid), 'namespace_uid_changed')
        self.namespace_uid = uid
        return uid

    def owned(self, item):
        meta = item['metadata']
        require(meta.get('namespace') == NS and all(meta.get('labels', {}).get(k) == v
                for k, v in LABELS.items()), 'inventory_ownership')
        return item

    async def deployment(self):
        await self.guard()
        item = await self.kubectl(['-n', NS, 'get', 'deployment', DEPLOY, '-o', 'json'])
        meta = item['metadata']
        annotations = meta.get('annotations', {})
        labels = item['spec']['template']['metadata'].get('labels', {})
        require(meta.get('namespace') == NS and meta['name'] == DEPLOY
            and annotations.get('meta.helm.sh/release-name') == NS
            and annotations.get('meta.helm.sh/release-namespace') == NS
            and all(labels.get(k) == v for k, v in LABELS.items()), 'inventory_deployment_ownership')
        return item

    async def pods(self):
        await self.guard()
        data = await self.kubectl(['-n', NS, 'get', 'pods', '-l',
            ','.join(k + '=' + v for k, v in LABELS.items()), '-o', 'json'])
        return [self.owned(item) for item in data['items']]

    async def delete_pod(self, pod):
        await self.guard()
        self.owned(pod)
        name, uid = pod['metadata']['name'], pod['metadata']['uid']
        require(re.fullmatch(r'urumi-m10-inventory-mcp-[a-z0-9-]+', name), 'inventory_pod_name')
        await self.kubectl(['delete', '--raw', f'/api/v1/namespaces/{NS}/pods/{name}', '-f', '-'],
            {'apiVersion': 'v1', 'kind': 'DeleteOptions', 'gracePeriodSeconds': 0,
             'preconditions': {'uid': uid}})
        return {'name': name, 'uid': uid, 'atomic_uid_precondition': True}

    async def scale(self, replicas):
        deployment = await self.deployment()
        meta = deployment['metadata']
        patch = [{'op': 'test', 'path': '/metadata/uid', 'value': meta['uid']},
            {'op': 'test', 'path': '/metadata/resourceVersion', 'value': meta['resourceVersion']},
            {'op': 'test', 'path': '/spec/replicas', 'value': deployment['spec']['replicas']},
            {'op': 'replace', 'path': '/spec/replicas', 'value': replicas}]
        await self.kubectl(['-n', NS, 'patch', 'deployment', DEPLOY, '--type=json',
                            '-p', json.dumps(patch), '-o', 'json'])


async def server_state(browser, server_id, wanted, timeout=50):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        state = await browser.request('GET', '/api/v1/servers/' + server_id)
        if state['status'] == wanted:
            return {'id': state['id'], 'status': state['status'],
                    'status_reason': state['status_reason'], 'last_checked_at': state['last_checked_at']}
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(1)


async def healthy_peers(session):
    result_data(await session.call_tool('woocommerce__list_products', {'per_page': 1}))
    tools = (await session.list_tools()).tools
    searches = [tool for tool in tools if tool.name.startswith('learn__') and
        'search' in tool.name.lower() and tool.inputSchema.get('properties', {}).get('query', {}).get('type') == 'string'
        and set(tool.inputSchema.get('required', [])) <= {'query'}]
    require(bool(searches), 'learn_search_schema')
    result = await session.call_tool(searches[0].name, {'query': 'Kubernetes readiness probes'})
    require(not result.isError and bool(result.content), 'learn_healthy')
    return {'woocommerce': 'PASS', 'learn': 'PASS'}


async def run_control_checks(config, *, run_owned_demo=False):
    require(run_owned_demo is True, 'explicit_mutation_flag_required')
    origin, context = origin_value(config['origin']), tls_context(config['ca_path'])
    kube = OwnedInventory(config)
    admin, member = Browser(origin, context), Browser(origin, context)
    evidence = {'status': 'FAIL', 'checked_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Owned keys and Inventory-only controls; no browser/chat planner claim.',
        'checks': [], 'cleanup': {}, 'namespace': NS}
    keys, inventory, original_replicas = [], None, None
    disabled, scaled = False, False
    stage = 'login'
    try:
        await admin.login(config['admin_email'], config['admin_password'])
        await member.login(config['member_email'], config['member_password'])
        require(admin.user['role'] == 'admin' and member.user['role'] == 'member', 'roles')
        stage = 'issue_owned_keys'
        for browser, label in [(member, 'M10 selected revocation check'), (admin, 'M10 control check')]:
            user_id = browser.user['id']
            key = await browser.request('POST', f'/api/v1/members/{user_id}/keys', {'label': label}, 201)
            keys.append((browser, user_id, key))
        member_key, admin_key = keys[0][2], keys[1][2]
        evidence['ids'] = {'member_user_id': member.user['id'], 'admin_user_id': admin.user['id'],
                          'selected_key_id': member_key['id'], 'control_key_id': admin_key['id']}
        servers = (await admin.request('GET', '/api/v1/servers?per_page=50'))['items']
        inventory = next(item for item in servers if item['slug'] == 'inventory')
        require(inventory['enabled'] and inventory['url'] == config['inventory_url'], 'inventory_target')
        stage = 'selected_session_discovery'
        rejected = False
        try:
            async with gateway(origin, context, member_key['raw_key']) as selected:
                await wait_tools(selected, ['woocommerce', 'inventory', 'learn'])
                result_data(await selected.call_tool('woocommerce__list_products', {'per_page': 1}))
                stage = 'revoke_selected_key'
                await member.request('DELETE', f"/api/v1/members/{member.user['id']}/keys/{member_key['id']}", expected=204)
                stage = 'open_session_next_call'
                try:
                    reply = await selected.call_tool('woocommerce__list_products', {'per_page': 1})
                    rejected = reply.isError is True
                except Exception:
                    rejected = True
                require(rejected, 'open_session_revocation')
                stage = 'revoked_session_context_exit'
        except Exception as error:
            # The SDK transport task group also raises on context exit after its
            # POST receives HTTP401. The independent raw check below must still
            # prove KEY_REVOKED; earlier discovery/execution errors are not ignored.
            def revoked_http_failure(item):
                return ((isinstance(item, httpx.HTTPStatusError) and item.response.status_code == 401)
                        or any(revoked_http_failure(child) for child in getattr(item, 'exceptions', ())))
            if stage == 'open_session_next_call' and revoked_http_failure(error):
                rejected = True
            elif not (rejected and stage == 'revoked_session_context_exit'):
                raise
            evidence['revoked_session_transport_exit'] = safe_failure(error)
        stage = 'raw_revoked_key_check'
        response = await member.client.post('/mcp', json={'jsonrpc': '2.0', 'id': 101,
            'method': 'tools/call', 'params': {'name': 'woocommerce__list_products', 'arguments': {'per_page': 1}}},
            headers={'Authorization': 'Bearer ' + member_key['raw_key'],
                     'Accept': 'application/json, text/event-stream'})
        require(response.status_code == 401 and response.json()['error']['code'] == 'KEY_REVOKED', 'raw_revocation')
        stage = 'independent_control_key'
        async with gateway(origin, context, admin_key['raw_key']) as control:
            result_data(await control.call_tool('woocommerce__list_products', {'per_page': 1}))
            evidence['checks'].append({'check': 'selected_key_revocation', 'status': 'PASS',
                'open_session_next_call_rejected': True, 'raw_http_status': 401, 'control_key_works': True})
            stage = 'disable_inventory'
            disabled = True
            await admin.request('PATCH', '/api/v1/servers/' + inventory['id'], {'enabled': False})
            names = [tool.name for tool in (await control.list_tools()).tools]
            require(not any(name.startswith('inventory__') for name in names), 'disabled_gateway_discovery')
            preview = await member.request('GET', '/api/v1/servers/' + inventory['id'] + '/tools')
            require(preview['items'] == [], 'disabled_session_preview')
            stale_rejected = False
            try:
                await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'})
            except McpError as error:
                stale_rejected = error.error.code == -32602
            require(stale_rejected, 'disabled_stale_name_invalid_params')
            evidence['checks'].append({'check': 'server_disable', 'status': 'PASS',
                'gateway_absent': True, 'member_preview_empty': True, 'stale_name_invalid_params': True,
                'healthy_peers': await healthy_peers(control)})
            await admin.request('PATCH', '/api/v1/servers/' + inventory['id'], {'enabled': True})
            disabled = False
            await wait_tools(control, ['woocommerce', 'inventory', 'learn'])
            result_data(await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
            stage = 'inventory_pod_failure'
            deployment = await kube.deployment()
            original_replicas = deployment['spec']['replicas']
            require(original_replicas == 1, 'single_inventory_replica_required')
            pods = await kube.pods()
            require(len(pods) == 1, 'single_inventory_pod_required')
            deleted = await kube.delete_pod(pods[0])
            observed = await server_state(admin, inventory['id'], 'Unreachable', timeout=10)
            method = 'pod_delete'
            failed_call = False
            if observed is not None:
                result = await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'})
                failed_call = result.isError is True
            if observed is None or not failed_call:
                scaled = True
                await kube.scale(0)
                method = 'pod_delete_then_scale_zero'
                deadline = asyncio.get_running_loop().time() + 40
                while await kube.pods():
                    require(asyncio.get_running_loop().time() < deadline, 'scale_down_deadline')
                    await asyncio.sleep(1)
                observed = await server_state(admin, inventory['id'], 'Unreachable')
                result = await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'})
                failed_call = result.isError is True
            require(observed is not None, 'unreachable_status_observed')
            require(failed_call, 'failed_inventory_call_required')
            evidence['checks'].append({'check': 'inventory_failure_isolation', 'status': 'PASS',
                'deleted_pod': deleted, 'method': method, 'observed': observed,
                'failed_inventory_call': True, 'healthy_peers': await healthy_peers(control)})
            if scaled:
                await kube.scale(original_replicas)
                scaled = False
            stage = 'inventory_recovery'
            recovered = await server_state(admin, inventory['id'], 'Connected', timeout=70)
            require(recovered is not None, 'inventory_recovery_status')
            result_data(await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
            replacement = await kube.pods()
            require(bool(replacement) and all(p['metadata']['uid'] != deleted['uid'] for p in replacement), 'replacement_pod_uid')
            evidence['checks'].append({'check': 'inventory_recovery', 'status': 'PASS',
                'observed': recovered, 'replacement_uids': [p['metadata']['uid'] for p in replacement]})
        stage = 'audit_attribution'
        records = (await admin.request('GET', '/api/v1/audit?per_page=50'))['items']
        ids = {member_key['id'], admin_key['id']}
        evidence['audit'] = [{field: row[field] for field in
            ('audit_id', 'user_id', 'key_id', 'auth_source', 'public_tool_name', 'outcome', 'error_code')}
            for row in records if row['key_id'] in ids]
        require(any(row['key_id'] == member_key['id'] and row['error_code'] == 'KEY_REVOKED'
                    for row in evidence['audit']), 'revocation_audit')
        evidence['status'] = 'PASS_CONTROLS_ONLY'
    except Exception as error:
        evidence['failure'] = 'A scoped control check failed; raw request/response diagnostics intentionally omitted.'
        evidence['failure_stage'] = stage
        evidence.update(safe_failure(error))
        if evidence['failed_checks']:
            evidence['failure_check'] = evidence['failed_checks'][0]
    finally:
        if scaled and original_replicas is not None:
            try:
                await kube.scale(original_replicas)
                evidence['cleanup']['replicas_restored'] = True
            except Exception:
                evidence['cleanup']['replicas_restored'] = False
        if inventory is not None:
            try:
                if disabled:
                    await admin.request('PATCH', '/api/v1/servers/' + inventory['id'], {'enabled': True})
                current = await admin.request('GET', '/api/v1/servers/' + inventory['id'])
                evidence['cleanup']['server_enabled'] = current['enabled'] is True
            except Exception:
                evidence['cleanup']['server_enabled'] = False
        if original_replicas is not None:
            try:
                deployment = await kube.deployment()
                evidence['cleanup']['original_replicas'] = original_replicas
                evidence['cleanup']['final_replicas'] = deployment['spec']['replicas']
                evidence['cleanup']['replicas_restored'] = deployment['spec']['replicas'] == original_replicas
                deadline = asyncio.get_running_loop().time() + 40
                while deployment.get('status', {}).get('readyReplicas', 0) < original_replicas:
                    if asyncio.get_running_loop().time() >= deadline:
                        break
                    await asyncio.sleep(1)
                    deployment = await kube.deployment()
                evidence['cleanup']['inventory_ready'] = deployment.get('status', {}).get('readyReplicas', 0) >= original_replicas
            except Exception:
                evidence['cleanup']['replicas_restored'] = False
        for browser, user_id, key in keys:
            try:
                await browser.request('DELETE', f"/api/v1/members/{user_id}/keys/{key['id']}", expected=204)
                evidence['cleanup'][key['id']] = 'REVOKED'
            except Exception:
                evidence['cleanup'][key['id']] = 'CLEANUP_FAILED'
        await member.close()
        await admin.close()
        if any(value is False or value == 'CLEANUP_FAILED' for value in evidence['cleanup'].values()):
            evidence['status'] = 'FAIL'
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--run-owned-demo', action='store_true')
    args = parser.parse_args()
    if not args.run_owned_demo:
        parser.error('--run-owned-demo is required for the owned failure checks.')
    if not args.private_config.resolve().is_relative_to(ROOT / '.tools'):
        parser.error('Private config must stay under ignored .tools.')
    if not args.output.resolve().is_relative_to(ROOT / 'docs/evidence/m10'):
        parser.error('Evidence output must stay under docs/evidence/m10.')
    logging.disable(logging.CRITICAL)
    try:
        config = json.loads(args.private_config.read_text(encoding='utf-8-sig'))
        evidence = asyncio.run(run_control_checks(config, run_owned_demo=True))
    except Exception:
        evidence = {'status': 'FAIL', 'failure': 'Configuration or pre-check initialization failed.', 'cleanup': {}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(evidence['status'])
    return 0 if evidence['status'] == 'PASS_CONTROLS_ONLY' else 1


if __name__ == '__main__':
    raise SystemExit(main())
