# M2: install and check the persistent shop

The shop is standard WordPress plus WooCommerce; MariaDB saves records and a separate website disk saves uploads/plugins. Helm describes the running containers and disks. The setup Job is a one-off task, similar to running a Docker container for a script.

Run from the project root in PowerShell with Docker Desktop Linux engine running and the existing `urumi` cluster started. Do not delete/recreate the cluster to repair connectivity. The scripts always use `.tools/m1/kubeconfig.yaml`, context `k3d-urumi` and namespace `urumi`; they never switch your active context.

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/deploy-store.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/check-store.ps1
~~~

The deployment resolves approved image tags to digests, builds the thin store image, imports it into k3d, creates missing Secrets without printing them, applies Helm and runs setup. `-UsePulledImages` skips network pulls when the approved images are already downloaded. `-SkipBuild` reuses the existing local `urumi-store:m2` image; use only when source has not changed. Runtime image IDs and safe settings are recorded under `docs/evidence/m2/`; ignored `.tools/m2/` holds local runtime settings, never credentials.

Map `shop.urumi.test` to `127.0.0.1` in Windows hosts if missing, using the approved administrative host-edit workflow. Open `http://shop.urumi.test` and add **Urumi Demo Product**, SKU `DEMO-001`, price INR499, to your cart. This virtual sample needs no shipping. Checkout as a guest using fictional information and Cash on delivery. No money or delivery is involved. Save cropped storefront, cart, confirmation and admin-order screenshots without passwords or personal details.

The admin username is `urumi-admin`. To retrieve its password deliberately in your own local terminal, without saving it to the evidence directory:

~~~powershell
$encoded = kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi get secret urumi-store-admin -o jsonpath='{.data.password}'
[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encoded))
Remove-Variable encoded
~~~

This intentionally displays an operator password. Do not run it in a shared recording or save its output. Sign into `/wp-admin`, open WooCommerce orders and verify the confirmation's order ID and product/price. Record that ID and run `check-store.ps1 -BrowserOrderId <id>`; the checker verifies saved data and replaces only the recorded WordPress and MariaDB Pods. Browser screenshot checks remain BLOCKED until a human or an actual browser review confirms the flow; an HTTP200 or existing order alone is not checkout proof.

For the optional automated browser evidence runner, use an isolated test environment and installed Google Chrome:

~~~powershell
uv venv .tools/browser-venv --python .venv/Scripts/python.exe
uv pip install --python .tools/browser-venv/Scripts/python.exe playwright==1.64.0
.tools/browser-venv/Scripts/python.exe scripts/m2/browser-checkout.py
~~~

This performs a real browser COD checkout with fictional details, then checks the same order in admin. It reads the project's admin Secret only in memory and masks customer fields in screenshots. On this workspace, the ignored `.tools/m2/browser-order.json` records order 15; rerunning the helper reuses that order for evidence instead of creating another one. Keep that marker when refreshing screenshots. The helper is a test tool, not part of the deployed shop.

To rerun configuration without rebuilding:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/store-setup.ps1
~~~

Rerun reuses existing Secrets, seed SKU, attachment and integration-key identity. It does not overwrite existing product edits. A missing or mismatched key after completed initialization stops instead of silently rotating or recreating revoked credentials. The read/write integration key belongs to `urumi-integration`, not the human administrator. OAuth1a signs canonical `http://shop.urumi.test` requests sent internally to `urumi-wordpress.urumi.svc.cluster.local` with the fixed public Host. Responses and JSON bodies remain unencrypted locally; do not use real customer data. M3 does not connect to this shop until M10.

The two retained PVCs are `urumi-mariadb-data` and `urumi-wordpress-content`. Replacing a Pod preserves them; deleting the cluster/node can lose them. Normal cleanup removes only recorded checking Jobs. Both claims have Helm's `keep` annotation, so disabling resources/uninstall does not intentionally delete them; reinstall may require explicit ownership reconciliation. Never delete the PVCs as troubleshooting. Backups, restoration and production migration are separate M9 work. Save data before upgrading WordPress/WooCommerce/MariaDB: persisted WordPress files do not automatically upgrade when a new image starts, and Helm rollback does not reverse database changes.

For intentional credential rotation: pause callers, create a new integration key and matching Secret through an operator-controlled secure step, prove signed access, update callers in M10, revoke the old key, then verify rejection. The ordinary setup does not provide an automatic rotation command; avoid editing one side of the database/Secret pair. Never expose REST keys to browser/client configuration or Helm values.

Production-shaped values use the same templates, replacement hostname, immutable private-registry image, supplied Secret names and selected StorageClass. HTTPS requires trusted termination and consistent canonical URLs; no disabled certificate verification. Rendering those values is configuration evidence, not a VPS deployment claim.
