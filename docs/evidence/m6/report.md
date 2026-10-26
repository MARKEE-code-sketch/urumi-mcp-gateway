# M6 gateway implementation evidence

**Status:** Implemented; host, Linux and all 12 live Kubernetes check groups PASS. Independent review: **PASS for all 12 module criteria**; user acceptance remains pending. This report does not claim the final system works end to end.

M6 gives clients one MCP endpoint, combines enabled upstream tools, routes names to the correct server and coordinates one audit attempt per execution. Chat receives the same safe catalog and calls the same three-argument executor. Personal gateway keys and browser identities are checked independently; upstream credentials stay inside the backend.

## Observed checks

| Check | Observed result | Evidence |
|---|---|---|
| Host protocol/lifecycle/TLS suite | 41 PASS in 36.92 seconds | [host-tests.txt](host-tests.txt) |
| Additional catalog limits/collisions/stale recovery | 6 PASS in 5.23 seconds | [host-catalog-tests.txt](host-catalog-tests.txt) |
| Concurrent peer isolation and internal identity denial | 3 PASS in 9.10 seconds | [host-isolation-identity-tests.txt](host-isolation-identity-tests.txt) |
| Actual wrong upstream credentials | 2 PASS in 11.09 seconds; safe AUTH_FAILED, zero tool submissions | [host-upstream-auth-tests.txt](host-upstream-auth-tests.txt) |
| Linux M6 + M7 suite | 119 PASS in 43.66 seconds: 47 M6 and 72 M7 | [linux-module-tests.txt](linux-module-tests.txt) |
| Actual PostgreSQL M5 regression, including conditional status | 42 PASS in 47.39 seconds; one upstream deprecation warning | [m5-regression-tests.txt](m5-regression-tests.txt) |
| Linux dependencies | `pip check`: no broken requirements | [linux-pip-check.txt](linux-pip-check.txt) |
| Image/source parity | 35 runtime/dependency/schema files matched | [image-source-check.json](image-source-check.json) |
| Live Kubernetes | 12 runtime groups PASS; original identities unchanged; no saved credential matches | [cluster-results.json](cluster-results.json), [audit/status](cluster-audit-status.json) |
| Network enforcement | Allowed gateway call -> denied fixture egress -> allowed gateway call | [network-denial.json](network-denial.json) |
| Runtime image | All four observed Pods matched the verified configuration digest | [runtime-image-check.json](runtime-image-check.json) |
| Helm | Lint and local/production render artifacts saved | [helm-lint.txt](helm-lint.txt), [local](render-local.yaml.txt), [production](render-prod.yaml.txt) |

There are **52 distinct M6 host cases**: the first 41, six catalog cases, three isolation/identity additions and two actual upstream-auth failures. The final preview-error UUID assertion reuses an existing method, so it adds no distinct case. The last five additions were host-only and do not increase the recorded Linux count. Linux M7 checks are reported separately by its owner; the combined total is not 119 M6 tests.

Observed host commands:

```powershell
& .tools/m6/venv/Scripts/python.exe -m pytest tests/gateway -q --assert=plain -p no:cacheprovider --basetemp .tools/m6/pytest-final-approved
& .tools/m6/venv/Scripts/python.exe -m pytest tests/gateway/test_catalog_edges.py -q --assert=plain -p no:cacheprovider
& .tools/m6/venv/Scripts/python.exe -m pytest tests/gateway/test_lifecycle.py -k 'healthy_peer or internal_identity' -q --assert=plain -p no:cacheprovider
& .tools/m6/venv/Scripts/python.exe -m pytest tests/gateway/test_gateway.py -k 'actual_wrong_upstream' -q --assert=plain -p no:cacheprovider
```

The first host command preceded the six catalog and three isolation/identity additions and two upstream-auth cases. A separate targeted preview-envelope regression passed after the last small API correction. Temporary certificate creation required pytest outside the filesystem sandbox; no credential-bearing output was saved. Reproduction and executed cluster commands are in the [runbook](runbook.md).

## What the checks prove

