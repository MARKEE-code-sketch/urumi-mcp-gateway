# Teal storefront implementation and verification

Observed 23 October 2026 on the existing local `urumi-m10` shop. User approved a storefront matching the gateway and requested that all components connect to real shop functions.

## Result

Live shop: **https://shop-m10.urumi.test/**. Local Helm release is now revision **9**. The first-party `urumi-shop` theme uses gateway teal/mint, the same local Figtree font and Urumi mark, responsive navigation, product search, a real-product home page and matching WooCommerce page styles.

The theme delegates product details, sorting, add-to-cart, quantities, sessions, checkout, cash on delivery, orders, account forms and validation to WooCommerce. It contains no copied product data, payment-provider integration, fake reviews or inert newsletter controls. Native template integration follows [WooCommerce's classic theme guidance](https://developer.woocommerce.com/docs/theming/theme-development/classic-theme-developer-handbook), with assets loaded through [WordPress's enqueue API](https://developer.wordpress.org/reference/functions/wp_enqueue_style/).

## Verified observations

- **23 store/setup regression tests passed**; Helm lint passed. Tests cover existing boundaries plus read-only mount, exact text/font data, size, literal non-template contents, checksum changes and fresh-setup activation.
- **Six PHP files** passed syntax checks inside the running WordPress PHP image before deployment.
- **21 final browser checks passed**, including search, empty search, sorting, product detail, add-to-cart, quantity updates, removal/empty cart, asynchronous header counts, required checkout validation, customer account login, orders navigation and logout. Screenshots cover desktop and 390px mobile; no tested page overflow, broken images, JavaScript errors or external storefront requests.
- One real, labelled guest cash-on-delivery purchase created **order #21**, product **12 / DEMO-001**, quantity **1**, total **INR 499.00**, status **processing**. The thank-you page was observed. A separate read through **`woocommerce__get_order` at the authenticated HTTPS gateway `/mcp`** returned the same order. No LLM/provider call was needed.
- Final stored order IDs are **16, 19, 21**: only one new test purchase. The order's note matches the unique purchase test tag. Later browser runs reused this order and did not resubmit checkout.
- All **seven workloads Ready**, all **three existing PVCs Bound**. Each rollout check preserved product records, existing order IDs, settings, disk identities and the other six Pod identities. The theme selection survived subsequent WordPress rollouts.
- New artifacts were checked against saved private credential values: **zero matches**. No credentials, order keys, browser cookies, traces or HAR files were saved in public evidence.

## Issues found and resolved

The first cart check found a stale header count after a quantity update. Enqueuing WooCommerce's native `wc-cart-fragments` script fixed it; both quantity refresh and asynchronous catalogue add-to-cart subsequently passed. `cart-badge-regression.json` records the original failure.

The purchase completed before an account screenshot check caught remote Gravatar images from WordPress's frontend admin toolbar. The theme now hides that toolbar on customer pages and supplies a permission-checked administration link in the footer. WordPress administration itself is unchanged. Final browser checks have no external storefront requests. `purchase-browser.json` is the original overall failed run with its successful order-creation checkpoint; it is deliberately not labelled as an overall pass.

Two test-harness adjustments were needed: WooCommerce's descriptive accessible add-to-cart label required its native link selector, and lazy images must be decoded before checking whether they loaded. Neither adjustment bypasses the corresponding cart/image assertions.

## Files and reproducibility

- Source: `deploy/charts/urumi/files/store-theme/` and `templates/store/theme.yaml`.
- WordPress mount: `templates/store/wordpress.yaml`.
- Fresh setup: `scripts/store-setup.ps1`, `scripts/m10/store_bootstrap.py`. Both mount and activate the theme after normal setup. Existing shop setup was **not** rerun.
- Scoped local deployment: `scripts/store/deploy-storefront.py` saves private effective Helm values, checks PHP, upgrades the same chart, activates only this theme and checks data/PVC/other-Pod preservation and deployed file hashes.
- Browser test: `scripts/store/check-storefront.mjs`; once an order exists it requires `--reuse-order` to avoid another purchase.
- Gateway read-back: `scripts/store/verify-storefront-order.py`.

Commands run from repository-root PowerShell:

```powershell
C:\Python313\python.exe -m pytest tests\store\test_store.py tests\e2e\test_store_bootstrap.py -q -p no:cacheprovider
.tools\m1\helm.exe lint deploy\charts\urumi
.\.venv\Scripts\python.exe scripts\store\deploy-storefront.py
node scripts\store\check-storefront.mjs
node scripts\store\check-storefront.mjs --reuse-order
.\.venv\Scripts\python.exe scripts\store\verify-storefront-order.py
```

Actual final test result: **23 passed in 3.24s**. The first browser command was used before the test order existed. The second command completed final verification without creating another order.

Primary evidence: [deployment](deployment.json), [browser checks](browser.json), [purchase checkpoint](purchase-browser.json), [gateway read](gateway-order.json), [final cluster/order state](final-state.json), [desktop](home-desktop.png), [mobile](home-mobile.png), [checkout](checkout-desktop.png), [confirmation](order-confirmation.png), [account](account-desktop.png).

## Scope and remaining limits

This verifies the currently visible simple demo catalogue and cash-on-delivery flow. Existing product titles/images were retained, including sample artwork and WooCommerce's placeholder where no photo exists. Other payment providers, shipping scenarios, variable/downloadable products and live customer accounts were not introduced or claimed tested. Fresh-install job wiring was source-tested; a new store was not provisioned for this redesign. No new full M10 acceptance, VPS deployment, publication or submission claim.

Theme files live in a Helm ConfigMap rather than the content PVC; restoring a backup requires the corresponding chart and values. WordPress's theme editor cannot change this read-only theme. For rollback from the first redesign, activate the prior `twentytwentyfive` theme before rolling Helm back to revision 6. Revision 8 retains the teal theme but precedes the frontend-toolbar fix. Existing database/content disks and credentials are unchanged.
