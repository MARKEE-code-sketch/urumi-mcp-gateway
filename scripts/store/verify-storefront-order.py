"""Read back one browser-created order through the authenticated gateway."""
import asyncio
import json
import logging
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.m10.live_checks import gateway, result_data, tls_context


async def main():
    logging.disable(logging.CRITICAL)
    out = ROOT / 'docs/evidence/ui-refresh/storefront'
    browser = json.loads((out / 'browser.json').read_text())
    assert browser['orderId'] > 0
    config = json.loads((ROOT / '.tools/operator/m10/live-config.json').read_text())
    key = json.loads((ROOT / '.tools/operator/m10/external-key.json').read_text())
    async with gateway(config['origin'], tls_context(config['ca_path']), key['raw_key']) as session:
        data = result_data(await session.call_tool('woocommerce__get_order', {'order_id': browser['orderId']}))
    order = data['order']
    assert order['id'] == browser['orderId'] and order['currency'] == 'INR'
    evidence = {'status': 'PASS', 'tool': 'woocommerce__get_order', 'route': 'HTTPS gateway /mcp',
                'provider_calls': 0, 'write_calls': 0,
                'order': {k: order[k] for k in ['id', 'status', 'currency', 'total', 'line_items']}}
    (out / 'gateway-order.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({'status': 'PASS', 'order_id': order['id'], 'artifact': str(out.relative_to(ROOT) / 'gateway-order.json')}))


if __name__ == '__main__':
    asyncio.run(main())
