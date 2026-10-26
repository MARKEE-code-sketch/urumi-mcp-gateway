# M0 independent implementation review

**Date:** 14 October 2026. **Verdict:** Local disposable experiments are suitable for user review; **M0 acceptance remains BLOCKED/incomplete**. This review does not approve M1 or application implementation.

## Scope and evidence

Read experiments/m0, tests/m0, the shared contracts, sample fixtures, dependency lock, and saved M0 evidence. Reviewed the implementation and existing results; did not rerun commands, install dependencies, read .env, use provider credentials, or change application code. The acceptance skill evidence rules were applied: missing runtime evidence stays unverified.

The saved test-results.json records 14 passing tests, zero failures/errors, no recorded ResourceWarnings, and negotiated MCP protocol 2025-11-25 using mcp 1.26.0. This is observed output from the main agent run, not an independent rerun. Tests cover formal schemas, sample envelopes, input rejection, localhost Streamable HTTP initialize/list/call, three-page discovery, bearer/custom-header/no-auth modes, safe execution errors, unknown tools/cursors, cancellation, reconnect, and stateful-session termination.

## Code findings

No material blocking defect found in the reviewed disposable fixture scope. The fixture binds loopback, uses only a visibly fake public key, authenticates HTTP requests before dispatch, and makes no real shop writes. Input validation and safe errors agree with the contracts. Handling request=None in list_tools is necessary for the SDK internal direct-call path; the dedicated call-before-discovery test covers it. This callback compatibility workaround and manual handler guard are experiment-specific; review them again before reusing code in a production component.

The slow-call test proves client cancellation and a separate fixture endpoint remaining usable. It does not prove future gateway timeout isolation, revocation, identity binding, or durable audit behavior. Those remain M5/M6 acceptance work. Shop filtering, order boundaries, writes, and persistence are represented by samples, not real WooCommerce evidence.

The model probe deliberately returns before reading .env without free-plan confirmation and checks unauthenticated reachability first. It bounds calls/rounds, validates the only allowed fixture action, and avoids storing raw exception/provider bodies. Google currently reports GOOGLE_ADAPTER_DEFERRED; it is not a functioning fallback. Default model IDs and a confirmation flag do not themselves establish account quota or free billing.

## Remaining M0 checks

| Check | Current evidence | Next requirement |
|---|---|---|
| Real-model tool loop | BLOCKED: FREE_PLAN_NOT_CONFIRMED; no key read or provider request | Verify approved free account/model access, restore network access, then capture a real tool request, fixture result, and final answer. |
| Codex compatibility | Untested | Isolated user-B-style client using only fixture URL/key; discovery, call, session/auth behavior. Real gateway two-user evidence remains M10. |
| Inspector CLI | Saved list/call payloads exist, but both processes exited 3221226505 with Windows Node UV_HANDLE_CLOSING assertion; report currently FAIL | Complete the pending rerun and record its exact command/runtime/exit status. A returned payload alone is not a clean passing process. This is CLI evidence, not visual Inspector proof. |
| Microsoft Learn | BLOCKED: Windows access-denied error 5 during connectivity/protocol probe | Run initialize/list from an allowed environment; save discovered schemas and distinguish discovery from a tool call. Independent real tool call belongs to M4. |
| Repeatable dependencies | Exact Windows/Python 3.13.5 version snapshot saved | Verify clean installation from lock before claiming reproducibility. This lock is not the Linux/application image lock. |

Network access failures do not identify invalid provider credentials or a broken hosted server. Docker/Kubernetes readiness remains separate and unproved.

## Gate

Present local results and limitations to the user. Resolve or explicitly review remaining M0 acceptance gaps before marking M0 complete; do not treat local fixtures as the real-model/client or final system demonstration. M1 requires its own user approval after M0 review.
