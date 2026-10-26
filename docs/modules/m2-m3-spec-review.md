# M2 and M3 specification review

**Date:** 15 October 2026. **Reviewer:** independent subagent m2_m3_specs_review using mcp-gateway-spec-review.

**Verdict:** READY FOR USER REVIEW — no blocking issues in M2, M3, or their parallel coordination plan. User approval remains pending.

Reviewed assignment DOCX, AGENTS.md, blueprint M2/M3, M0 tool contracts and schemas, decisions, both specifications, and the parallel plan. Verified official WooCommerce authentication guidance.

| Document | Finding |
|---|---|
| M2 specification | Persistent database/content, real checkout/admin order/image, separate Pod replacements, Secrets and independent REST preparation covered. |
| M3 specification | Five M0 tools preserved; real MCP against fake REST, strict input/output contracts, date/pagination, deadlines, failures, redaction and internal network boundary covered. |
| Parallel plan | Separate module files and proposed test release/namespace; root owns shared chart changes; no same-release concurrent Helm upgrades; explicit cleanup and design gates. |

Shared REST authentication (HTTP signed OAuth versus trusted HTTPS Basic) remains explicitly unresolved before design approval. Canonical URL, API path, Secret shape and caller boundaries are joint handoff items. M3 fixture results cannot prove real WooCommerce integration; M10 retains that check.

No tests, installation, application code, provider calls, or cluster changes performed during this review.
