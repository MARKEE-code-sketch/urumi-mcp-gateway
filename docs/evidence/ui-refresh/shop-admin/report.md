# Teal WordPress / WooCommerce administration

Observed 23 October 2026 on **https://shop-m10.urumi.test/wp-admin/**. User requested administration matching the gateway/storefront, then flagged the WordPress Events and News RSS errors during implementation.

## Implemented

Local Figtree font, Urumi logo/favicon, teal/mint navigation, readable headings/controls, white panels and branded native login. Products, orders, editor tabs, settings, native status colours, permissions, notices and mobile navigation keep their WordPress/WooCommerce behavior. A permission-checked overview shows actual WooCommerce product/order totals and links to Products, Orders, Shop and Settings. The default WordPress welcome introduction is replaced for store managers; users who dismissed it receive a native dashboard-widget fallback.

The internet-backed WordPress Events and News widget is omitted for store managers. The actual WordPress NetworkPolicy allows server egress only to DNS (53) and MariaDB (3306), so its external RSS fetches fail. No public-internet egress rule was added. Site Health and other native notices/widgets remain visible. This removes an irrelevant feed, rather than claiming that external feeds or WordPress update checks now work.

WordPress's official [admin asset hook](https://developer.wordpress.org/reference/hooks/admin_enqueue_scripts/) and [login asset hook](https://developer.wordpress.org/reference/hooks/login_enqueue_scripts/) load `admin.css` on those screens only. Theme source is shipped through the existing Helm ConfigMap. No new plugin, JavaScript library, authentication logic, secret, database or image was introduced.

## Verification

- **23 store/setup tests passed in 4.25s**, Helm lint passed.
- **Seven PHP files** syntax-checked in the existing PHP image before deployment.
- **25 browser checks passed**: branded login at desktop/390px, invalid password feedback, valid login, real overview totals, Products/search, Product 12 price/SKU/inventory tabs, Orders/search, Order 21 status/details, cash-on-delivery settings, desktop and390px screens, mobile submenu navigation, logout, and admin-stylesheet absence on the storefront. No page overflow on the tested closed-menu screens; zero JavaScript page errors.
- Extra settled dashboard check: native Woo status data and empty review state load; RSS panel is absent. Desktop/mobile screenshots were recaptured after those native widgets finished loading.
- Final local Helm revision **11**, all **seven workloads Ready**, existing PVC identities preserved. Three product records and order IDs **16, 19, 21** unchanged. Shop settings and the other six Pod identities preserved across each WordPress rollout. No new product/order/settings saves were performed by these admin UI checks.
- Saved-credential scan of42new/source/evidence files reported zero matches. Passwords/cookies/nonces/HAR/traces are not saved in evidence.

Browser test adjustments followed actual installed behavior: WordPress clears/focuses the password field on a delayed callback after an invalid login, WooCommerce11 uses a labelled React checkbox rather than the older COD ID, and the native mobile Products menu requires choosing All Products after expanding the submenu. The checks now exercise those native flows.

## Evidence and commands

[Browser results](browser.json), [deployment/hash checks](deployment.json), [final state/network restriction](final-state.json), [settled dashboard data](dashboard-data.json), [dashboard desktop](dashboard-desktop.png), [dashboard mobile](dashboard-mobile.png), [login](login-desktop.png), [products](products-desktop.png), [order details](order-detail-desktop.png), [settings](settings-desktop.png). Before screenshots are retained for comparison.

Repository-root PowerShell commands:

```powershell
C:\Python313\python.exe -m pytest tests\store\test_store.py tests\e2e\test_store_bootstrap.py -q -p no:cacheprovider
.tools\m1\helm.exe lint deploy\charts\urumi
.\.venv\Scripts\python.exe scripts\store\deploy-storefront.py --output docs\evidence\ui-refresh\shop-admin
node scripts\store\check-shop-admin.mjs
```

## Limits and rollback

This is native administration restyled by the active first-party theme. No attempt was made to recreate every WooCommerce analytics/extension screen or override the editor's internals. Product/order controls were inspected without saving; the previously verified order21 remains the same. No new full M10 acceptance, new installation, VPS or mail-delivery claim.

Existing WordPress/WooCommerce admin code still requests its usual browser-side stats/avatar/service resources (`stats.wp.com`, `pixel.wp.com`, `secure.gravatar.com`, `woocommerce.com` observed). These are separate from server-side RSS egress. The custom branding is local; this report does not claim an entirely offline native administration. Existing Site Health/mail warnings were not hidden or resolved by this styling task.

Admin appearance follows the `urumi-shop` theme. Roll Helm back to revision9 to return to the original storefront-only theme while preserving shop data; revision10 contains admin styling before news-widget removal. Use the same chart/values for restoration because theme files live in a ConfigMap rather than the PVC archive.
