"""Real local Chrome checkout/admin evidence; never prints or persists credentials."""
import base64
import json
from pathlib import Path
import re
import subprocess
import sys

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/m2'
STATE = ROOT / '.tools/m2/browser-order.json'
STAGE = 'startup'
sys.stdout.reconfigure(encoding='utf-8')


def main():
    global STAGE
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 900})
        page = context.new_page()
        page.set_default_timeout(15000)
        if not STATE.exists():
            page.goto('http://shop.urumi.test/shop/')
            page.get_by_role('heading', name='Shop', exact=True).wait_for()
            page.screenshot(path=str(EVIDENCE / 'storefront.png'), full_page=True)
            page.goto('http://shop.urumi.test/product/urumi-demo-product/')
            image = page.locator('.woocommerce-product-gallery__image img').first
            image.wait_for(state='visible')
            assert image.evaluate('e=>e.complete && e.naturalWidth===64 && e.naturalHeight===64')
            page.screenshot(path=str(EVIDENCE / 'product-image.png'), full_page=True)
            page.get_by_role('button', name='Add to cart', exact=True).click()
            page.goto('http://shop.urumi.test/cart/')
            assert 'Urumi Demo Product' in page.locator('main').inner_text()
            page.screenshot(path=str(EVIDENCE / 'cart.png'), full_page=True)
            page.goto('http://shop.urumi.test/checkout/')
            for field, value in {
                'billing_first_name': 'Demo', 'billing_last_name': 'Shopper',
                'billing_address_1': '1 Demo Street', 'billing_city': 'New Delhi',
                'billing_postcode': '110001', 'billing_phone': '9000000000',
                'billing_email': 'shopper@example.invalid',
            }.items():
                page.locator('#' + field).fill(value)
            page.locator('#billing_country').select_option('IN')
            page.locator('#billing_state').select_option('DL')
            page.screenshot(path=str(EVIDENCE / 'checkout.png'), full_page=True,
                            mask=[page.locator('.woocommerce-billing-fields__field-wrapper')])
            page.get_by_role('button', name='Place order', exact=True).click()
            page.wait_for_url(re.compile(r'/checkout/order-received/\d+/'), timeout=30000)
            order_id = int(re.search(r'order-received/(\d+)/', page.url).group(1))
            assert 'Cash on delivery' in page.locator('main').inner_text()
            STATE.write_text(json.dumps({'order_id': order_id}), encoding='utf-8')
            email = page.get_by_text('shopper@example.invalid', exact=True)
            billing = page.get_by_text('Demo Shopper', exact=False)
            phone = page.get_by_text('9000000000', exact=False)
            assert email.count() == 1 and billing.count() >= 1 and phone.count() >= 1
            page.screenshot(path=str(EVIDENCE / 'order-confirmation.png'), full_page=True,
                            mask=[email, billing, phone])
        else:
            order_id = int(json.loads(STATE.read_text(encoding='utf-8'))['order_id'])

        # This newly created project Secret is read only in memory for this admin check.
        STAGE = 'admin-login'
        secret = json.loads(subprocess.check_output([
            'kubectl', '--kubeconfig', str(ROOT / '.tools/m1/kubeconfig.yaml'),
            '--context', 'k3d-urumi', '-n', 'urumi', 'get', 'secret',
            'urumi-store-admin', '-o', 'json'], text=True))['data']
        username = base64.b64decode(secret['username']).decode()
        password = base64.b64decode(secret['password']).decode()
        page.goto('http://shop.urumi.test/wp-login.php')
        page.locator('#user_login').fill(username)
        page.locator('#user_pass').fill(password)
        page.locator('#wp-submit').click()
        page.wait_for_url('**/wp-admin/**')
        STAGE = 'admin-order'
        page.goto(f'http://shop.urumi.test/wp-admin/admin.php?page=wc-orders&action=edit&id={order_id}')
        page.get_by_role('heading', name=f'Order #{order_id}', exact=True).wait_for()
        page.get_by_text('Urumi Demo Product', exact=True).first.wait_for()
        assert str(order_id) in page.locator('body').inner_text()
        assert '499.00' in page.locator('body').inner_text()
        page.screenshot(path=str(EVIDENCE / 'admin-order.png'), full_page=True,
                        mask=[page.locator('.order_data_column').nth(1),
                              page.locator('.order_data_column').nth(2),
                              page.locator('#order-attribution')])
        # Reopen the existing receipt without creating another order. Its private
        # receipt URL remains in memory and never enters the evidence or logs.
        STAGE = 'receipt-evidence'
        kubectl = ['kubectl', '--kubeconfig', str(ROOT / '.tools/m1/kubeconfig.yaml'),
                   '--context', 'k3d-urumi', '-n', 'urumi']
        pods = json.loads(subprocess.check_output(kubectl + ['get', 'pods', '-l',
            'app.kubernetes.io/component=wordpress,app.kubernetes.io/instance=urumi',
            '-o', 'json'], text=True))['items']
        assert len(pods) == 1
        receipt = subprocess.check_output(kubectl + ['exec', pods[0]['metadata']['name'],
            '--', 'su', '-s', '/bin/sh', 'www-data', '-c',
            f"wp eval 'echo wc_get_order({order_id})->get_checkout_order_received_url();' --path=/var/www/html"],
            text=True).strip()
        assert receipt.startswith(f'http://shop.urumi.test/checkout/order-received/{order_id}/')
        page.goto(receipt)
        email = page.get_by_text('shopper@example.invalid', exact=True)
        billing = page.get_by_text('Demo Shopper', exact=False)
        phone = page.get_by_text('9000000000', exact=False)
        assert email.count() == 1 and billing.count() >= 1 and phone.count() >= 1
        assert 'Cash on delivery' in page.locator('main').inner_text()
        assert '₹499.00' in page.locator('main').inner_text()
        page.screenshot(path=str(EVIDENCE / 'order-confirmation.png'), full_page=True,
                        mask=[email, billing, phone])
        result = {'status': 'PASS', 'order_id': order_id, 'currency': 'INR',
                  'total': '499.00', 'payment_method': 'cod',
                  'browser': browser.version, 'mode': 'isolated headless Chrome',
                  'customer_fields': 'fictional and masked in screenshots',
                  'steps': ['storefront', 'displayed 64x64 image', 'add to cart',
                            'COD checkout', 'confirmation', 'same order in WooCommerce admin']}
        (EVIDENCE / 'browser-result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result))
        context.close()
        browser.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Playwright's raw call log can echo fill values; never emit it.
        print(json.dumps({'status': 'FAIL', 'stage': STAGE, 'error_type': type(exc).__name__}))
        sys.exit(1)
