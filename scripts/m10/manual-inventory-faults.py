"""User-authorized F4/F5: owned Inventory Pod loss and temporary scale-to-zero."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.control_checks import OwnedInventory, server_state
from scripts.m10.live_checks import Browser, gateway, result_data, require, tls_context

NS = 'urumi-m10'
OUT = ROOT / 'docs/evidence/manual-faults' / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
logging.disable(logging.CRITICAL)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def ready(pod):
    return not pod['metadata'].get('deletionTimestamp') and any(
        c['type'] == 'Ready' and c['status'] == 'True' for c in pod['status'].get('conditions', []))


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    config = {'namespace': NS, 'release': NS, 'context': 'k3d-urumi'}
    kube = OwnedInventory(config)
    context = tls_context(ROOT / '.tools/operator/m10/tls/ca.pem')
    private = json.loads((ROOT / '.tools/operator/m10/access.json').read_text())
    credential = json.loads((ROOT / '.tools/operator/m10/external-key.json').read_text())
    key_id = credential['raw_key'].split('_', 2)[1]
    admin = Browser('https://dashboard-m10.urumi.test', context)
    evidence = {'checked_at': datetime.now(timezone.utc).isoformat(), 'namespace': NS,
                'context': 'k3d-urumi', 'F4': 'Not run', 'F5': 'Not run', 'calls': [],
                'provider_calls': 0, 'shop_write_calls': 0,
                'coverage': 'Real Kubernetes controls and external MCP tool equivalents of Q1/Q7; no new chat planner claim.'}
    original = None
    scaled = False
    used_audits = set()

    def save():
        (OUT / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')

    async def snapshot():
        items = (await kube.kubectl(['-n', NS, 'get', 'deployments,statefulsets,pods,pvc', '-o', 'json']))['items']
        return {'namespace_uid': await kube.guard(),
            'workloads': sorted([{'name': x['metadata']['name'], 'uid': x['metadata']['uid'],
                'spec_sha256': digest(x['spec']), 'replicas': x['spec'].get('replicas', 1),
                'ready': x['status'].get('readyReplicas', 0)} for x in items
                if x['kind'] in ['Deployment', 'StatefulSet']], key=lambda x: x['name']),
            'pods': sorted([{'name': x['metadata']['name'], 'uid': x['metadata']['uid'],
                'component': x['metadata']['labels']['app.kubernetes.io/component'], 'ready': ready(x)}
                for x in items if x['kind'] == 'Pod' and not x['metadata'].get('deletionTimestamp')], key=lambda x: x['name']),
            'claims': sorted([{'name': x['metadata']['name'], 'uid': x['metadata']['uid'], 'phase': x['status']['phase']}
                for x in items if x['kind'] == 'PersistentVolumeClaim'], key=lambda x: x['name'])}

    async def wait_pod_ready(old_uid=None, timeout=90):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pods = await kube.pods()
            candidates = [p for p in pods if ready(p) and (old_uid is None or p['metadata']['uid'] != old_uid)]
            if candidates:
                deployment = await kube.deployment()
                if deployment['spec']['replicas'] > 0 and deployment.get('status', {}).get('readyReplicas', 0) >= deployment['spec']['replicas']:
                    return {'name': candidates[0]['metadata']['name'], 'uid': candidates[0]['metadata']['uid'], 'ready': True}
            await asyncio.sleep(.5)
        raise RuntimeError('Inventory replacement readiness deadline exceeded')

    async def call(session, stage, name, args):
        started = datetime.now(timezone.utc).isoformat()
        reply = await session.call_tool(name, args)
        if reply.isError:
            texts = [block.text for block in reply.content if block.type == 'text']
            payload = json.loads(texts[0]) if texts else {}
            result = {'is_error': True, 'error_code': payload.get('error', {}).get('code')}
        else:
            result = {'is_error': False, 'data': result_data(reply)}
        audits = (await admin.request('GET', '/api/v1/audit?per_page=50'))['items']
        matches = [r for r in audits if r['key_id'] == key_id and r['public_tool_name'] == name
                   and r['audit_id'] not in used_audits and r['started_at'] >= started.replace('+00:00', 'Z')]
        require(len(matches) == 1, 'unique_tool_audit')
        audit = matches[0]
        used_audits.add(audit['audit_id'])
        evidence['calls'].append({'stage': stage, 'tool': name, 'arguments': args, 'result': result,
            'audit': {k: audit[k] for k in ['audit_id', 'request_id', 'user_id', 'key_id', 'auth_source',
                'server_id', 'public_tool_name', 'upstream_tool_name', 'outcome', 'error_code', 'started_at', 'duration_ms']}})
        save()
        return result

    async def inventory_ok(session, stage):
        result = await call(session, stage, 'inventory__lookup_sku', {'sku': 'DEMO-001'})
        require(not result['is_error'] and result['data']['found'] and
            result['data']['warehouses'] == [{'name': 'Bengaluru', 'quantity': 12}], 'inventory_expected_sample')
        return result

    async def woo_ok(session, stage):
        result = await call(session, stage, 'woocommerce__list_products', {'per_page': 50})
        require(not result['is_error'] and bool(result['data']['items']), 'woocommerce_healthy')
        return result['data']

    try:
        await admin.login(private['admin_email'], private['admin_password'])
        deployment = await kube.deployment()
        original = deployment['spec']['replicas']
        require(original == 1, 'single_inventory_replica_required')
        evidence['original_replicas'] = original
        evidence['deployment_uid'] = deployment['metadata']['uid']
        servers = (await admin.request('GET', '/api/v1/servers?per_page=50'))['items']
        inventory = next(s for s in servers if s['slug'] == 'inventory')
        require(inventory['enabled'], 'inventory_enabled_before_test')
        fields = ['id', 'slug', 'url', 'enabled', 'auth_type', 'header_name']
        evidence['registry_before'] = sorted([{k: s.get(k) for k in fields} for s in servers], key=lambda x: x['id'])
        evidence['before'] = await snapshot()
        require(len(evidence['before']['pods']) == 7 and all(p['ready'] for p in evidence['before']['pods']), 'initial_workloads_ready')
        async with gateway('https://dashboard-m10.urumi.test', context, credential['raw_key']) as session:
            names = [tool.name for tool in (await session.list_tools()).tools]
            require('inventory__lookup_sku' in names and 'woocommerce__list_products' in names, 'required_tools_discovered')
            evidence['shop_products_before'] = await woo_ok(session, 'baseline')
            await inventory_ok(session, 'baseline')
            pods = [p for p in await kube.pods() if ready(p)]
            require(len(pods) == 1, 'single_owned_inventory_pod')
            evidence['F4_deleted_pod'] = await kube.delete_pod(pods[0])
            print('F4: owned Inventory Pod deleted; checking peers and automatic replacement.', flush=True)
            f4_inventory, _ = await asyncio.gather(
                call(session, 'F4 immediately after Pod deletion', 'inventory__lookup_sku', {'sku': 'DEMO-001'}),
                woo_ok(session, 'F4 while Inventory Pod is replacing'))
            evidence['F4_inventory_immediate_failed_safely'] = f4_inventory['is_error']
            evidence['F4_unreachable_observed'] = await server_state(admin, inventory['id'], 'Unreachable', timeout=12)
            evidence['F4_replacement'] = await wait_pod_ready(pods[0]['metadata']['uid'])
            require(await server_state(admin, inventory['id'], 'Connected', timeout=45) is not None, 'F4_registry_recovered')
            await inventory_ok(session, 'F4 recovered')
            evidence['F4'] = 'Succeeded' if evidence['F4_unreachable_observed'] else 'Replacement succeeded; sustained outage visibility covered by F5'
            save()

            scaled = True  # Restoration is required even if the scale response becomes uncertain.
            await kube.scale(0)
            print('F5: owned Inventory Deployment scaled to zero; waiting for recorded Unreachable.', flush=True)
            deadline = time.monotonic() + 60
            while await kube.pods():
                require(time.monotonic() < deadline, 'F5_pod_termination_deadline')
                await asyncio.sleep(.5)
            evidence['F5_unreachable_observed'] = await server_state(admin, inventory['id'], 'Unreachable', timeout=45)
            require(evidence['F5_unreachable_observed'] is not None, 'F5_recorded_unreachable')
            failed = await call(session, 'F5 zero replicas', 'inventory__lookup_sku', {'sku': 'DEMO-001'})
            require(failed['is_error'], 'F5_inventory_safe_failure')
            await woo_ok(session, 'F5 zero replicas healthy peer')
            await kube.scale(original)
            scaled = False
            evidence['F5_replacement'] = await wait_pod_ready()
            require(await server_state(admin, inventory['id'], 'Connected', timeout=45) is not None, 'F5_registry_recovered')
            await inventory_ok(session, 'F5 recovered')
            evidence['shop_products_after'] = await woo_ok(session, 'final')
            require(evidence['shop_products_before'] == evidence['shop_products_after'], 'shop_products_preserved')
            evidence['F5'] = 'Succeeded'
    except BaseException as error:
        evidence['failure_type'] = type(error).__name__
        if type(error).__name__ == 'CheckFailed':
            evidence['failed_check'] = str(error)
    finally:
        try:
            if scaled and original is not None:
                await kube.scale(original)
                scaled = False
            if original is not None:
                evidence['final_inventory_pod'] = await wait_pod_ready()
                final_deployment = await kube.deployment()
                evidence['replicas_restored'] = final_deployment['spec']['replicas'] == original
                if 'inventory' in locals():
                    evidence['final_inventory_registry'] = await server_state(admin, inventory['id'], 'Connected', timeout=45)
            evidence['after'] = await snapshot()
            if 'before' in evidence:
                before, after = evidence['before'], evidence['after']
                require(before['namespace_uid'] == after['namespace_uid'] and before['claims'] == after['claims'], 'persistent_disks_preserved')
                require(before['workloads'] == after['workloads'], 'all_workload_specs_preserved')
                require([p for p in before['pods'] if p['component'] != 'inventory-mcp'] ==
                    [p for p in after['pods'] if p['component'] != 'inventory-mcp'], 'other_six_pods_preserved')
                evidence['other_six_pods_workload_specs_and_pvcs_preserved'] = True
            final_servers = (await admin.request('GET', '/api/v1/servers?per_page=50'))['items']
            evidence['registry_after'] = sorted([{k: s.get(k) for k in fields} for s in final_servers], key=lambda x: x['id'])
            require(evidence['registry_before'] == evidence['registry_after'], 'registry_configuration_preserved')
        except BaseException as error:
            evidence['restoration_failure_type'] = type(error).__name__
        await admin.close()
        evidence['status'] = 'PASS' if evidence.get('F5') == 'Succeeded' and evidence.get('replicas_restored') and not evidence.get('failure_type') and not evidence.get('restoration_failure_type') else 'FAIL'
        save()
        print(json.dumps({'status': evidence['status'], 'F4': evidence['F4'], 'F5': evidence['F5'],
            'replicas_restored': evidence.get('replicas_restored'), 'artifact': str(OUT.relative_to(ROOT) / 'results.json')}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
