# Q10 Learn chat fix

**Historical successful run; Q10 reopened after a later failure.** User retest `348ed464-5f35-445f-9aa5-4180c0adf8a6` failed after three successful Learn calls and the single permitted provider wait. See [current investigation/design](../../../modules/q10-rate-recurrence-fix.md). This report preserves the earlier observation, not a guarantee of reliable completion.

Verified on **25 October 2026**, local `urumi-m10`, Helm revision **17** at the time. The exact original prompt produced a completed dashboard response, a summary, rendered official source links and matching successful Learn audits in that run.

## Observed cause and changes

The initial captured Learn search included the same JSON as text and structured content. Chat counted both:44,744bytes in the presentation payload. Lossless canonical deduplication reduced it to21,249bytes with all10 results intact. This fixed the original32KiB result-limit failure without changing gateway responses.

Live testing then exposed provider limits. Dedup-only and intermediate8KiB search views still failed at the model-provider stage. A diagnostic observed an8000tokens/minute limit, and the4KiB live run later explicitly returned PROVIDER_RATE_LIMIT after two successful searches and one fetch. Earlier failures without an explicit rate code are not retroactively labelled observed429s.

The final implementation:

- `backend/chat/agent.py`: canonically identical single JSON text/structured copies are represented once for the model. Distinct values, multiple blocks and malformed text remain available. Unknown successful operations whose results cannot be displayed warn about repeating an **action**, rather than assert a write.
- `backend/chat/search_results.py`: only the observed successful documentation-search shape receives a bounded ranked excerpt view. Whole presentation≤4KiB including metadata; titles≤256UTF-8bytes, content≤384bytes, full URLs preserved. Mixed/error/unsupported shapes fall back to existing handling. The captured real result retained6of10 sources in3551bytes, with a deterministic visible N-of-M excerpt notice. Original gateway content is unchanged.
- `backend/chat/prompts.py`: asks the model to summarize relevant documentation results rather than rephrase the same search, and not claim full-page reading unless a fetch happened. No hard stop prevents legitimate refinement or cross-server use.
- `backend/chat/llm_client.py`:429 now has clear rate-limit feedback. A validated0–60second hint comes only from Retry-After or the token-reset header; raw error bodies are not read. [Groq documents these rate-limit headers](https://console.groq.com/docs/rate-limits).
- `ChatAgent`: after at least one tool attempt, one bounded asynchronous provider-completion wait/retry is allowed per chat if the header delay fits the existing120second deadline. Identity is revalidated after waiting. The identical model context is retried; gateway calls are not replayed. Planning429, absent/invalid hints, repeated429 and other errors fail safely. At most8 successful rounds/9 completion attempts, no paid/provider fallback or background continuation.

The32KiB per-tool and96KiB accumulated hard limits, authentication, read/write classification, unknown-operation replay guard, tool-call cap and audit semantics remain intact.

## Final live verification

Exact prompt:

> Use Microsoft Learn to find official documentation explaining Kubernetes Pods. Summarise the result and provide the source links.

Observed **state `completed`**. Actual calls:

1. `learn__microsoft_docs_search` — success.
2. `learn__microsoft_docs_fetch` — success.

The rendered response includes a readable summary/table and two working-style HTTPS source anchors to Microsoft Learn. It discloses shortened search excerpts from6of10 results. Both actual call audit IDs correlate with reply request `186564d9-90df-41fa-a990-eeb82c479c33`, signed-in admin session and the Learn server. The final live run did **not** need the optional rate wait; that path is covered by controlled regression tests, not falsely claimed exercised by this final run.

Evidence: [actual final reply](live-chat.json), [rendered screenshot](live-chat.png), [audit correlation](audit-correlation.json), [dedup measurement](dedup-measurement.json), [excerpt measurement](excerpt-measurement-4k.json), [provider diagnostic](provider-diagnostic.json), [immutable runtime/source checks](runtime.json).

## Tests and deployment

**145 chat/runtime tests passed in10.04s.** Regressions cover lossless deduplication, strict JSON type differences, retained source URLs/ranked excerpts/UTF-8/whole budget/source immutability, unsupported shapes, unchanged hard limits, replay protection, header-only bounded wait hints, one completion retry/no tool replay, initial and persistent provider failures, cancellation, identity revocation and deadline/round bounds.

```powershell
.\.tools\m10\venv\Scripts\python.exe -m pytest tests\chat tests\e2e\test_runtime.py -q -p no:cacheprovider
node scripts\m8\check-q10-learn.mjs
```

An early timing-sensitive health test failed under build load and then passed alone and in the full suite without application or assertion weakening. New wait/deadline fixtures use deterministic2second test deadlines to avoid expiring before their intended phase under Windows scheduling load. Final145 passed.

Built/deployed `urumi/backend:m10-q10-rate-wait`, immutable index `sha256:89402aea206a1373776bf66fb0b494f140cca224a12380980c2f08bdd2fedb8b`. All42 runtime backend/contract source files matched the43-file input freeze (the extra input is root Docker ignore policy). Only backend image tag/digest changed in each Q10 rollout. Existing dashboard image, repaired API CIDR, shop, users/keys/registry/PVC identities and other six Pods were preserved at each rollout.

Failed live trials/build identities remain under `dedup-only/`, `excerpts-8k/`, `excerpts-4k/`, and the earlier named live-chat JSON/screenshots. Their failures are not presented as passes. Final [combined state](../final-state-20261025.json):7Ready workloads,3Bound existing PVCs, zero pending registration operations/test aliases. User-added Context7 was left unchanged; no claim that its upstream is reachable.

## Limits

The provider's quota is shared and may still be exhausted by concurrent use, oversized requests, persistent429, absent/long wait hints or a deadline. The implementation does not promise every free-plan request succeeds; it bounds context, permits one safe completion wait and reports remaining failures clearly. No provider/model/key upgrade or payment setup was performed. No new full M10 acceptance, VPS deployment or submission claim.
