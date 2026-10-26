# Teal shop administration

User approved matching the shop administration to the gateway/storefront on 23 October 2026.

## What, why and how

Restyle the existing WordPress/WooCommerce administration and login with the local Figtree font, Urumi mark, teal/mint palette, readable controls and white panels. Preserve native menus, mobile collapse, roles, nonce protection, notices, product/order editing and settings. A small native dashboard widget gives store managers real product/order totals and capability-checked shortcuts. No separate admin app, authentication service, copied database or UI plugin.

## Files and design

- `deploy/charts/urumi/files/store-theme/admin.css`: admin/login presentation, responsive native-layout refinements.
- `deploy/charts/urumi/files/store-theme/admin.php`: native asset hooks, login identity and dashboard overview. Included by `functions.php`.
- Existing Helm theme ConfigMap includes PHP/CSS automatically; its checksum rolls only WordPress. No image, secret or disk change.
- `scripts/store/check-shop-admin.mjs`: real browser login/error/logout, overview, products/list/editor, orders/list/details, settings, responsive navigation and storefront isolation checks.
- Existing deployment checker accepts a separate evidence directory so storefront evidence remains historical.

Use native Dashicons in administration, preserving its established control language. Scope custom overview styles with `urumi-admin-` names. Retain status badge/error colours and visible notices. Do not override editor iframes, block-editor positioning, toolbar heights or collapsed navigation behavior. The CSS is loaded only in administration and login, never on the storefront.

User flagged the built-in WordPress Events and News RSS connection errors during review. Omit that unrelated news widget for store managers; retain Site Health, notices and all shop controls. The shop's existing egress policy allows DNS and its database, so external server-side RSS fetches fail as expected. Do not loosen that policy to load a promotional news feed.

## Verification and release

Independent review of plan and final changes; PHP syntax and Helm store/setup regression tests before rollout. Deploy the same local chart with the current values and capture product/order/settings/PVC/other-Pod preservation. Verify actual WordPress login (including a harmless invalid password), dashboard counts against Woo APIs, Product 12 editor and Order 21 details, product search and order search, cash-on-delivery settings, logout, desktop and390px navigation/layout. No order creation, settings save, user change or existing product mutation is needed. Inspect screenshots and separate existing native/plugin console/network behavior from newly introduced failures.

This supersedes the earlier storefront-only scope: administration is now explicitly included. Customer checkout and gateway authentication remain separate. Admin appearance follows the active first-party theme; switching that theme restores native administration styling. Helm rollback to the recorded prior revision reverts this addition. Native admin widgets may make their usual external requests; locally bundled branding adds no external service.

Implemented and deployed on23October2026. [Verification report](../evidence/ui-refresh/shop-admin/report.md):23store/setup tests,25browser checks, native Woo dashboard data loaded, release11 healthy, existing shop data preserved.
