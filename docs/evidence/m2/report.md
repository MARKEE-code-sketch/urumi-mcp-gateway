# M2 implementation and observed checks

**Dates:** 15?16 October 2026. **Status:** Implemented and verified; all ten M2 checks PASS when runtime results are combined with reviewed browser evidence. User module acceptance is pending. `results-initial.json` preserves the first run; `results.json` preserves raw runtime output with three deliberate browser-review BLOCKED labels. `acceptance-results.json` records the combined review.

## What works and what it proves

The real WordPress/WooCommerce store and MariaDB have been installed into the existing local Kubernetes cluster using the shared Helm chart. Separate saved disks hold the database and website files. Setup creates server-side credentials, INR/Asia-Kolkata settings, COD checkout, the seed product and a dedicated REST identity. M3 remains independent; no MCP-to-real-shop integration has been performed.

Seven offline checks passed in `unittest-output.txt`: opt-in installation, two retained disks, public storefront/internal services, Secret references without templated credentials, workload probes/resources/no API token, narrow database policy, production-shaped templates, and signing boundary behavior. Four PowerShell scripts parsed successfully (`powershell-syntax.json`); built-image PHP syntax checks are in `php-syntax.txt`. These checks do not replace live checkout or persistence evidence.

`browser-result.json` records an actual isolated headless Chrome session, browser `155.0.8059.40`, using Playwright 1.64. It opened the storefront, displayed the corrected 64x64 product image, added the product to cart, completed guest COD checkout and opened the same order in WooCommerce admin. The recorded order is **15**, total **INR499.00**, payment method **cod**. Screenshots include `storefront.png`, `product-image.png`, `browser-cart.png`, `browser-checkout-form.png`, `order-confirmation.png`, and `admin-order.png`; fictional customer fields are masked. Final receipt/admin/product screenshots were visually reviewed after the configuration correction: matching order15/INR499, visible image, masked contact fields and live shop indicator. Runtime browser-review labels remain BLOCKED by design; the combined review records their separate PASS evidence.

## Initial run and correction

| Acceptance | Initial observed state | Evidence / remaining check |
|---|---|---|
| M2-01 | PASS: local and production-shaped lint/render | `helm-checks.txt`, `rendered-local.txt`, `rendered-prod.txt` |
| M2-02 | PASS: both workloads Ready with probes/resources | `workload-settings.txt`, `versions.json` |
| M2-03 | Technical checks passed; runner BLOCKED for browser review | `ingress-check.txt`, `exposure-check.txt`, `database-access-check.txt`, storefront screenshots |
| M2-04 | PASS: configuration rerun preserved identities and settings | `setup-check.txt`, `snapshot.txt` |
| M2-05 | Runner BLOCKED for browser/admin review | Browser result and screenshots record actual order15; promote only after review. |
| M2-06 | Runner BLOCKED for displayed-image/browser-order review | `persistence-before.json`, `product-image.png`; disk and HTTP image hashes match. |
| M2-07 | PASS: WordPress replacement preserved records and image | `wordpress-restart.txt`, `persistence-after-wordpress.json` |
| M2-08 | Initial action failed during recovery; initial runner incorrectly left BLOCKED | MariaDB replacement occurred, but subsequent snapshot failed because cached WordPress Ready preceded fresh DB connectivity; `mariadb-restart.txt`, `snapshot.txt`, `failure.txt`. Final rerun required. |
| M2-09 | Not reached initially | Real signed REST reads/writes and invalid/replayed signatures remain pending in final run. |
| M2-10 | Not reached initially | Final reapply/retention/cleanup remains pending. |

The first failure was observed at the database restart stage: rollout completed at approximately 15:05:42 UTC, but a snapshot at 15:05:49 reported a database connection failure. The checker now waits for a **fresh HTTP readiness response through Apache/PHP and the database**, with redirects disabled, before each snapshot. Read-only snapshots retry within the recovery window. Its catch handler now marks the active acceptance ID FAIL instead of leaving a failed action as “Not reached”. Historical outputs are preserved; successful rerun evidence must establish the fix.

