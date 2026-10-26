> **20 October update:** The previously blocked real Groq probe now passed after current free-plan confirmation: two provider rounds, 1.606 seconds. See [provider evidence](provider-probe.json) and the real [M10 browser flow](../m10/browser/report.md). Earlier pending statements below describe the original module checkpoint.

# M7 chat implementation evidence

**Date:** 18 October 2026. **Status: implementation complete; 72 host and 72 Linux chat checks PASS; independent source review has no remaining blockers. Module acceptance is BLOCKED on the unrun live-provider check.** No final application integration is claimed.

## What was built

M7 turns one signed-in user's message into bounded model requests and gateway calls. The model chooses tools; the gateway performs and audits them. Chat returns actual attempt references alongside its answer. It has no direct upstream MCP client, shop connection, saved transcript or personal-key recovery path.

| Area | Implementation |
|---|---|
| Chat loop | [agent.py](../../../backend/chat/agent.py): eight provider requests including final-answer opportunity, twelve gateway attempts, two active messages, no replay of uncertain actions. |
| Groq adapter | [llm_client.py](../../../backend/chat/llm_client.py): HTTPX, fixed 20b model/endpoint, bounded payload/response/time, zero retries or fallback. |
| Shop-day enforcement | [day_window.py](../../../backend/chat/day_window.py): captured Asia/Kolkata midnight/now bounds, exact first-page guard and bounded automatic pages. |
| Browser adapter | [api.py](../../../backend/chat/api.py): bounded input, session/Origin/CSRF checks, thread-pool identity work, disconnect cancellation and no-store responses. |
| Stand-ins | [fixtures.py](../../../scripts/m7/fixtures.py): real M5 Principal class with fixture proof, fake identity/gateway only; no database or upstream access. |

## Observed host verification

From the project root in PowerShell:

```powershell
./.tools/m6/venv/Scripts/python.exe scripts/m7/check-m7.py
```

Observed final host run **72 passed in 5.05 seconds**, exit 0, no warnings. The runner executes:

```powershell
./.tools/m6/venv/Scripts/python.exe -m pytest tests/chat -q --assert=plain -p no:cacheprovider
```

Evidence: [unit output](unit-output.txt), [machine result](unit-results.json). This uses the isolated M6/M7 dependency environment; the M5 environment is unchanged. An earlier 56-case exploratory run passed with a pytest cache permission warning; the reproducible runner disables that optional cache. Subsequent checks added sixteen regression/boundary cases, including the final source-review corrections.

Checks include two distinct users/proof rejection, exact product name/decimal price, cross-server tool sequencing, provider ID/result pairing, JSON and schema rejection, duplicate IDs/reordered write replay, round-eight answer reservation, timeout/unknown/audit failure outcomes, nullable unsaved audit IDs, midnight and UTC-date boundaries, automatic pages, repeated/out-of-window pages, incomplete results, byte/dispatch/catalog bounds, unsupported successful-write results, external annotation trust, and provider failures after a successful attempt.

HTTP evidence includes safe 401/403/429/5xx/redirect failures, zero retries, rejected compressed/oversized/truncated responses, provider-key scrubbing, API cookie/Origin/CSRF/input rejection, responsive health during blocking identity validation, actual ASGI disconnect cancellation, and a real loopback TCP read-timeout server. Fixture failures do not access a live shop or hosted model.

## Observed Linux verification

The root ran the frozen shared backend image's chat and gateway suites together: **119 passed in 43.66 seconds**, comprising **72 M7 chat checks and 47 M6 gateway checks**. [Combined Linux output](../m6/linux-module-tests.txt). The root also verified parity for 35 copied runtime files before cluster checks. This is independent Linux execution of the module suites; it is not a real-provider or final chat deployment test.

## Review corrections

The independent reviewer identified four early implementation gaps. They were corrected and covered by regressions: a later failed order page cannot become “all today's orders”; an observed successful write with unsupported content stays visibly successful with an uncertainty/display warning; cancelled synchronous threads retain the two-task capacity until they actually exit; and disconnect replies include no-store.

Synchronous work is tracked separately from active requests. Cancellation cannot kill a Python thread, so no new blocking operation is scheduled when two earlier operations remain outstanding. M6 remains responsible for its dispatch/audit cleanup and fencing. There is no promise that cancellation undoes a shop write.

Further review fixed the real M5 boundary requiring UUID objects for request IDs, added strict fixture checks for that boundary, and bounded schema/argument traversal. Chat now accepts only the two known linear owned-input patterns; arbitrary upstream regular expressions, cyclic/exploding references and unsupported schema keywords are rejected as explicit chat limitations. Schemas are capped at 16 KiB, 256 expanded visits and depth 10; generic schema/argument JSON has a 512-node/depth-20 cap. This prevents untrusted regex/reference work from defeating asynchronous deadlines.

Connection loss and invalid protocol replies can occur after a remote write. Those errors now conservatively stop the message with an uncertainty warning, even when the gateway's audit outcome is `error`; a modified model retry cannot bypass this rule. Final reviewer source verdict: no remaining blockers. Runtime acceptance still requires the separate provider evidence below.

## Pending evidence and limits

The real Groq check is prepared and intentionally has not been run while current free-account confirmation is pending. Its key will be read in memory from explicitly supplied runtime configuration or the ignored host `.env`; key values are never printed or saved. The check calls a fake gateway only. Historical M0 provider success is not reused as an M7 PASS.

Source review and Linux checks are complete; **C7-11 remains BLOCKED** awaiting current free-account confirmation and the actual Groq probe. No provider call was made. No M7 Kubernetes workload or provider Secret was created by this module. Root owns shared chart/image verification. M10 still owns real PostgreSQL/gateway/upstream wiring and the two-user demonstration; M8 owns browser chat rendering.

The initial chat supports text/JSON results and explicit English “today” without status filters. It reports unsupported schemas/content and partial results honestly. Upstream prompt text remains untrusted; this is not a complete defence against every malicious-server/model trick. Only known owned reads bypass duplicate-write protection, regardless of external read-only annotations.
