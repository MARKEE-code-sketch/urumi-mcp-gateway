# Real browser demo — 20 October 2026

Chromium used its default certificate verification. No HTTPS bypass, trace,
video, HAR, raw password, session cookie, API key, or checkout URL containing
an order key was retained. Credentials were read only from the ignored private
operator file. Administrator screenshots mask the WordPress account bar.

| Check | Observed result | Evidence |
|---|---|---|
| Fresh shop checkout | Synthetic customer purchased DEMO-001, INR 499, cash on delivery; order 16 received | [checkout.json](checkout.json), [screenshot](checkout.png) |
| WooCommerce order visible | Actual store administrator login showed order 16 | [admin-order.json](admin-order.json), [screenshot](admin-order.png) |
| Dashboard creates product | Signed-in administrator chat used real Groq and exactly one successful `woocommerce__create_product`; product 18, M10 Browser Demo Notebook, INR 129 | [chat-create.json](chat-create.json), [screenshot](chat-create.png) |
| Product appears in storefront | Both original demonstration product and chat-created notebook visible | [screenshot](created-product.png) |
| Checkout of chat-created product | A separate browser session bought product 18, cash on delivery, INR 129; order 19 received | [checkout-notebook.json](checkout-notebook.json), [screenshot](checkout-notebook.png) |
| New order visible in admin | Actual store administrator showed order 19 and notebook line item INR 129 | [admin-notebook.json](admin-notebook.json), [screenshot](admin-notebook.png) |
| Today's order question | Real administrator chat returned order 16 and notebook order 19 using `woocommerce__list_orders`, with store Asia/Kolkata date bounds | [chat-orders.json](chat-orders.json), [screenshot](chat-orders.png) |

The earlier successful today's-orders question, before the notebook purchase,
is preserved in `chat-orders-before-notebook.json` and its screenshot. Order 16
was changed to completed by the separate root-owned API acceptance check before
the final read; the browser did not change its status. Order 19 was processing.

Product creation audit: `193ec61e-66de-4ea4-af6f-d69ac4bb11da`.
Final today's-orders audit: `b64c1863-7371-4020-98f7-331b4eb9a3f8`.
These are real response references; database attribution is checked separately.

Exact commands, run from the repository root in PowerShell with Node and the
already installed frontend Playwright dependency:

```powershell
node scripts/m10/browser_demo.mjs inspect-checkout
node scripts/m10/browser_demo.mjs checkout
node scripts/m10/browser_demo.mjs admin-order
node scripts/m10/browser_demo.mjs chat-create
node scripts/m10/browser_demo.mjs checkout-notebook
node scripts/m10/browser_demo.mjs admin-notebook
node scripts/m10/browser_demo.mjs chat-orders
node --check scripts/m10/browser_demo.mjs
```

The helper now refuses to repeat a recorded checkout or product-creation action.
Earlier checkout inspections timed out on an incorrect accessible button name;
inspection identified WooCommerce's product-specific name, and the selector was
corrected before either order was submitted. There was no uncertain order or
product write and no automatic write retry.

Images of product creation, storefront, notebook receipt, admin order 19, and
final today's-orders reply were visually inspected. Chat intentionally renders
model Markdown as escaped plain text, as approved in M8. WooCommerce saved both
orders but reported that notification email could not be sent: SMTP/email delivery
is not configured in this local test setup. No real payment or customer was used.

## Additional real dashboard acceptance

`node scripts/m10/browser_acceptance.mjs` completed eight actual browser checks:
administrator invitation creation; member redemption; member login and role-aware
navigation; own-key issue; own-key confirmed revocation; own audit view;
administrator Inventory display-name edit and restoration; administrator view of
20 real tool audit records. See [ui-acceptance.json](ui-acceptance.json).
The invitation fragment was removed before redemption; the member did not see
Members navigation or the administrator User UUID audit filter. The Inventory
credential action stayed `keep`; its original name was restored. The browser
does not claim that registry name edits are tool-call audit records.

The synthetic member password and already revoked raw key remain only in
`.tools/operator/m10/browser-qa.json`. Its inherited access rules were checked:
only the current Windows user and SYSTEM have access. The helper refuses to
restart when this private progress file exists, preventing unreviewed duplicate
mutations. All browser contexts closed before the root maintenance/backup work.

Visual review caught a misplaced full-page screenshot mask in the initial key
issuance image. That key had already been revoked; the image was immediately
overwritten with the safe revoked-state screenshot. Therefore the remaining
`own-key-issued-masked.png` is a duplicate revoked-state image, not proof of the
issuance screen. Issuance is supported by the recorded actual API response and
subsequent revoked metadata. The helper now dismisses one-time invitation/key
disclosures before taking screenshots, instead of relying on mask positioning.
The safe replacement image, invitation mask, registry restoration, and audit
screens were visually inspected. No additional key or member was created to
replace the screenshot.
