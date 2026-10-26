# M6 independent acceptance review

**Date:** 18 October 2026. **Verdict: PASS for the independent M6 module.** All twelve module criteria have supporting evidence. User acceptance remains pending. This is not final-system or M10 acceptance.

The reviewer applied the project's MCP/Kubernetes acceptance skill, inspected the assignment, approved specification/design, application and test source, and saved command outputs. Review was read-only: the reviewer did not rerun disruptive checks, modify application code or change cluster data. The implementation team ran the recorded checks.

## Evidence reviewed

- [Host tests](host-tests.txt): 41 passed; [catalog cases](host-catalog-tests.txt): six additional passed; [isolation/identity cases](host-isolation-identity-tests.txt): three additional passed; [incorrect upstream credential cases](host-upstream-auth-tests.txt): two additional passed. Total: **52 distinct gateway tests**. The preview-envelope regression reused an existing test.
- [Final Linux run](linux-module-tests.txt): **119 passed in 43.66 seconds**, covering 47 gateway and 72 chat cases. Five additional gateway cases ran separately on Windows without application/image changes; they are not included in 119.
- [M5 regression](m5-regression-tests.txt): **42 passed** against actual PostgreSQL, including version-conditional status updates. Its one dependency warning is retained in the output.
- [Live checker](cluster-results.json): twelve runtime groups passed. Raw status remains `PASS_RUNTIME_REVIEW_PENDING`; this review supplies the separate derived verdict. Commands and reproduction are in the [runbook](runbook.md); checker output is [saved separately](cluster-check-output.txt).
- [Image source comparison](image-source-check.json): 35 runtime files matched; [exported configuration](image-identity.json) and [actual Pod image IDs](runtime-image-check.json) agree on `sha256:48a2f637063bb048b6bc16f25b2ee91b9302756c5a926659af8c548386970573`.

## Criterion mapping

| Criterion | Verdict | Evidence and interpretation |
|---|---|---|
| M6-01: one endpoint and three upstreams | PASS | Real SDK/TCP fixtures and cluster checker initialized MCP `2025-11-25`, listed six tools and routed all three authentication modes. Host fixtures exercise JSON and stateful SSE upstreams; downstream is intentionally stateless JSON. |
| M6-02: collision-safe names | PASS | Host cases cover duplicate names, stable prefix/hash aliases, unsafe/reserved/long names and injected alias collisions. A failed new snapshot cannot replace another server's mapping. |
| M6-03: discovery completeness and bounds | PASS | Multi-page transport fixtures plus repeated-cursor/page/tool-count cases, malformed/unsafe schema rejection and incremental response/SSE bounds. Invalid discovery does not publish a partial catalog. Supported-schema/name limitations are explicit. |
| M6-04: static credentials and secrecy | PASS | Fixture-side header assertions distinguish none/bearer/custom-header modes and reject caller-cookie forwarding. Actual wrong bearer/header TCP cases return safe `UPSTREAM_AUTH_FAILED`, set `Unreachable/AUTH_FAILED`, execute zero fixture tools and create one error attempt. Echoed credential and child-logger regressions pass; the cluster checker saved zero credential matches. |
| M6-05: external authentication and revocation | PASS | Missing/wrong keys and cookie-only MCP requests are rejected; a retained SDK client loses access after B's revocation. Live next call returned 401 with attributed `KEY_REVOKED`. Stateless downstream provides no transferable session authority. |
| M6-06: internal identity and final dispatch check | PASS | Genuine session path, forged-proof/invalid-session zero-submission tests and a final-boundary revocation barrier. Forged identity is not attributed to its claimed user. M5's proof/owner checks are reused. |
| M6-07: configuration invalidation | PASS | Version-conditional status regression, stale-disabled direct-call denial, fresh listing shrink to four tools and delayed discovery after disable. Router rereads current enabled/version state under the ordering lock; obsolete metadata cannot authorize a new destination. |
| M6-08: failure isolation and timing | PASS | Live listing took 0.066 seconds, timeout 10.031 seconds, outage status 1.129 seconds. A separate real-TCP host case completed a healthy peer in under two seconds while another call remained slow. Recovery restored the header fixture and its successful call. These measurements concern controlled fixtures. |
| M6-09: one audit lifecycle and uncertainty | PASS | Host begin/finalization failures, cancellation before/after submission, late begin, invalid input and output-schema regressions; live success/error/timeout/denial/running rows. Audit-start failure dispatched nothing; finalization failure withheld success. Persisted recovery remains M5/M10, not this in-memory harness. |
| M6-10: safe previews | PASS | Session-authenticated pagination, valid request-ID error envelope, connected/stale/disabled/never-discovered cases. Preview data contains no Secret reference or hidden member connection settings. |
| M6-11: checked destination transport | PASS | Deterministic mixed/private DNS and checked numeric-dial tests; real TLS fixture accepts the original hostname and rejects a mismatched certificate name. Redirect/compression/reference restrictions and explicit no-proxy configuration were inspected. These establish the reviewed connector boundary, not immunity to every malicious upstream. |
| M6-12: Kubernetes and cleanup | PASS | Four available Deployments with probes/resources and no ServiceAccount token, internal ClusterIP Services, actual controlled upstream replacement, network denial and final cleanup/preservation checks. No public Ingress was added. |

## Kubernetes observations

The [saved resources](cluster-resources.json) show startup/readiness/liveness probes and the reviewed resource budgets for gateway and three fixtures. [Network evidence](network-denial.json) records allowed HTTP 200, denied `ConnectError` in 0.408 seconds, then allowed HTTP 200. A preliminary diagnostic assumed denial must be `ConnectTimeout`; that assumption was corrected in the checking helper. It was not an application failure or a failed twelve-group acceptance run.

The controlled header Pod changed from UID `781d7ac1-e531-4121-ba05-17004cc93ede` to `8f5e3644-24c4-4b2f-8756-c1c5e434bc5e`. Other peers and gateway readiness continued working. The [raw checker result](cluster-results.json) records removal of the owned test namespace. Root's [independent final resource comparison](final-root-check.json) confirms seven retained identities unchanged and the owned M5/M6 namespaces absent. The [shop status](final-shop-status.txt) shows both original shop Pods ready with zero restarts and all three retained PVCs Bound.

## Corrections and remaining limits

Implementation review corrected late-audit double-record risk, stale mapping/version pairing, SDK error normalization, invalid-output false success, child-logger leakage, multiline SSE bounds and request-ID typing. Regression evidence supports these corrections. Bounded schema validation rejects reference-driven/unsafe-regex schemas instead of fetching or executing them; this compatibility limitation must remain documented.

No application defect remains open in this review. M6 intentionally uses stand-in identity, registry, credential and audit adapters; it does not prove durable real-M5 dispatch, actual WooCommerce/Inventory/Microsoft Learn integration, browser behavior, Codex/Inspector acceptance or VPS operation. Those are later module/M10 checks. The original shop and its disks were preserved.
