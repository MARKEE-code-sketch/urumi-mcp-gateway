"""Run requested K2-K4 checks; retain the MCP session for user-controlled K5."""
import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, time, timedelta, timezone
import getpass
import json
import logging
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.live_checks import Browser, gateway, result_data, tls_context

ORIGIN = 'https://dashboard-m10.urumi.test'
IST = timezone(timedelta(hours=5, minutes=30))
OUT = ROOT / 'docs/evidence/manual-client' / datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
logging.disable(logging.CRITICAL)


async def audit_rows(admin):
    rows = []
    for page in range(1, 101):
        data = await admin.request('GET', f'/api/v1/audit?per_page=50&page={page}')
        rows.extend(data['items'])
        if not data['has_more']:
            return rows
    raise RuntimeError('Audit pagination limit reached')


async def main():
    key = getpass.getpass('Selected gateway API key: ')
    key_id = key.split('_', 2)[1]
    context = tls_context(ROOT / '.tools/operator/m10/tls/ca.pem')
    private = json.loads((ROOT / '.tools/operator/m10/access.json').read_text())
    admin = Browser(ORIGIN, context)
    evidence = {'checked_at': datetime.now(timezone.utc).isoformat(), 'endpoint': ORIGIN + '/mcp',
                'transport': 'Streamable HTTP', 'selected_key_id': key_id,
                'K2': 'Pending', 'K3': 'Pending', 'K4': 'Pending', 'K5': 'Not run',
                'calls': [], 'provider_calls': 0, 'shop_write_calls': 0}
    OUT.mkdir(parents=True, exist_ok=True)

    def save():
        (OUT / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')

    try:
        async with AsyncExitStack() as stack:
            # The external client receives only the gateway address/key and local TLS trust.
            selected = await stack.enter_async_context(gateway(ORIGIN, context, key))
            tools = [t.name for t in (await selected.list_tools()).tools]
            # Separate operator session checks configuration and attribution only.
            await admin.login(private['admin_email'], private['admin_password'])
            members = (await admin.request('GET', '/api/v1/members?per_page=50'))['items']
            owner = None
            for member in members:
                keys = (await admin.request('GET', f"/api/v1/members/{member['id']}/keys?per_page=50"))['items']
                if any(k['id'] == key_id and not k['revoked_at'] for k in keys):
                    owner = member
                    break
            assert owner and owner['role'] == 'member', 'Selected key must belong to member B'
            evidence['member_B_id'] = owner['id']
            servers = (await admin.request('GET', '/api/v1/servers?per_page=50'))['items']
            enabled = [s['slug'] for s in servers if s['enabled']]
            assert all(any(t.startswith(slug + '__') for t in tools) for slug in enabled)
            evidence.update(K2='Succeeded', discovered_tools=tools, enabled_server_slugs=enabled,
                            tls_verified=True, upstream_credentials_given_to_client=False)
            before = {r['audit_id'] for r in await audit_rows(admin)}

            async def call(name, args):
                data = result_data(await selected.call_tool(name, args))
                evidence['calls'].append({'tool': name, 'arguments': args, 'result': data})
                return data

            today = datetime.now(IST).date()
            lower = datetime.combine(today, time.min, IST)
            upper = lower + timedelta(days=1) - timedelta(microseconds=1)
            evidence['today_IST'] = str(today)
            orders = []
            for page in range(1, 11):
                data = await call('woocommerce__list_orders', {'page': page, 'per_page': 50,
                    'created_from': lower.isoformat(), 'created_to': upper.isoformat()})
                orders.extend(data['items'])
                if not data['has_more']:
                    break
            else:
                raise RuntimeError('Orders pagination limit reached')
            evidence['today_order_count'] = len(orders)
            # The labelled existing order is deliberately not called a today's order.
            order = (await call('woocommerce__get_order', {'order_id': 21}))['order']
            assert order['id'] == 21
            products = await call('woocommerce__list_products', {'sku': 'DEMO-001', 'per_page': 50})
            matching = [p for p in products['items'] if p['sku'] == 'DEMO-001']
            assert len(matching) == 1
            inventory = await call('inventory__lookup_sku', {'sku': 'DEMO-001'})
            assert inventory['found'] and any(w['name'] == 'Bengaluru' and w['quantity'] == 12 for w in inventory['warehouses'])
            rows = [r for r in await audit_rows(admin) if r['audit_id'] not in before and r['key_id'] == key_id]
            assert len(rows) == len(evidence['calls'])
            assert all(r['user_id'] == owner['id'] and r['auth_source'] == 'api_key' and r['outcome'] == 'success' for r in rows)
            evidence['audit'] = [{k: r[k] for k in ['audit_id', 'request_id', 'user_id', 'key_id', 'auth_source',
                'public_tool_name', 'upstream_tool_name', 'outcome', 'started_at', 'duration_ms']} for r in rows]
            evidence['K3'] = 'Succeeded'

            denials = []
            async with httpx.AsyncClient(verify=context, trust_env=False, timeout=30) as http:
                for label, token in [('missing', None), ('wrong', 'ugw_' + key_id + '_invalid-test-value')]:
                    headers = {'Accept': 'application/json, text/event-stream'}
                    if token:
                        headers['Authorization'] = 'Bearer ' + token
                    # Real MCP initialize and tools/call messages, not browser GET requests.
                    for method, params in [('initialize', {'protocolVersion': '2025-03-26', 'capabilities': {},
                            'clientInfo': {'name': 'manual-negative-client', 'version': '1'}}),
                            ('tools/call', {'name': 'inventory__lookup_sku', 'arguments': {'sku': 'DEMO-001'}})]:
                        response = await http.post(ORIGIN + '/mcp', headers=headers,
                            json={'jsonrpc': '2.0', 'id': len(denials) + 1, 'method': method, 'params': params})
                        body = response.json()['error']
                        assert response.status_code == 401 and body['code'] == 'UNAUTHENTICATED'
                        denials.append({'key_case': label, 'method': method, 'http_status': 401,
                            'error_code': body['code'], 'request_id': body['request_id']})
            denied_rows = [r for r in await audit_rows(admin) if r['request_id'] in {d['request_id'] for d in denials}]
            assert len(denied_rows) == 2 and all(r['outcome'] == 'denied' and r['user_id'] is None
                and r['upstream_tool_name'] is None and r['server_id'] is None for r in denied_rows)
            evidence.update(K4='Succeeded', negative_auth=denials,
                denied_audit=[{k: r[k] for k in ['audit_id', 'request_id', 'user_id', 'key_id', 'outcome', 'upstream_tool_name']} for r in denied_rows])
            save()
            print(json.dumps({'K2': evidence['K2'], 'K3': evidence['K3'], 'K4': evidence['K4'],
                'today_IST': str(today), 'today_orders': len(orders), 'existing_order_id': order['id'],
                'sku': matching[0]['sku'], 'price': matching[0]['price'], 'currency': matching[0]['currency'],
                'warehouse': inventory['warehouses'], 'member_B_id': owner['id'], 'audit_calls': len(rows),
                'evidence': str(OUT.relative_to(ROOT) / 'results.json')}), flush=True)

            # Prepare K5, but do not revoke the user's selected key.
            control_key = await admin.request('POST', f"/api/v1/members/{owner['id']}/keys",
                {'label': 'Manual K5 control ' + OUT.name}, 201)
            control = await stack.enter_async_context(gateway(ORIGIN, context, control_key['raw_key']))
            result_data(await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
            evidence.update(K5='Ready - awaiting user revocation', control_key_id=control_key['id'],
                control_key_prefix=control_key['prefix'], selected_session_kept_open=True)
            save()
            print('READY_FOR_USER_REVOCATION. Original MCP ClientSession remains open. Awaiting CHECK after user revokes selected key.', flush=True)
            command = await asyncio.to_thread(input)
            if command.strip() != 'CHECK':
                return
            denied = False
            try:
                await selected.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'})
            except BaseException:
                denied = True
            async with httpx.AsyncClient(verify=context, trust_env=False, timeout=30) as http:
                response = await http.post(ORIGIN + '/mcp',
                    headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json, text/event-stream'},
                    json={'jsonrpc': '2.0', 'id': 501, 'method': 'tools/call',
                          'params': {'name': 'inventory__lookup_sku', 'arguments': {'sku': 'DEMO-001'}}})
                assert denied and response.status_code == 401 and response.json()['error']['code'] == 'KEY_REVOKED'
            result_data(await control.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
            evidence.update(K5='Revocation/control checks passed - B browser confirmation still needed',
                open_session_next_call_rejected=True, revoked_http_status=401, revoked_code='KEY_REVOKED', control_still_works=True)
            save()
            print(json.dumps({'K5': evidence['K5'], 'evidence': str(OUT.relative_to(ROOT) / 'results.json')}), flush=True)
    except BaseException as error:
        evidence['failure_type'] = type(error).__name__
        save()
        print(json.dumps({'status': 'FAILED', 'type': type(error).__name__, 'evidence': str(OUT.relative_to(ROOT) / 'results.json')}), flush=True)
    finally:
        await admin.close()


if __name__ == '__main__':
    asyncio.run(main())
