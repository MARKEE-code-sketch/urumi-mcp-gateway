# M3 verification report

**WHAT:** Our own Python server offers five WooCommerce tools over Streamable HTTP. **WHY:** It translates the approved MCP contract into shop REST calls. **HOW:** Validate -> sign -> request -> project safe fields -> validate reply. These checks use a fake shop; M10 connects the real M2 store.

**Status:** Independently reviewed and verified. All ten M3 acceptance IDs PASS within their module boundary; user acceptance is pending. No real-shop integration claim is made.

## Verified local results

Command, from project-root PowerShell:

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests/woocommerce_mcp -v
~~~

Observed final run: **18 tests PASS**, 15.002 seconds. Actual negotiated MCP protocol: **2025-11-25**. See [local-tests.txt](local-tests.txt). `pip check` returned `No broken requirements found`. PowerShell ParseFile found zero runner syntax errors; Helm lint passed. The final run added reviewer-requested validation bounds/search regressions and aggregate/normalized byte-limit tests; runtime code did not change after the Kubernetes image was built.

| Acceptance | Observed local evidence | Cluster evidence / remaining gate |
|---|---|---|
| M3-01 | Actual HTTP client initializes, discovers exactly five original tool schemas/annotations; direct call before discovery; stateless session ID absent. | PASS: [allowed client discovery/calls](m3-allowed-first.json). |
| M3-02 | All five tools over actual TCP HTTP; fake REST observes signed method/path/query/body. Independent WooCommerce 11.2.1 OAuth normalization vectors pass for GET/POST/PUT, percent literals, plus/space, Unicode, ampersand; wrong method/origin differ. | PASS: all five in [cluster client transcript](m3-allowed-first.json); actual shop integration remains M10. |
| M3-03 | Invalid integer/float/bool/text IDs/pages, bad prices, blanks, unknown fields, statuses, dates/offsets and reversed bounds return INVALID_ARGUMENT with zero fake REST dispatch. | Unit validation is independent of deployment; no gateway identity claim. |
| M3-04 | 240 source products over three REST source pages and five logical pages; exact SKU/search; empty page; exactly-full last source page; work cap; inclusive UTC endpoints and fractional lower bound across logical pages. | PASS independently. Installed shop filter/timezone evidence remains M10. |
| M3-05 | Distinct safe missing-order, duplicate-SKU, 401/403, connection, 503, invalid JSON/fields/pagination-header, and redirect failures; healthy call succeeds afterward. | No installed-shop failure behavior inferred. |
| M3-06 | Whole-tool deadline injected for read/write; real TCP read timeout returns within 8 seconds with uncertain-write warning; exactly one write dispatch. | Kubernetes does not substitute for REST deadline checks. |
| M3-07 | Contact sentinel omitted; echoed configured key/secret redacted even in allowed product-name field; exception/log sentinels absent. Destination/credential override arguments rejected. | PASS: [translator logs](translator-logs.txt), runner sentinel assertion. |
| M3-08 | Helm lint and PowerShell syntax gate pass; 2 MiB source, total 8 MiB, normalized 512 KiB caps all exercised. | PASS build/Linux pip check/render/probes/Ready, observed liveness restart and [image identity](image-identity-check.json). |
| M3-09 | HTTP Origin/Host guards and streamed 64 KiB request cap pass; translator health stays healthy during fake shop outage. | PASS: allowed-denied-allowed same-service connectivity; DNS resolved first; no public exposure. |
| M3-10 | Independent source reviewer checked contract/security/harness and requested validation/DNS clarifications, now applied. | PASS cleanup: exact owned namespace/release removed; M2 UIDs unchanged. User acceptance remains pending. |

## Verified Kubernetes results

Root agent ran the reviewed runner on the existing k3d cluster:

~~~powershell
.\scripts\m3\check-m3.ps1
~~~

Observed runner exit **0**, with **six live check groups PASS**, including cleanup, in [results.json](results.json). The Linux image installs exact dependencies and `pip check` passes ([build](image-build.txt), [Linux dependencies](linux-pip-check.txt)). Both [local](render-local.yaml.txt) and [production](render-prod.yaml.txt) translator resources render from the same chart. Production rendering is not a live VPS deployment.

Root independently verified image identity: build config digest `sha256:486c72b5ce744f67ef680fc5135cc0f69dae7f54e5c951a9903cc07384b80ef3` matches every recorded translator/fake-shop Pod imageID. Docker's inspected image ID is the separate multi-platform index digest; the verification correctly compares the running config digest to build output rather than confusing these two identifiers. See [identity check](image-identity-check.json).

Actual SDK client Jobs discovered/called all five tools via the internal ClusterIP. The unrelated caller resolved DNS before connecting and was refused; a fresh permitted caller then succeeded. See [first allowed](m3-allowed-first.json), [denied](m3-denied.json), [allowed again](m3-allowed-again.json), and [exposure](exposure.json.txt).

The deliberate nonexistent liveness path produced HTTP 404 probe failures and an observed container restart. Restoring `/livez` produced Ready service and another successful five-tool client run. See [events](probe-events.txt), [restart state](probe-restart.json.txt), [recovery](m3-after-probe.json), and [workload resources](workload-status.yaml.txt).

The harness release and its dedicated namespace, including fake shop/client Jobs/fake Secret/temporary policy, were removed. [Cleanup commands](cleanup.txt) include successful namespace absence check; [M2 before](store-before.txt) and [after](store-after.txt) resource UIDs match. This check did not connect the translator to M2 or modify shop disks.

## What was implemented

`services/woocommerce_mcp` contains server, schemas, tools, bounded signed REST client, exact dependency baseline, and Dockerfile. The SDK supplies protocol plumbing; our code supplies all shop behavior. No installed WooCommerce MCP implementation is used.

The shared chart's translator templates create one non-root Deployment, internal ClusterIP Service, readiness/liveness/startup probes, explicit resources, and caller/shop/DNS NetworkPolicy. Tests own the fake shop, independent OAuth verifier, real MCP client, and dedicated `urumi-m3-check` harness. `scripts/m3/check-m3.ps1` owns isolated install, allowed/denied checks, controlled probe failure/recovery, evidence, and exact namespace cleanup. It never targets M2 PVCs for deletion.

## Limits

Local HTTP authentication does not encrypt data or sign JSON body integrity. Actual M2 credential validity, shop-visible product changes, installed WooCommerce inclusive date behavior, gateway/user audit, user-B external client, and full failure isolation remain later integration evidence. Default limits are 8 seconds per tool, 20 source pages/2,000 source records, 2 MiB per source body/8 MiB total/512 KiB normalized result. An exceeded limit returns an explicit failure, not a complete-looking truncated result. Concurrent store edits are not a snapshot transaction.

Initial local test run had one incorrect test expectation: page 6 omitted per_page=50 and therefore used default20, making it a valid nonempty page. Corrected the test to hold page size fixed; no application behavior was changed to satisfy that mistaken expectation. Earlier 14- and 16-test runs passed; the final 18-test run is the current saved result. The deployed image contains the earlier test suite, while runtime files match; final host tests exercise the same runtime with the additional test cases.
