# Q10 manual finding: Learn succeeds, chat cannot finish

**Subsequent user sign-off, 26 October 2026:** the maintainer reported completing the full manual checklist successfully. This is [user-reported acceptance](../manual-acceptance-20261026.json), without a new operator-run request/audit trace. The earlier observations below remain historical evidence.

**Reopened 25 October 2026:** an earlier exact-prompt live run succeeded, but the user's subsequent request `348ed464-5f35-445f-9aa5-4180c0adf8a6` failed with a provider rate limit after three successful Learn calls (search, fetch, search), including one provider wait. The requested summary was not delivered. Matching user-reported audit IDs: `2a84c6cf-8f23-4047-a767-b5f94230c005`, `6c31b46b-5585-4c53-99b0-7ac7c4aafcad`, `f3d5851b-3830-445f-a4ba-dc7b7fe3dfd8`. The earlier [fix and verification report](../fixes/q10-learn-chat/report.md) records a successful observation, not proof of reliable completion under the provider quota. Investigation is ongoing. The original 23 October finding below is retained as history.

**Date:** 23 October 2026. **Evidence source:** User-pasted dashboard transcript, followed by read-only source inspection. No new provider/tool requests executed.

| Part | Observed |
|---|---|
| Prompt | Use Microsoft Learn to find official documentation explaining Kubernetes Pods. Summarise the result and provide the source links. |
| Gateway tool | learn__microsoft_docs_search; one attempt, successful. |
| Chat | Limit reached; no requested summary or source links delivered. |
| Displayed explanation | The gateway reported success, but chat could not display the complete result. Do not repeat the write. |
| Q10 result | FAIL for the requested complete chat journey; upstream execution succeeded. |

## Source findings

- backend/chat/agent.py result_text rejects encoded per-tool results exceeding 32 * 1024 bytes with CHAT_LIMIT and state limit_reached. This matches the reported path; actual response bytes and the running image were not inspected in this triage.
- Its READS set recognizes selected WooCommerce and Inventory tools only. The Learn tool is therefore conservatively treated as a possible write for replay protection and error wording. This explains the misleading write warning; the user's request was a documentation search.
- Asking the final answer to be shorter does not by itself avoid a limit applied before the result reaches the model.

## Proposed follow-up

Review bounded handling of large external search results with explicit partial-result disclosure, preserving gateway protocol results and existing safety limits. Improve error wording so an unknown external operation is not asserted to be a write. Design/review approval and implementation verification remain separate steps; no code or limits changed here. Retest the exact Q10 prompt after a fix.
