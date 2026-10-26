# M10 live acceptance

The separate `urumi-m10` release runs the real application on local Kubernetes. The original `urumi` shop remains separate. The [independent live review](final-live-review.md) passed all18 criteria on21 October2026 with no unresolved mandatory implementation/testing defect. User acceptance remains pending; the [ledger](acceptance-results.json) records the observed criteria rather than treating unit tests as deployment proof.

## Observed results

| Check | Result and evidence |
|---|---|
| Actual runtime | Seven workloads Ready, three Bound persistent claims; final rebuilt backend image chain and all41 source inputs verified in both targets; [current image/runtime](monitor-fix-runtime.json). The [earlier snapshot](live-runtime.json) and [review](runtime-review.md) describe the original image. |
| HTTPS | Windows chain, normal HTTPS request and Chromium validation passed for the dashboard. Development CA is restricted to `.urumi.test` and CurrentUser trust; [setup and rollback](local-https.md). |
| Storefront | Real COD checkout orders 16 and 19 visible in Woo admin; [browser evidence](browser/report.md). |
| Dashboard chat | Real Groq created published product 18, INR129; later listed both actual orders. Chat activity and audits match administrator A; [browser evidence](browser/report.md), [audit correlation](audit-correlation.json). |
| External member | Actual Codex CLI 0.162.1 answered today's orders and a Woo/Inventory question using only the gateway URL and member B's key; [orders](external-codex-orders.json), [cross-server](external-codex-cross.json). Inspector 2.11.0 listed nine tools and called Inventory with clean exit; [Inspector](inspector.json). CLI proof does not claim Inspector visual UI testing. |
| All five Woo tools | Product list/create and order list/get/status update observed through the gateway. Owned order16 changed processing to completed; [order tools](owned-order-tools.json). |
| Key revocation | The next request on the existing MCP connection was rejected; separate raw HTTP401 confirmed KEY_REVOKED; independent control key still worked. Temporary keys revoked after checks; [controls](control-checks.json). |
| Disable and outage | Disabled Inventory disappeared from gateway/member preview; its old tool name was rejected. Deleting the owned Inventory Pod produced Unreachable and failed Inventory calls while Woo/Learn succeeded. Replacement recovered Connected; [controls](control-checks.json). No scale-to-zero fallback was needed in the final passing run. |
| Security | Non-gateway Pod could resolve Woo DNS but connection was denied. Gateway positive control worked; [network](network-denial.json). Eighteen actual RBAC checks verified scoped Secret permissions; [runtime review](runtime-review.md). Member privacy and missing-CSRF negatives passed; [audit correlation](audit-correlation.json). |
| Woo HTTPS/OAuth | The actual M3 client read product12 and created draft probe20 through the real shop TLS Ingress, using verified local CA/hostname and OAuth1 HMAC-SHA256; [transport](woo-https.json). This host-side check does not prove production Pod egress or a VPS deployment. |
| Restart persistence | Four actual sequential Pod replacements preserved shop/platform records and three PVC identities; [results](persistence.json), [review](persistence-review.md). All seven workloads recovered after each fault. |
| Browser account management | Actual invitation/redeem/login, own-key issuance/revocation, registry edit/restore and audit viewing passed; [browser acceptance](browser/ui-acceptance.json). |
| Isolated recovery | Encrypted consistent backup restored into disposable isolated storage; all11 PostgreSQL tables, complete MariaDB data, 9,289 WordPress files and matching Secret bytes agreed; [restore](recovery-restore.json), [scope](recovery.md). No running-app or off-machine recovery claim. |
| Clean source installation | Fresh source-only package/operator environment and empty storage produced seven Ready workloads, trusted login and a real fresh-store MCP read. Edit/disable/deletion survived restarts. The late monitor patch was separately deployed and matched to41 running source files; disposable three PVCs/two namespaces removed; [report](clean-install/report.md). |

The real provider probe also closed the earlier M7 provider gap: [provider probe](provider-probe.json). No paid fallback was configured. Microsoft Learn remains a real hosted upstream; Inventory explicitly supplies sample warehouse data.

## Final recovery correction

During the clean rehearsal a backend Pod remained unready and refused requests; restarting that disposable Pod recovered it. The exact cause of that incident was not established. Separate regression testing reproduced a concrete monitor gap: after fencing requests, a temporarily busy blocking adapter could raise `PlatformError` outside the recovery loop's PostgreSQL-only handler and terminate that monitor. The handler now retries that known error while keeping requests fenced, then exits for a clean restart only after reachability succeeds. It never reacquires ownership in place.

The new regression failed before the correction. All27 runtime tests then passed, followed by the complete final controlled suite: **231 PASS, 6 opt-in PostgreSQL SKIP, 71.03 seconds**; [final suite](controlled-final/controlled-tests.txt), [focused runtime results](monitor-recovery-tests.xml). Earlier live flows used the original image; the surgical correction has separate [rebuilt-image/upgrade](monitor-fix-runtime.json) and [actual gateway read](post-upgrade-checks.json) evidence. Historical image/source hashes are retained rather than relabelled as the new image.

On21 October the local API was briefly unavailable after the existing node container restarted; the operator did not recreate the node or disks. The first upgrade timed out and was retained as a failed attempt. Once the API returned, the imported OCI content needed an exact CRI-visible digest alias; adding that alias resolved ImagePullBackOff without another Pod deletion. The subsequent same-chart upgrades passed, both targets had seven Ready workloads, and original resource identities remained unchanged. This is recorded in the [upgrade evidence](monitor-fix-runtime.json), not attributed to an application test failure.

## Check commands

These are explicit test actions from repository-root PowerShell. They create disposable keys/data or briefly disrupt the selected test component. Do not blindly replay browser checkout/product creation or reuse them against a different shop.

```powershell
./.tools/m10/venv/Scripts/python.exe scripts/m10/control_checks.py --private-config .tools/operator/m10/live-config.json --output docs/evidence/m10/control-checks.json --run-owned-demo
./.tools/m10/venv/Scripts/python.exe scripts/m10/audit_check.py
./.venv/Scripts/python.exe scripts/m10/woo_https_check.py --run-owned-demo
```

The Woo HTTPS helper used the existing M3 environment with oauthlib3.3.1. It refuses another write when its evidence or probe SKU already exists. Private inputs remain under the ACL-protected ignored operator directory; no upstream credentials were supplied to Codex or Inspector.

## Limitations and remaining work

Implementation, live checks and independent review are complete. Restart persistence, clean installation and isolated encrypted data restoration passed, with temporary resources removed. The [known-value scan](final-artifact-scan.json) and [document check](final-doc-check.json) record their actual scope. A real VPS, demo recording/upload, repository handoff and submission have not been performed. Checkout email delivery is unconfigured; orders were saved successfully. Development certificates expire and require renewal; this is a local trust setup, not public hosting.

The first combined external-client run encountered concurrent Woo failures while Inventory worked; separate final prompts passed. The client's invalid per_page100 call was rejected and corrected to20; the saved final orders evidence retains this failed attempt. Early control-runner attempts stopped because of SDK task-group shutdown and an overly strict controller-label assumption; temporary keys were cleaned up. The passing final run is recorded separately from those harness corrections.

The [earlier report](report.md) remains the historical controlled-build checkpoint, including 161 controlled passes, six separate PostgreSQL passes and actual image build/smoke evidence. Those counts are separate suites and must not be added as unique tests.
