# Q10 chat result handling

User requested fixing the recorded Q10 Learn failure on25October2026. Existing report: [finding](../evidence/manual/q10-learn-chat-limit.md).

## Evidence and smallest design

A real gateway Learn search returned one JSON text block and structured search results, around44.9KB combined; the text alone was22.8KB. Chat's current32KiB per-tool budget counts both representations. First verify exact canonical JSON equivalence, then retain one complete structured representation rather than duplicating it in model context. This is lossless: source links/results remain intact, no truncation or partial-result claim, and the32KiB per-tool /96KiB accumulated limits stay unchanged.

`backend/chat/agent.py` owns the existing `result_text` presentation boundary. Remove the text copy only when a single JSON text block is canonically identical to structuredContent. Distinct payloads (including JSON true versus1), other blocks and malformed/non-JSON text must not be silently discarded. Do not mutate gateway results, schemas, audit outcomes, read/write classification or retry behavior. Unique oversized results still stop safely with explicit limits. If actual live results remain oversized after deduplication, review a separate bounded projection rather than raising all limits.

For an unknown operation whose successful result cannot be displayed, keep replay caution but say “action” rather than asserting it was a “write.” Preserve known write/unknown-operation replay guards; untrusted readOnlyHint is not permission to replay.

## Live-provider follow-up

The dedup-only release cleared the original32KiB failure, but the first exact-prompt chat attempt still received a provider-unavailable result after a successful Learn call. A separate safe provider diagnostic succeeded while leaving1307 of its8000tokens/minute budget, showing little room for the preceding planning round. The precise rejection status of that first production request was not captured; rate pressure is an inference, not a claimed observed429.

Add `backend/chat/search_results.py` as a bounded presentation adapter only for successful `microsoft_docs_search` results with the observed exact title/content/contentUrl schema and no distinct text copy. The final presentation budget is4KiB: a ranked prefix of at most10 records, titles up to256UTF-8bytes, excerpts up to384bytes, full unchangedURLs, with metadata included in the limit. Mixed/malformed/error results and an unfit first source fall back to existing handling. Display a deterministic note stating how many returned results supplied shortened excerpts. Keep gateway content, audit outcomes,32/96KiB hard limits and replay classification unchanged. The intermediate8KiB trial and its provider failure are retained as historical evidence.

The4KiB live run completed two searches and one fetch but then explicitly hit PROVIDER_RATE_LIMIT. [Groq documents Retry-After on429 responses](https://console.groq.com/docs/rate-limits). `GroqClient.complete` still sends one HTTP request and returns only a validated0–60second header-derived retry hint on429; no raw error body is read or exposed. After at least one tool attempt, `ChatAgent` may asynchronously wait and repeat that same provider-completion request once per chat, only if the delay fits the original120second deadline. Revalidate identity after the wait; preserve messages/tool catalog/final mode and do not repeat gateway tool calls. Planning failures, absent/invalid hints, later429s, provider timeouts and other errors stop as before. Eight successful rounds and at most nine completion attempts, no provider/model fallback or background continuation. A deterministic note discloses rate limiting and preserved tool executions. The overall deadline still cancels the wait/request normally.

## Verification

Reproduce the duplicated-size failure with a realistic search fixture, test strict equivalence/distinct data, source immutability, full source-link retention and unchanged hard limits; run the existing chat safety suite. Build the pinned backend release image and deploy only that image with current Helm values. Verify the exact Q10 prompt through actual dashboard chat and match Learn tool success/audit, completed summary and links. Preserve state and separate provider availability/quotas from successful tool execution. No claim of complete chat success based only on unit tests.

Implemented and live verified25October2026:145 chat/runtime tests passed; exact Q10 prompt completed with successful Learn search/fetch, rendered summary and2source links. [Final evidence and limits](../evidence/fixes/q10-learn-chat/report.md).
