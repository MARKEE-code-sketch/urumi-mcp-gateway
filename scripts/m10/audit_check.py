"""Read-only correlation of recorded demo attempts with actual gateway audits."""
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.live_checks import Browser, CheckFailed, require, tls_context


async def pages(browser):
    rows = []
    for page in range(1, 101):
        result = await browser.request('GET', f'/api/v1/audit?per_page=50&page={page}')
        rows.extend(result['items'])
        if not result['has_more']:
            return rows
    raise ValueError('Audit collection exceeded its fixed limit.')


async def check(config):
    context = tls_context(config['ca_path'])
    admin, member = Browser(config['origin'], context), Browser(config['origin'], context)
    try:
        await admin.login(config['admin_email'], config['admin_password'])
        await member.login(config['member_email'], config['member_password'])
        rows, own = await pages(admin), await pages(member)
        require(all(row['user_id'] == member.user['id'] for row in own), 'member_audit_boundary')
        await member.request('GET', '/api/v1/audit?user_id=' + admin.user['id'], expected=403)
        await member.request('GET', '/api/v1/members/' + admin.user['id'] + '/keys', expected=404)
        await member.request('POST', '/api/v1/servers',
            {'name': 'Denied', 'slug': 'denied', 'url': config['inventory_url']}, expected=403)
        response = await admin.client.post('/api/v1/members/' + admin.user['id'] + '/keys',
            json={'label': 'Rejected CSRF probe'}, headers={'Origin': config['origin']})
        require(response.status_code == 403, 'csrf_missing_rejected')
        correlations = []
        for name in ('chat-create', 'chat-orders'):
            reply = json.loads((ROOT / f'docs/evidence/m10/browser/{name}.json').read_text())['reply']
            expected_tool = 'woocommerce__create_product' if name == 'chat-create' else 'woocommerce__list_orders'
            require(any(call['tool_name'] == expected_tool for call in reply['tool_calls']), 'expected_chat_tool_present')
            for call in reply['tool_calls']:
                matches = [row for row in rows if row['audit_id'] == call['audit_id']]
                require(len(matches) == 1, 'chat_audit_present')
                row = matches[0]
                require(row['user_id'] == admin.user['id'] and row['auth_source'] == 'session'
                    and row['public_tool_name'] == call['tool_name'] and row['request_id'] == reply['request_id']
                    and row['outcome'] == call['outcome'], 'chat_audit_correlation')
                correlations.append({'demo': name, 'audit_id': row['audit_id'], 'status': 'PASS'})
        external = json.loads((ROOT / 'docs/evidence/m10/external-codex-orders.json').read_text())
        external_rows = [row for row in rows if row['key_id'] == external['key_id']]
        require(bool(external_rows) and all(row['user_id'] == member.user['id'] and
            row['auth_source'] == 'api_key' for row in external_rows), 'external_attribution')
        for tool in ('woocommerce__list_orders', 'woocommerce__list_products', 'inventory__lookup_sku'):
            require(any(row['public_tool_name'] == tool and row['outcome'] == 'success'
                for row in external_rows), 'external_tool_audit')
        for tool in ('woocommerce__get_order', 'woocommerce__update_order_status'):
            require(any(row['public_tool_name'] == tool and row['outcome'] == 'success'
                for row in external_rows), 'owned_order_tool_audit')
        controls = json.loads((ROOT / 'docs/evidence/m10/control-checks.json').read_text())
        control_ids = {controls['ids']['selected_key_id'], controls['ids']['control_key_id']}
        control_rows = [row for row in rows if row['key_id'] in control_ids]
        require(any(row['error_code'] == 'KEY_REVOKED' and row['upstream_tool_name'] is None
            for row in control_rows), 'revocation_no_upstream_audit')
        require(any(row['public_tool_name'] == 'inventory__lookup_sku' and row['outcome'] != 'success'
            for row in control_rows), 'control_failure_audit')
        require(all(row['finished_at'] and row['duration_ms'] is not None and row['duration_ms'] >= 0
            for row in rows if row['outcome'] in ('success', 'error', 'timeout', 'denied')), 'audit_completion_fields')
        fields = ('audit_id', 'request_id', 'user_id', 'key_id', 'auth_source', 'server_id',
                  'public_tool_name', 'upstream_tool_name', 'started_at', 'finished_at', 'duration_ms', 'outcome', 'error_code')
        return {'status': 'PASS', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'correlations': correlations, 'checks': ['member sees only own audits',
                'member cannot filter another user or list their keys', 'member cannot register servers',
                'missing CSRF rejected', 'external key attributed to B', 'completed duration fields present'],
            'attempt_groups': {
                'external_B_including_Codex_Inspector_and_owned_order_tools': [r['audit_id'] for r in external_rows],
                'final_revocation_disable_outage_controls': [r['audit_id'] for r in control_rows],
                'other_owned_demo_and_exploratory_attempts': [r['audit_id'] for r in rows
                    if r['key_id'] != external['key_id'] and r['key_id'] not in control_ids
                    and r['audit_id'] not in {c['audit_id'] for c in correlations}]},
            'correlation_limit': 'Exact request/audit IDs for saved chat; per-user/key/tool/outcome for external CLI calls because CLI does not expose gateway request IDs. Failed exploratory attempts retained in rows.',
            'rows': [{field: row[field] for field in fields} for row in rows]}
    finally:
        await member.close()
        await admin.close()


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    config = json.loads((ROOT / '.tools/operator/m10/live-config.json').read_text(encoding='utf-8-sig'))
    try:
        result = asyncio.run(check(config))
    except CheckFailed as error:
        result = {'status': 'FAIL', 'failure': str(error)}
    except Exception:
        result = {'status': 'FAIL', 'failure': 'Audit correlation or role check failed; no raw response retained.'}
    (ROOT / 'docs/evidence/m10/audit-correlation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])
    raise SystemExit(int(result['status'] != 'PASS'))
