"""Read-only gateway proof after the final backend image upgrade."""
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.live_checks import gateway, require, result_data, tls_context, wait_tools


async def check(config, key):
    require(config['origin'] == 'https://dashboard-m10.urumi.test', 'exact_test_origin')
    async with gateway(config['origin'], tls_context(config['ca_path']), key['raw_key']) as session:
        names = await wait_tools(session, ['woocommerce', 'inventory', 'learn'])
        orders = result_data(await session.call_tool('woocommerce__list_orders', {'per_page': 20}))
        inventory = result_data(await session.call_tool('inventory__lookup_sku', {'sku': 'DEMO-001'}))
        require(inventory.get('found') is True and isinstance(inventory.get('warehouses'), list), 'sample_inventory_present')
        ids = sorted(item['id'] for item in orders['items'])
        require({16, 19} <= set(ids), 'saved_demo_orders_present')
        return {'status': 'PASS', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'user_id': key['user_id'], 'key_id': key['id'] if 'id' in key else key['key_id'],
            'tool_names': names, 'order_ids': ids, 'inventory_result_received': bool(inventory),
            'scope': 'Real authenticated gateway reads after the final image upgrade; no writes or provider calls.'}


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    config = json.loads((ROOT / '.tools/operator/m10/live-config.json').read_text(encoding='utf-8-sig'))
    key = json.loads((ROOT / '.tools/operator/m10/external-key.json').read_text(encoding='utf-8-sig'))
    try:
        result = asyncio.run(check(config, key))
    except Exception:
        result = {'status': 'FAIL', 'failure': 'Post-upgrade gateway read failed; no raw response retained.'}
    (ROOT / 'docs/evidence/m10/post-upgrade-checks.json').write_text(json.dumps(result, indent=2) + '\n')
    print(result['status'])
    raise SystemExit(int(result['status'] != 'PASS'))
