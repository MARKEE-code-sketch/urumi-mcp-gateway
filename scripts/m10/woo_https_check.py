"""Explicit owned-shop HTTPS/OAuth read/write proof using the real M3 client."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import ssl
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import httpx
from services.woocommerce_mcp.woocommerce_client import Settings, WooCommerceClient, ShopError

ORIGIN = 'https://shop-m10.urumi.test'


async def check(access, ca):
    context = ssl.create_default_context(cafile=str(ca))
    settings = Settings(ORIGIN, ORIGIN, access['consumer_key'], access['consumer_secret'])
    async with httpx.AsyncClient(verify=context, trust_env=False) as http:
        client = WooCommerceClient(settings, http)
        products, _ = await client.request('GET', '/products', {'sku': 'M10-TLS-PROBE'})
        if products:
            raise ValueError('Probe already exists; review its result before any new write.')
        original, _ = await client.request('GET', '/products/12')
        if original['sku'] != 'DEMO-001':
            raise ValueError('Owned demo product does not match.')
        created, _ = await client.request('POST', '/products', body={
            'name': 'M10 HTTPS Transport Probe', 'sku': 'M10-TLS-PROBE',
            'type': 'simple', 'status': 'draft', 'regular_price': '1.00'})
        return {'status': 'PASS', 'checked_at': datetime.now(timezone.utc).isoformat(),
            'canonical_origin': settings.canonical, 'transport_origin': settings.transport,
            'tls_verification': 'Explicit trusted local CA; hostname/SNI verification enabled',
            'authorization': 'Real M3 OAuth1 HMAC-SHA256; no Basic auth or forged forwarding headers',
            'read_product_id': original['id'], 'created_product_id': created['id'],
            'created_status': created['status'],
            'scope': 'Host client through real Traefik TLS and installed WordPress; not VPS or production Pod egress proof.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-owned-demo', action='store_true', required=True)
    args = parser.parse_args()
    output = ROOT / 'docs/evidence/m10/woo-https.json'
    if output.exists():
        parser.error('Existing evidence must be reviewed before another write.')
    logging.disable(logging.CRITICAL)
    access = json.loads((ROOT / '.tools/operator/m10/access.json').read_text(encoding='utf-8-sig'))
    try:
        result = asyncio.run(check(access, ROOT / '.tools/operator/m10/tls/ca.pem'))
    except ShopError as error:
        result = {'status': 'FAIL', 'error_code': error.code}
    except Exception:
        result = {'status': 'FAIL', 'error_code': 'TRANSPORT_CHECK_FAILED'}
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(result['status'])
    return int(result['status'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
