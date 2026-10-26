# M2 acceptance evidence review

**Dates:** 15–16 October 2026. **Verdict:** PASS for the ten independent M2 checks; user module acceptance remains pending.

Applied the project acceptance-QA guidance. The independent reviewer inspected the implementation, diagnosed the initial readiness race, and visually reviewed the final product/receipt/admin screenshots. The root agent verified the final corrected restart, REST and cleanup outputs and assembled the combined results. This does not claim that the independent reviewer reran commands or personally inspected the final REST stage.

| Checks | Observed proof |
|---|---|
| M2-01/02 | Local/production-shaped Helm lint/render; Ready workloads with resources/probes; pinned build inputs and publisher plugin checksum verification. |
| M2-03 | Actual storefront screenshot and HTTP Ingress; internal database Service; baseline, allowed, denied and fresh allowed network controls. |
| M2-04 | Setup rerun preserves seed, attachment and key identities; INR, Asia/Kolkata and COD recorded in snapshots. |
| M2-05 | Real isolated Chrome guest checkout created order15 for INR499.00/COD; same product, quantity and total visible in admin. Final receipt/admin contact masks visually confirmed. |
| M2-06 | Displayed 64x64 image, attachment13 and URL; matching saved-file and fetched-HTTP SHA256; original PVC identities recorded. |
| M2-07/08 | Different WordPress and MariaDB Pod UIDs; identical safe product/order fields, image hashes and PVC identities before/after each replacement. Corrected fresh-readiness recovery checks passed on 16 October. |
| M2-09 | Real protected signed read/write; invalid/missing/expired/replayed/incorrect-canonical signatures rejected. Safe result records product12/order15; disposable product deleted. |
| M2-10 | Helm reapply succeeds, retained claims remain, zero owned checking Jobs and temporary ConfigMap removal observed. |

`results.json` intentionally retains the runner's three browser-review BLOCKED labels. `acceptance-results.json` combines its seven runtime PASS results with the separately observed browser evidence; all ten are PASS. Original failure evidence remains in `results-initial.json`, `failure.txt` and appended logs. The PowerShell provider-metadata serialization fix is supported by `configmap-serialization-check.json`; resume syntax and final successful runtime checks support the corrected runner.

The shop remains running. No PVC/cluster reset occurred. No real payment or mail delivery is configured. Pod replacement is proved on this node; backup restoration, node/cluster loss and actual VPS deployment are not proved. M3-to-real-shop wiring, gateway identity/audit, chat and two-user behavior remain later modules/M10.
