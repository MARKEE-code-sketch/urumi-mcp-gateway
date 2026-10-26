# M7 independent acceptance review

**Date:** 18 October 2026. **Verdict: BLOCKED on the required real-provider check.** Eleven criteria pass at the independent-module boundary; C7-11 has no current real Groq evidence. Source review found no remaining implementation blockers. User acceptance remains pending.

The reviewer applied the project's MCP/Kubernetes acceptance skill and inspected the assignment, approved specification/design, chat source, deterministic test source and saved outputs. Review did not call Groq, modify application code or change live resources.

## Evidence reviewed

The [host runner output](unit-output.txt) records **72 passed in 5.05 seconds**, exit 0; [machine result](unit-results.json) identifies the fixture/TCP/ASGI boundary. The shared [final Linux run](../m6/linux-module-tests.txt) records **119 passed in 43.66 seconds**, including those 72 chat cases and 47 gateway cases. The final [runtime-source comparison](../m6/image-source-check.json) includes the chat files. Historical M0 provider success is not an M7 result.

Reproduction uses the commands in the [runbook](runbook.md), including `.tools/m6/venv/Scripts/python.exe scripts/m7/check-m7.py`. The optional `--live-provider --confirm-free-plan` mode has not been executed: current account/free-use confirmation is still missing. No paid fallback is authorized.

## Criterion mapping

| Criterion | Verdict | Evidence and interpretation |
|---|---|---|
| C7-01: API protection and inputs | PASS | ASGI checks reject missing session, bearer-only authentication, wrong Origin/CSRF, blank/extra/oversized fields with zero inference/tools. Valid protected requests work; replies are no-store. |
| C7-02: identity and revalidation | PASS | Proof-backed fixture principals stay distinct for A/B; forged identity and expiry between model/dispatch prevent execution. Trusted request context carries a UUID compatible with M5 audit, rather than caller JSON. |
| C7-03: product creation | PASS | Scripted model requests the exact product name and decimal-string price once; visible activity references the gateway attempt. This is a fake-gateway write, not a storefront change. |
| C7-04: today's orders | PASS | Frozen-clock shop-midnight/UTC-date/empty/multiple-page cases; code enforces fixed bounds, initial page and no status filter. Failed/repeated/out-of-window/over-budget pages produce backend partial warnings rather than model claims of completeness. |
| C7-05: cross-server dependency | PASS | Product lookup supplies its observed SKU to Inventory using distinct gateway names and the same principal. Warehouse data remains explicitly sample data. |
| C7-06: catalog/content compatibility | PASS | Catalog refresh, unsupported schema/content disclosure, malformed/unknown calls, byte limits and reserved final round. Unsafe regex/reference expansion is bounded or rejected; schemas are not silently rewritten. |
| C7-07: audit and uncertain outcomes | PASS | Success/error/denial/timeout/unknown and audit-start/finalization failures retain honest activity, including nullable unsaved audit IDs. Duplicate writes and connection/protocol uncertainty stop further actions. M7 does not create a second audit store. |
| C7-08: budgets/cancellation | PASS | Eight provider requests, twelve actual dispatches, two messages, bounded retained blocking tasks, content caps, provider stall and actual ASGI disconnect checks. Cancellation stops later dispatch; it cannot undo an already submitted write. |
| C7-09: provider failures | PASS | HTTP fixtures and a real loopback TCP timeout cover authentication/rate-limit/5xx/invalid/compressed/oversized/truncated replies. Earlier activity remains visible; no retry/fallback or raw provider-body exposure. These are controlled failures, not hosted-provider availability evidence. |
| C7-10: credentials/trust boundary | PASS | Provider-key payload/output scrubbing, fixed backend identity, schema-rejected overrides and external read-only annotation distrust. Chat calls only the injected gateway and never reads upstream credentials or opens MCP connections. This is not a complete prompt-injection defence. |
| C7-11: real Groq loop | BLOCKED | No implementation-time `provider-probe.json` with a real model-requested call, consumed fake-gateway result and consistent final answer exists. Current free-account confirmation is required before the prepared explicit probe. A fixture or old M0 result cannot substitute. |
| C7-12: module/deployment boundary | PASS | Independent host and Linux suites, API/provider cleanup and shared image parity reviewed. No separate permanent chat workload or provider Secret was created; final Helm/provider configuration and browser wiring remain M9/M10. |

## Corrections and remaining work

Review corrections are covered by regressions: a failed later order page cannot become all-day success; unsupported successful-write output preserves the observed success warning; cancelled synchronous work retains capacity; disconnect replies are no-store; request UUIDs match the real M5 contract; schema CPU/reference bounds and conservative lost-reply write handling prevent unchecked replay. No remaining source defect is identified.

To close C7-11, confirm current free-use account access, run the prepared real Groq probe once against the fake gateway, then inspect its sanitized model/call IDs, expected/executed arguments, result-dependent answer and duration. A quota/auth/network failure must remain an explicit gap. Neither this review nor a future fake-gateway provider PASS proves real shop changes, PostgreSQL audit attribution through the integrated gateway, the browser chat experience, the external-client demonstration or VPS operation.
