"""Real WooCommerce signing check; secrets are mounted, never emitted."""
import base64
import hashlib
import hmac
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def signature(method, canonical, query, key, secret, nonce, timestamp):
    quote = lambda value: urllib.parse.quote(str(value), safe='~')
    oauth = {'oauth_consumer_key': key, 'oauth_nonce': nonce, 'oauth_timestamp': str(timestamp), 'oauth_signature_method': 'HMAC-SHA256'}
    params = sorted((quote(k), quote(v)) for k, v in list(query.items()) + list(oauth.items()))
    normalized = '&'.join(k + '=' + v for k, v in params)
    base = '&'.join((method, quote(canonical), quote(normalized)))
    oauth['oauth_signature'] = base64.b64encode(hmac.new((quote(secret) + '&').encode(), base.encode(), hashlib.sha256).digest()).decode()
    return 'OAuth ' + ', '.join(quote(k) + '="' + quote(v) + '"' for k, v in sorted(oauth.items()))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def run():
    key = Path('/run/urumi/rest/consumer-key').read_text().strip()
    secret = Path('/run/urumi/rest/consumer-secret').read_text().strip()
    opener = urllib.request.build_opener(NoRedirect)

    def request(method, path, query=None, body=None, mode='valid', auth=None):
        query = query or {}
        canonical = 'http://shop.urumi.test/wp-json/wc/v3' + path
        signed = canonical if mode != 'canonical' else canonical.replace('shop.urumi.test', 'wrong.urumi.test')
        stamp = int(time.time()) - (3600 if mode == 'expired' else 0)
        headers = {'Host': 'shop.urumi.test', 'Content-Type': 'application/json'}
        if mode != 'missing':
            headers['Authorization'] = signature(method, signed, query, key, secret if mode != 'wrong' else 'wrong-secret', secrets.token_hex(16), stamp)
        if auth:
            headers['Authorization'] = auth
        url = 'http://urumi-wordpress.urumi.svc.cluster.local/wp-json/wc/v3' + path
        if query:
            url += '?' + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        try:
            with opener.open(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=10) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, {}

    status, products = request('GET', '/products', {'context': 'edit', 'sku': 'DEMO-001'})
    assert status == 200 and len(products) == 1, 'Signed administrative read failed'
    replay_query = {'context': 'edit', 'sku': 'DEMO-001'}
    replay_auth = signature('GET', 'http://shop.urumi.test/wp-json/wc/v3/products', replay_query, key, secret, secrets.token_hex(16), int(time.time()))
    assert request('GET', '/products', replay_query, auth=replay_auth)[0] == 200, 'Replay baseline failed'
    assert request('GET', '/products', replay_query, auth=replay_auth)[0] in (401, 403), 'Replayed signature accepted'
    for mode in ('missing', 'wrong', 'canonical', 'expired'):
        status, _ = request('POST', '/products', body={'name': 'Unauthorized probe', 'type': 'simple', 'regular_price': '1.00'}, mode=mode)
        assert status in (401, 403), 'Invalid signature was not rejected: ' + mode
    status, product = request('POST', '/products', body={'name': 'M2 disposable check', 'type': 'simple', 'regular_price': '1.00', 'status': 'draft'})
    assert status == 201, 'Authorized write failed'
    status, _ = request('DELETE', '/products/' + str(product['id']), {'force': 'true'})
    assert status == 200, 'Disposable product cleanup failed'
    status, orders = request('GET', '/orders', {'per_page': 100})
    assert status == 200, 'Signed order read failed'
    print(json.dumps({'signed_read': True, 'signed_write': True, 'invalid_rejected': True, 'product_id': products[0]['id'], 'order_ids': [order['id'] for order in orders]}))


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        # Only our own assertion messages are safe; network exceptions may contain headers/URLs.
        print(json.dumps({'error': str(error) if isinstance(error, AssertionError) else type(error).__name__}))
        raise SystemExit(1)
