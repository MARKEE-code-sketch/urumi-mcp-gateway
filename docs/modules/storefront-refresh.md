# Teal WooCommerce storefront

User approved implementation on 2026-10-23, following the explanation of a custom WordPress theme versus a separate React storefront.

## What, why and how

Give the customer shop the gateway's teal (`#147d69`), mint (`#eaf6ef`), Figtree typography and Urumi mark. WordPress renders the theme; WooCommerce still owns products, search, sorting, pagination, product options, cart sessions, checkout validation, payment methods, orders and customer accounts. No second application or copied product database.

The home page introduces the real catalogue and features an actual available product. Shop, search, product detail, cart, checkout and account pages share one header and footer. Every navigation item resolves through WordPress/WooCommerce URL functions. There are no fake reviews, invented discounts, newsletter forms, payment claims or decorative buttons.

## Ownership and design

- `deploy/charts/urumi/files/store-theme/`: first-party classic theme, PHP templates, CSS, local font and licensed identity/icons.
- `templates/store/theme.yaml`: Helm ConfigMap containing text and font bytes. A ConfigMap is a Kubernetes resource for non-secret files, mounted as a read-only theme directory inside the existing WordPress container.
- `templates/store/wordpress.yaml`: mount and content checksum to restart WordPress when theme changes. Existing content/database persistent disks and image stay intact.
- `scripts/store-setup.ps1` and `scripts/m10/store_bootstrap.py`: mount and activate the bundled theme on fresh setup; existing shop activation is explicit and does not rerun setup.
- `scripts/store/check-storefront.mjs`: browser checks and sanitized screenshots/results.
- `tests/store/test_store.py`: independent chart regression checks.

Native WooCommerce templates remain authoritative, avoiding copied checkout logic and template-version drift. Customer authentication remains separate from gateway team authentication. WordPress administration keeps its current interface. The selected visual direction is a light storefront with readable type, restrained rounded panels, real catalogue contents and responsive layouts.

Subsequent approved scope: [shop administration refresh](shop-admin-refresh.md) extends the same identity to native admin/login screens. The statement above describes the original storefront-only release.

## Checks and release

Before activation: render/lint Helm, run store tests, lint PHP inside the existing PHP image, capture theme/settings/product/order counts and PVC identities privately. Deploy with existing Helm values, activate only `urumi-shop`, then verify home/catalog/search/sorting/product/cart update/remove/empty state/account login/logout/checkout errors and a uniquely tagged cash-on-delivery test order. Confirm the order in WooCommerce administration and through the existing MCP/gateway path when available. Never repeat an uncertain checkout without checking for an existing order.

Check desktop and 390px layouts, images/fonts, keyboard focus and public network requests. Recreate the WordPress Pod through the rollout and verify the same content/database disks, product data and other workloads. Theme changes require the same chart on restore; read-only theme files are deliberately managed through source/Helm rather than the WordPress theme editor.

Rollback: activate the previously captured theme before rolling Helm back to the recorded prior revision. No credential rotation, payment-provider setup, product replacement, customer-data cleanup, backend redesign or public publishing is in scope. Test orders use clearly identified local test details and are reported rather than silently removed.

## Implementation evidence

Implemented and deployed locally on 23 October 2026. See [verification report](../evidence/ui-refresh/storefront/report.md) for observed results, commands, screenshots and limits.
