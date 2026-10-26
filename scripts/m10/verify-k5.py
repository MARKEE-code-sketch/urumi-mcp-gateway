"""Repeat K5 with disposable B keys, isolating revoked-client transport shutdown."""
import asyncio
from datetime import datetime, timezone
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
OUT = ROOT / 'docs/evidence/manual-client/20261024-095606'
FIELDS = ['audit_id', 'request_id', 'user_id', 'key_id', 'auth_source', 'public_tool_name',
          'upstream_tool_name', 'outcome', 'error_code', 'started_at']
logging.disable(logging.CRITICAL)


async def main():
    original = getpass.getpass('Previously revoked gateway key: ')
    previous = json.loads((OUT / 'results.json').read_text())
    owner = previous['member_B_id']
    private = json.loads((ROOT / '.tools/operator/m10/access.json').read_text())
    context = tls_context(ROOT / '.tools/operator/m10/tls/ca.pem')
    admin = Browser(ORIGIN, context)
    result = {'status': 'FAIL', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'member_B_id': owner, 'shop_write_calls': 0, 'provider_calls': 0}
    issued = []
    selected_task = None
    state = {}
    trigger = asyncio.Event()

    async def selected_worker(raw, ready):
        try:
            async with gateway(ORIGIN, context, raw) as session:
                state['before'] = result_data(await session.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
                ready.set_result(True)
                await trigger.wait()
                state['same_session_next_call_attempted'] = True
                try:
                    reply = await session.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'})
                    state['unexpected_success'] = not reply.isError
                except BaseException as error:
                    state['call_exception_type'] = type(error).__name__
        except BaseException as error:
            state['transport_exit_type'] = type(error).__name__
            if not ready.done():
                ready.set_exception(RuntimeError('Selected client could not initialize'))

    try:
        await admin.login(private['admin_email'], private['admin_password'])
        async with httpx.AsyncClient(verify=context, trust_env=False, timeout=30) as http:
            response = await http.post(ORIGIN + '/mcp',
                headers={'Authorization': 'Bearer ' + original, 'Accept': 'application/json, text/event-stream'},
                json={'jsonrpc': '2.0', 'id': 601, 'method': 'tools/call',
                      'params': {'name': 'inventory__lookup_sku', 'arguments': {'sku': 'DEMO-001'}}})
            error = response.json()['error']
            assert response.status_code == 401 and error['code'] == 'KEY_REVOKED'
            result['original_user_key'] = {'http_status': 401, 'code': error['code'], 'request_id': error['request_id']}

        for label in ['selected', 'control']:
            key = await admin.request('POST', f'/api/v1/members/{owner}/keys',
                {'label': 'K5 isolated verification ' + label + ' ' + result['checked_at'][:19]}, 201)
            issued.append(key)
        selected, control = issued
        result.update(selected_test_key_id=selected['id'], control_test_key_id=control['id'])
        async with gateway(ORIGIN, context, control['raw_key']) as control_session:
            control_before = result_data(await control_session.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
            ready = asyncio.get_running_loop().create_future()
            selected_task = asyncio.create_task(selected_worker(selected['raw_key'], ready))
            await asyncio.wait_for(asyncio.shield(ready), 45)
            await admin.request('DELETE', f"/api/v1/members/{owner}/keys/{selected['id']}", expected=204)
            result['selected_revoked_while_both_sessions_open'] = True
            trigger.set()
            await asyncio.wait_for(asyncio.shield(selected_task), 45)
            assert state.get('same_session_next_call_attempted') and not state.get('unexpected_success')
            control_after = result_data(await control_session.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
            assert control_before == control_after == state['before']
            assert control_after['warehouses'] == [{'name': 'Bengaluru', 'quantity': 12}]
            result.update(control_same_session_survived=True, control_result=control_after,
                          selected_client_state=state)

        rows = (await admin.request('GET', f'/api/v1/audit?per_page=50&user_id={owner}'))['items']
        selected_rows = [r for r in rows if r['key_id'] == selected['id']]
        control_rows = [r for r in rows if r['key_id'] == control['id']]
        denied = [r for r in selected_rows if r['error_code'] == 'KEY_REVOKED']
        assert len(selected_rows) == 2 and len(denied) == 1 and denied[0]['outcome'] == 'denied'
        assert denied[0]['upstream_tool_name'] is None
        assert len(control_rows) == 2 and all(r['outcome'] == 'success' for r in control_rows)
        assert all(r['user_id'] == owner and r['auth_source'] == 'api_key' for r in selected_rows + control_rows)
        assert max(r['started_at'] for r in control_rows) > denied[0]['started_at']
        result['audits'] = [{k: r[k] for k in FIELDS} for r in selected_rows + control_rows]
        result['B_browser_chat'] = {'result': 'Usable', 'evidence_source': 'User confirmation in conversation',
                                    'operator_browser_retest': False}
        result['status'] = 'PASS'
    except BaseException as error:
        result['error_type'] = type(error).__name__
    finally:
        if selected_task and not selected_task.done():
            selected_task.cancel()
            await asyncio.gather(selected_task, return_exceptions=True)
        cleanup = []
        for key in issued:
            try:
                await admin.request('DELETE', f"/api/v1/members/{owner}/keys/{key['id']}", expected=204)
                cleanup.append({'key_id': key['id'], 'revoked': True})
            except BaseException:
                cleanup.append({'key_id': key['id'], 'revoked': False})
        result['temporary_test_key_cleanup'] = cleanup
        await admin.close()
        (OUT / 'k5-verification.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'status': result['status'], 'original_user_key': result.get('original_user_key'),
            'control_same_session_survived': result.get('control_same_session_survived'),
            'temporary_keys_revoked': all(c['revoked'] for c in cleanup),
            'artifact': str(OUT.relative_to(ROOT) / 'k5-verification.json')}))


if __name__ == '__main__':
    asyncio.run(main())
