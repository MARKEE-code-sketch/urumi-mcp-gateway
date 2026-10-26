# Q10 rate-limit recurrence — 25 October 2026

**Subsequent manual sign-off, 26 October 2026:** the maintainer reported completing the entire manual checklist successfully. See [user-reported acceptance](../../manual-acceptance-20261026.json). The investigation and pending operator-verification state below describe this earlier checkpoint; no new operator-run model trace was supplied for the later sign-off.

Q10 is **reopened**, not marked Succeeded. The user's exact prompt failed after the previous successful live verification. A narrow retry correction has passed local tests and is deployed; fresh provider verification is pending approval.

## Verified failure

Request `348ed464-5f35-445f-9aa5-4180c0adf8a6` performed Learn search, fetch and another search successfully. A read-only dashboard API inspection matched all three user-supplied audit IDs and success outcomes. See `reported-request-audits.json`. The failed final response and rate-limit disclosure came from the user's transcript; chat answers/provider bodies are not persisted and were not reconstructed from audits.

The preceding implementation allowed one provider wait for the entire chat. After a successful retry on one completion, a new 429 on a later completion could not wait again. That is consistent with the transcript and was reproduced deterministically: the new separate-turn and maximum-attempt regressions failed against the previous code.

Each model turn resends the catalog and conversation. Local representative measurement found 12,108 bytes of definitions for eleven tools and 11,914 message bytes after three captured public Learn results. These are not exact provider tokens or the user's exact request. [Groq documents organization-wide rate limits](https://console.groq.com/docs/rate-limits); another user or application sharing that quota can also affect the result.

## Correction

`backend/chat/agent.py` removes the global once-per-chat retry flag. Its existing single exception handler now permits one header-directed retry per completion after tool activity. The retry is outside that handler, so another 429 on the same completion still fails.

Preserved: initial planning fail-fast; validated wait at most 60 seconds; original overall 120-second deadline; identity revalidation after every wait; identical messages, tools and final mode; no tool replay; unchanged model/provider and result limits. Maximum eight successful rounds and fifteen provider attempts. This neither extends the deadline nor supplies a fabricated answer when the provider fails.

Independent source/design review passed. Design: [q10-rate-recurrence-fix.md](../../../modules/q10-rate-recurrence-fix.md).

## Tests and deployment evidence

```powershell
.\.tools\m10\venv\Scripts\python.exe -m pytest tests/chat tests/e2e/test_runtime.py -q -p no:cacheprovider
```

**147 passed in 17.01 seconds.** Pre-fix targeted regressions: two expected failures, one passing deadline guard. Tests cover separate-turn waits, exact unchanged retry contexts, fifteen-attempt ceiling, same-completion repeated 429, original shared deadline, cancellation, revoked identity and no tool replay. See `tests.txt`.

Deployed backend: `urumi/backend:m10-q10-per-completion`. Build/source freeze and immutable image identity are recorded in this directory. `runtime.json` records a PASS for the actual Helm rollout, with all seven workloads Ready, the other six Pod identities and all three PVC identities preserved, and users/key metadata/registry unchanged. Forty-two runtime source files match the image input freeze. This is deployment evidence, not proof of a successful live Q10 answer.

## Remaining verification and limitations

Automatic approval review rejected the diagnostic Groq call because it would send a representative model conversation, chat instructions and gateway schemas to a third party. No diagnostic request was made. The user was asked for explicit permission; local tests, tool-audit inspection and the authorized Inventory failure tests continued independently.

No new provider-driven Q10 completion is claimed. Q10 remains FAIL/reopened pending live verification. The original successful run remains historical evidence in [the earlier report](../q10-learn-chat/report.md). A single request exceeding the available quota, persistent organization-wide quota exhaustion, an initial planning 429, or a wait that cannot fit the original deadline can still fail safely. This patch addresses the demonstrated retry-policy gap; it does not increase Groq's quota or guarantee completion.