The browser's initial admin page also showed the shop's coming-soon indicator. Bootstrap now explicitly sets WooCommerce's documented `woocommerce_coming_soon` option to `no`, so the required storefront is live. A final source rebuild/configuration rerun and browser recapture verify the corrected setting; source change alone is not proof. [Official WooCommerce guidance](https://developer.woocommerce.com/docs/extensions/extension-onboarding/integrating-coming-soon-mode/) documents this option.

## Saved data and initial image correction

The observed seed product is **12**, attachment **13**, integration-key record **1**, and order **15**. `persistence-before.json` records SKU/name/price/status; order status/currency/total and product/quantity/line totals; attachment URL; local and fetched-HTTP byte hashes; and PVC names/UIDs. Customer contacts are excluded.

The initial build created a 1x1 placeholder. The deliberate one-off correction checked the owned attachment marker, seed linkage, path, exact original dimensions and SHA256 before replacing that file with the repository bootstrap's visible 64x64 blue/orange picture. Product12 and attachment13 remained unchanged. `initial-image-migration-result.json` records old hash `13cdf73d971c90b0394dd0a268b8b8d3f930ee7ca36f1a7d04c8d90ebb238346` and new hash `f1d689bba3617d9af0d58e93b1a909b1f3ff16b2962ed6a27e9a728dc0e8aeb3`. This correction happened before checkout/persistence evidence; it was not a store reset.

The initial snapshot's Bound claims are `urumi-mariadb-data`, UID `91b18137-d90e-49f0-b16e-ab2686a82df0`, and `urumi-wordpress-content`, UID `cae72902-5c12-4c82-9225-965798cb78b4`. Final snapshots must retain both identities and all safe record/image content after both Pod replacements. Local-path data survives this Pod replacement test; node/cluster deletion, backups and production recovery are not proved.

## Commands and reproducibility

Run from project root in PowerShell. Agent Docker/Kubernetes operations required the approved outside-sandbox command path; no permission-denied result was counted as a pass.

~~~powershell
python -m unittest discover -s tests/store -v
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/deploy-store.ps1 -UsePulledImages
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/check-store.ps1 -BrowserOrderId 15
.tools/browser-venv/Scripts/python.exe scripts/m2/browser-checkout.py
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/check-store.ps1 -BrowserOrderId 15 -ResumeFromRest
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi get pods,services,ingresses,pvc
~~~

The browser helper is reviewable source under scripts/m2; its isolated environment and order marker are ignored local test state, not project services. The checkout run creates an order; do not blindly repeat it when only a screenshot recapture is required. Exact native commands, timestamps and exit codes appear in the named raw logs. `versions.json` records immutable WordPress/CLI/MariaDB inputs and the built local image ID. `image-build.txt` includes publisher plugin checksum verification; `image-import.txt` records cluster import. Secrets are never passed through Helm values or recorded in these artifacts.

## Remaining gates

The corrected restart checks passed on 16 October. The runner then stalled while PowerShell 5.1 serialized provider metadata attached to the file-read REST script. Converting that value to plain text fixed the ConfigMap payload; configmap-serialization-check.json records its correct bounded shape and content roundtrip. The guarded ResumeFromRest mode verified saved shop/PVC state and completed only09/10 without repeating Pod disruption. It exited0. Real OAuth protected reads/writes passed; missing/wrong/expired/replayed/incorrect-canonical signatures were rejected, and the disposable product was removed. Both PVCs remain retained; zero owned Jobs and removal of the temporary ConfigMap were verified. Browser03/05/06 PASS comes from actual screenshot/flow review, separately from raw runtime labels. User acceptance remains pending. The same-chart production render is verified, not an actual VPS deployment. M2 acceptance does not prove gateway authorization, chat, external-client use, or M3 integration; those remain their owning modules/M10.
