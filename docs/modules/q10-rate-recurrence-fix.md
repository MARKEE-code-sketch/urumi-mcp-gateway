# Q10: rate limits on separate model turns

## Scope and evidence

The user repeated the exact Q10 prompt after the previous successful verification. Request `348ed464-5f35-445f-9aa5-4180c0adf8a6` failed after successful Learn search/fetch/search calls. Live audit inspection confirmed all three outcomes as success. The user-visible response reports a provider rate limit and that the one allowed wait had been used. The chat answer is not persisted, so its final response is user-provided evidence rather than reconstructed from tool audits.

The earlier fix handled a single rate limit anywhere in a chat. However, the model can encounter a new rate limit after another successful tool round. Each completion resends the current conversation and catalog. A representative local measurement with the current eleven tools found 12,108 bytes of tool definitions and 11,914 bytes of messages after three captured Learn results. These are bytes, not exact provider tokens or the failed request's exact input. Groq's [rate-limit documentation](https://console.groq.com/docs/rate-limits) explains that quotas are shared at organization level.

## Smallest design

WHAT: permit one header-directed retry for each model completion after tool activity, rather than one retry across the entire chat.

WHY: a successful retry on one turn must not consume the recovery opportunity for a later turn. Repeating a model completion does not repeat an already completed tool operation.

HOW: remove the global `provider_waited` guard in `backend/chat/agent.py`. The existing single try/except and one retry outside that handler already bounds each completion to two attempts. Keep initial planning fail-fast, delay validation (0–60 seconds), original overall 120-second deadline, identity revalidation after every wait, and identical messages/tools/final flag. A second 429 on the same completion still fails. There are at most eight successful rounds and fifteen provider attempts (one initial plus two for seven later rounds). Keep the deterministic rate-limit disclosure.

No schema shortening, model/provider change, paid fallback, forced early answer, fabricated summary, background continuation, tool replay or deadline extension. Generic per-tool and aggregate result bounds remain unchanged. A quota that remains exhausted can still prevent completion; a single oversized request cannot be repaired by waiting.

## Review and verification

Independent source/design review accepted this narrow change. Add regression tests that fail with the existing once-per-chat guard: two separate model rounds can each wait once; all seven later rounds remain bounded; later waits cannot reset the original deadline. Retain initial fail-fast, repeated same-completion 429, cancellation, revocation and no-tool-replay tests. Run the chat/runtime suite, then build/deploy the backend only after the Inventory fault tests have restored state.

Q10 remains FAIL/reopened until a new exact-prompt live chat is observed. Provider diagnostic/live verification requires the pending approval after automatic review rejected exporting the representative model context. Local tests and F4/F5 do not depend on that approval.