- Real SDK clients connected over TCP through the gateway to three controlled servers, with no credential, static bearer and named API-key header modes. JSON and stateful SSE upstreams were exercised; the downstream gateway is stateless JSON Streamable HTTP.
- Discovery reads pages, rejects repeated cursors and page/tool bounds, assigns stable case-sensitive public/hash names, detects collisions and does not invent tools for a never-discovered dead server. Old discovery cannot publish after a configuration edit. Last valid metadata becomes stale on failure and recovers on success.
- Keys are checked on every request and before submission. An existing client fails after revocation; fabricated internal principals and invalid sessions make no tool submission. A queued final-boundary revocation produces one denied attempt. Member and admin identities are separate in fixture audit rows.
- The executor preserves a sanitized upstream `isError` payload. Invalid input, unknown protocol tool, output-schema failure, audit-start failure and audit-finalization failure do not become false successful results. Cancellation after possible submission is unknown; cancellation while the audit start is delayed cannot create a second attempt.
- A healthy peer completed within two seconds while another call remained slow. That is measured concurrent isolation, rather than a healthy call performed only after an outage finishes.
- DNS fixtures reject mixed public/private answers, forbidden addresses and later rebinding. Numeric addresses are dialed after checking, with no second unchecked hostname lookup. A real test-CA TLS server succeeded for the original hostname and failed for a wrong hostname despite dialing the same address. Redirects, compressed replies, excessive bytes and oversized multiline SSE events fail explicitly.
- Echoed sentinel secrets are redacted from results; actual SDK child loggers and future descendants are suppressed. There are no full arguments/results or raw credential fields in fixture audit records. Those rows include UUID attribution, UTC timing and safe outcomes.

## Image and implementation details

Image: `urumi/gateway-check:m6`. The Docker-exported runtime configuration digest is `sha256:48a2f637063bb048b6bc16f25b2ee91b9302756c5a926659af8c548386970573`, verified from actual configuration bytes. This is distinct from an OCI index digest. The observed gateway and three fixture Pod image IDs matched this exact configuration digest; see `runtime-image-check.json`.

Core files are `backend/gateway/{server,discovery,router,upstream_client,context,schema,common}.py`. The small M5 seam adds keyword-only `expected_version` to status updates using the existing version column; actual PostgreSQL regression checks passed without a migration. The disposable harness has its own in-memory identity/registry/audit adapters; it does not secretly integrate M5 or use real shop credentials.

Implementation review found and corrected late audit-start duplication risk, old-version catalog mapping, SDK error/validation shortcuts, SSE multiline event limits, child logger propagation, UUID context typing, output-schema false success and wrapped final-boundary authentication denial. The final preview API errors include a trusted request UUID. These are implementation corrections within the approved module scope, not new features.

Schema handling uses an explicit supported subset: original names up to 200 characters; bounded schema nodes/depth/composition; no remote/local/dynamic/recursive references or patternProperties; only the five reviewed linear patterns. This avoids evaluating arbitrary upstream regex or recursive references. Validation runs in bounded workers. Unsupported metadata fails clearly without silently modifying its schema. Request values are bounded; compressed replies are explicitly rejected; uncertain binary credential safety returns an explicit content error. These interoperability limits must remain visible in documentation.

## Remaining acceptance boundary

The isolated `urumi-m6-check` runtime passed all 12 groups. Fresh external tool listing returned six tools in **0.066 seconds** (negotiated downstream protocol `2025-11-25`); the controlled timeout returned in **10.031 seconds**; sustained header-peer outage became Unreachable in **1.129 seconds**. Other peers and gateway readiness stayed usable. The header fixture was restored with a different Pod UID, Connected status and a successful fresh call. Disabling another fixture removed its tools and denied its previously known name; revocation returned HTTP 401 on the existing-client path.

Actual header Pod replacement: `781d7ac1-e531-4121-ba05-17004cc93ede` -> `8f5e3644-24c4-4b2f-8756-c1c5e434bc5e`. The network policy test observed allowed gateway -> bearer health HTTP 200, denied none-fixture -> bearer Service in 0.408 seconds (`ConnectError`, an immediate k3s rejection), then allowed gateway HTTP 200 again. An earlier checker expected only a timeout; correcting that assumption changed the checker, not the policy.

The raw result remains `PASS_RUNTIME_REVIEW_PENDING`; independent acceptance must derive its own verdict without rewriting measured history. The owned M6 namespace was removed after successful checks (`owned_namespace_removed:true`). The root closure check confirms both disposable M5/M6 namespaces absent and seven retained resource identities unchanged; original shop Pods are Ready with zero restarts and all three PVCs remain Bound. The [independent acceptance review](acceptance-review.md) and [derived results](acceptance-results.json) mark all 12 criteria PASS, with user acceptance pending. The final [artifact scan](final-artifact-scan.json) checked 36 saved M6/M7 files across UTF-8 and Windows UTF-16 encodings against the six actual generated fixture credential values: zero matches.

Even after M6 acceptance, M10 still owns real PostgreSQL-backed gateway integration, real WooCommerce/Inventory/Microsoft Learn aggregation, Inspector/Codex interoperability, browser pages and the live two-user flow. In-memory fixture rows do not prove persistence or real M5 lock coordination. This module does not expose a production endpoint or claim a VPS deployment.
