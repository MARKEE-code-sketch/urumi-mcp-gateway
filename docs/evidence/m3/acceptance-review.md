# M3 independent acceptance evidence review

**Date:** 15 October 2026. **Verdict:** PASS for all ten independent M3 acceptance IDs; user acceptance is pending. Applied the project mcp-kubernetes-acceptance-qa guidance. The reviewer inspected source and saved observations, without rerunning tests or changing the system.

| Checks | Observed evidence and conclusion |
|---|---|
| M3-01 / M3-02 | [Host tests](local-tests.txt) show actual TCP Streamable HTTP discovery/calls and independent OAuth vectors. [First cluster client](m3-allowed-first.json) records protocol 2025-11-25, exactly five contract tools and all five successful calls with matching text/structured replies. PASS. |
| M3-03 / M3-04 | Final host suite exercises strict types, unknown/missing/blank/overlength inputs, invalid dates/offsets and zero REST dispatch; source/logical pagination, exact SKU/search, empty pages and inclusive fractional UTC bounds. PASS. |
| M3-05 / M3-06 | Final suite exercises distinct safe failures, healthy recovery, finite real TCP and whole-tool deadlines, uncertain-write warning and exactly one write dispatch. PASS against fake REST. |
| M3-07 | Host checks cover contact/credential sentinels and echoed credentials in allowed fields. [Translator logs](translator-logs.txt) contain fixed operational information without tested sentinels or authorization values. PASS. |
| M3-08 | [Linux pip check](linux-pip-check.txt) exits 0; [image identity check](image-identity-check.json) matches build config digest to recorded Pod imageIDs. Same-chart local/production rendering and [workload settings](workload-status.yaml.txt) establish resources/probes and running workloads. [Probe events](probe-events.txt) explicitly show liveness HTTP404 and kubelet-triggered restart; [restored client](m3-after-probe.json) succeeds afterward. PASS; no live VPS claim. |
| M3-09 | [Denied caller](m3-denied.json) reports ConnectionRefusedError after DNS-first checking; [first allowed](m3-allowed-first.json) and [allowed again](m3-allowed-again.json) succeed against the same endpoint. [Exposure snapshot](exposure.json.txt) shows ClusterIP-only Services and no Ingress. PASS. |
| M3-10 | [Cleanup](cleanup.txt) records release uninstall, namespace deletion and subsequent absence, all exit 0. [M2 before](store-before.txt) and [after](store-after.txt) contain identical seven resource identities, including retained PVCs. PASS. |

The [runner result](results.json) reports six live groups PASS, consistent with the inspected raw evidence. The [module report](report.md) accurately combines these with 18 passing host tests and explains the deployed-image/test-only source timing. Asyncio slow-task warnings and a pip cache-permission warning do not represent failed checks.

These results prove the translator with fake REST and an isolated gateway stand-in. They do not prove real-shop writes/date filtering, real gateway identity/audit, user-key revocation, external client interoperability, two-user end-to-end behavior, or VPS deployment. Those remain later modules/M10.
