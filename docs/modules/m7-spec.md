# M7 specification - chat tool loop

**Status:** Specification and concrete design approved on 18 October 2026; implemented with 72 host and 72 Linux chat checks PASS and independent source review finding no remaining blockers. Module acceptance is BLOCKED on the unrun real-provider check; see section 12.  
**Date:** Specification 17 October 2026; concrete design 18 October 2026.  
**Sources:** Assignment DOCX; [blueprint M7](../../blueprint.md#m7-chat-tool-loop); [decisions](../decisions.md); [platform API](../../contracts/platform-api.md); [identity and audit](../../contracts/identity-and-audit.md); [tool agreement](../../contracts/mcp-tools.md); [M5 specification](m5-spec.md); [M6 specification](m6-spec.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Build the Python chat agent that turns a signed-in person's message into tool calls and an understandable answer. Its reply also shows which tools actually ran and what happened.

**WHY:** The assignment requires a working chat agent in the dashboard. A model answering from its own knowledge cannot prove that it checked today's orders or created the requested product.

**HOW:** The backend verifies the person's login, obtains the gateway's current tool list, asks the model what to do, executes requested tools through the gateway, and gives their results back to the model. The model can then answer or request another tool. This repeated exchange is the **tool loop**.

Example: “Find the product with SKU DEMO-001 and check its warehouse quantity.” The model requests the shop lookup, reads the returned SKU, then requests the Inventory lookup. The response distinguishes real shop data from Inventory's sample warehouse data.

| Term | Meaning here |
|---|---|
| LLM / model | The language model that interprets the message and chooses tools. |
| Tool schema | The checklist describing a tool's arguments. |
| Principal | The identity M5 verified: user, current role and authentication source. |
| Gateway | M6's checked doorway to tools; it owns upstream connections and activity recording. |
| Provider | Groq, the external service running the selected language model. |
| Tool round | One exchange in which the model can request tools; its exact counting rule belongs to design review. |

M7 provides backend logic and an independently testable chat API adapter. M8 provides the visible chat page. M10 connects the real identity, gateway, provider configuration and dashboard.

## 2. Scope and existing decisions

| In M7 | Owned elsewhere / excluded |
|---|---|
| One-message, transient chat tool loop | Saved conversations, long-term memory and background agents. |
| Model request/response adapter and prompt | Training, retrieval databases and broad model-quality benchmarking. |
| Safe `/api/v1/chat` request and response behavior | Login/session storage M5 and browser chat screen M8. |
| Passing the genuine signed-in principal to M6 | Upstream MCP transport, routing, credentials, timeouts and tool audit lifecycle M6. |
| Recording actual gateway attempts in the chat reply | A second independent tool audit store or fabricated successful calls. |
| Fake-gateway tests and one real-provider check against that fake gateway | Real-shop writes and complete two-user demonstration M10. |

Confirmed stack: Python in the existing FastAPI backend. No separate chat microservice, database or Kubernetes workload is required. A Kubernetes **Secret** supplies the provider key, similar to giving a Docker container a private runtime credential; it is not part of the image or browser bundle.

Existing approved choices:

- Groq first; Google AI Studio free tier is the second option if needed. No automatic provider switch, paid use or paid fallback is authorized. Any change affecting cost/access needs user review.
- M0's real probe used Groq `openai/gpt-oss-20b` successfully on 14 October 2026. This is the starting candidate for M7 design, subject to a fresh availability/account check before its implementation-time live test.
- Maximum **eight model/tool rounds per message** was approved in M0. Exact counting and additional work/time bounds still need design review.
- Shop timezone is **Asia/Kolkata**; shop currency is **INR**. Audit timestamps are UTC.
- Both admin and member may use enabled tools, including product creation and order-status changes. Per-tool permissions are outside this core scope.

Only these two new module specs are created for M6/M7. After specification approval, detailed designs will be added inside the same files for review; implementation follows their approval.

## 3. Request and data path

1. A browser sends its message to `POST /api/v1/chat` with its login cookie and the required browser protections.
2. The API adapter obtains a genuine M5 principal. The browser cannot choose another user, role or key.
3. M7 obtains a fresh view of available tools through M6's read-only discovery adapter. It uses gateway public names and their discovered schemas.
4. The model receives the user's message, operating instructions and supported tool descriptions. Provider/upstream credentials and authentication objects are excluded.
5. If the model requests a tool, M7 sends its public name and argument object to `invoke_tool(principal, tool_name, arguments)`.
6. M6 rechecks identity and server state, creates the activity record, calls the upstream, finalizes the outcome and returns its safe result and audit reference.
7. M7 appends the actual attempt to `tool_calls`, supplies supported result content to the model, and continues within the approved limits.
8. The API returns an answer, terminal state and the list of actual attempts. Errors and partial results remain visible.

Only M6 opens upstream MCP connections. M7 does not read registry credential references, resolve upstream Secrets, sign WooCommerce requests, call upstream URLs or reconstruct a personal gateway key from its hash.

## 4. Functional requirements

### 4.1 Chat API and identity

- Implement the platform contract's `POST /api/v1/chat` behavior through a mountable adapter, without creating the final `main.py` or application orchestrator.
- Request body is `{ "message": "What orders came in today?" }`. Reject unknown fields and invalid/blank messages. The design must specify exact text/body limits compatible with M5's existing bounded request handling.
- Authenticate using the dashboard session, with allowed Origin and session-bound CSRF protection for this changing request. A personal gateway bearer key cannot substitute for a dashboard login.
- Use M5's actual proof-backed `Principal` contract and `Identity.revalidate` behavior. Never create a trusted principal from model/browser data or preserve permission after expiry/logout.
- Revalidate session/current account at protected entry and before every tool execution through the shared gateway path. If it becomes invalid during a message, dispatch no further tools and return an honest partial failure.
- Session cookies/tokens and private validation handles remain backend-only and never enter model messages, response bodies or logs.
- A fresh request carries no previous conversation history. Reject caller-supplied tool results or assistant messages; they are not part of the agreed request schema.

### 4.2 Tool discovery and model adaptation

- Obtain a fresh tool catalog for every new message. Disabled/removed servers contribute no usable tools; stale names cannot bypass M6's execution-time checks.
- Use the public gateway names and explicit mappings supplied by M6. Do not invent hosted tool definitions, split names to guess routes, hardcode Microsoft-specific routing, or expose upstream URLs/credentials.
- Adapt supported discovered input schemas to the provider's tool-calling format without changing their meaning. Clearly report tools that chat cannot use because the provider cannot represent their schema or content type.
- Validate model tool-call structure and JSON argument shape before dispatch. A malformed model call must not become a guessed or repaired write. M6/M3 remain responsible for authoritative tool/schema validation.
- Model-provided identity, URL, authentication or routing overrides grant no authority. Only advertised gateway tools and the verified principal can reach execution.
- Treat tool descriptions/results as untrusted information, not instructions that can override identity, permissions, credential rules or the user's task. Prompt text alone is not a guarantee against a malicious upstream.
- Feed supported, sanitized tool results back to the model. Do not silently drop unsupported content or present a truncated/partial result as complete. Exact size/content handling is a design item.

### 4.3 Tool loop and visible activity

- Support a final answer with no tools, one tool, and sequential calls across multiple servers. Required fixture scenarios are product creation, today's orders and WooCommerce-plus-Inventory lookup.
- Execute every actual call through `invoke_tool(principal, tool_name, arguments)` with the same signed-in identity. Correlation comes from trusted request context; there is no caller-supplied fourth argument.
- Preserve M6's `request_id`, `audit_id`, `outcome` and MCP `CallToolResult`. M7 does not create another tool audit row or finalize an M6-owned row.
- Distinguish a requested tool from an executed attempt. Never show a model's proposed call as successfully executed. A local malformed/unsupported request can be explained as a chat limitation without inventing a gateway audit ID.
- Pair every provider tool result with its originating requested call. Provider call IDs are correlation labels, never authorization; duplicate/replayed IDs or batches must not accidentally dispatch another attempt. Exact uniqueness scope and representation belong to design review.
- Return tool failures to the model in a safe, recognizable form and retain them in visible activity. A later successful answer must not hide an earlier denied/failed/timed-out attempt.
- Enforce the eight-round maximum. Provider failure or exhausted work budget returns an honest partial result; it cannot silently keep working in the background.
- Do not automatically replay an uncertain write after timeout, cancellation or lost response. A tool timeout can mean that the remote product/order change happened even though the reply was lost. Design must address model-requested duplicate writes after such a result and provider retries that could replay tool batches.
- Do not claim success after `AUDIT_FINALIZATION_FAILED`; the persisted activity outcome is uncertain. `AUDIT_UNAVAILABLE` means M6 did not dispatch.
- Cancellation must stop further dispatch and release resources. An already dispatched write may finish remotely; exact disconnect/deadline handling requires design review and a controlled test.

### 4.4 Today's orders

- Capture one current time for the request and calculate shop midnight in Asia/Kolkata. Pass both inclusive, offset-aware bounds to `list_orders` and keep those bounds fixed across all pages.
- Do not add an unrequested status filter that hides COD or other orders. Follow `has_more` until false when the work budget allows.
- If limits stop pagination, label the answer partial. Do not report a page's total as the whole day's total. Fixture tests must demonstrate this distinction.
- An empty order list is a successful “no orders found” result. Dates returned to the user must agree with the shop-day bounds; do not substitute the model's assumed current date.

## 5. API reply and failure requirements

Preserve the agreed response shape:

```json
{
  "request_id": "<uuid>",
  "state": "completed",
  "answer": "A readable answer based on the observed results.",
  "tool_calls": []
}
```

Each **actual gateway attempt** includes `call_id`, public `tool_name`, `server_id`, `outcome`, `duration_ms` and `audit_id`, with an optional safe error code or sanitized result summary. Preserve unavailable/unknown destination or timing honestly rather than inventing values; exact nullable field handling and extraction from M6's response/context must be resolved together during design.

Allowed outcomes: `success`, `error`, `timeout`, `denied`, `unknown`. Terminal states: `completed`, `failed`, `limit_reached`.

- `completed` means the agent finished its response; tool activity still reports any failures. It does not imply every attempted tool succeeded.
- `failed` means processing could not finish, such as provider failure or session invalidation. Preserve actual earlier attempts and explain uncertainty.
- `limit_reached` means the work/round budget stopped the loop. Return useful observed partial results where available.
- Failures before processing use the existing HTTP error envelope and safe status conventions. Detailed design must define the boundary between that envelope and a processed-chat terminal reply.
- Never return provider exception traces, raw authentication messages, keys, cookies, credential references or full private provider requests.
- Use no-store responses. Do not save chat transcripts in PostgreSQL or send them to application logs as part of this module.

## 6. Provider, security and operational requirements

- The provider adapter is the only M7 component that contacts Groq. Read its key from server-side runtime configuration backed by a Kubernetes Secret; never commit, print or echo it.
- The provider receives the user's message and selected tool information/results needed for the response. This is an external data transfer. Shop tools already exclude billing/contact details; M7 must not reintroduce them or send internal auth/registry/audit records. User messages can themselves contain private text; document that boundary plainly.
- Retain existing credential redaction and add checks for provider-key leakage. Do not promise protection against every transformed or malicious upstream payload; document residual risks.
- Bound model calls, tool batches, text/result sizes, overall request duration and concurrency. Exact values and overload/error behavior are design-review items; eight rounds alone does not bound many calls in one round.
- Use finite network deadlines and release clients/tasks on shutdown or cancellation. No unbounded retry loops; no automatic paid/provider fallback.
- Provider outage must produce a safe chat failure, not crash other backend routes or permanently make unrelated tools unavailable. Runtime liveness should not depend on Groq being reachable. Final shared-backend readiness/probe wiring remains M10.
- Reuse the existing backend's deployment boundary. Any temporary cluster harness is opt-in, internal, resource-bounded, probe-equipped and separately owned; it cannot replace the real shop or delete existing PVCs.
- Same-chart local/VPS configuration remains required, with environment differences in values. M7 does not claim a VPS deployment or browser TLS test.

## 7. Proposed file responsibilities

These are ownership proposals for detailed design, not permission to create application code now.

| File / directory | Responsibility | Checked by |
|---|---|---|
| `backend/chat/agent.py` | Per-message loop, work limits, gateway calls and visible attempt list. | Deterministic fake-model/fake-gateway tests. |
| `backend/chat/llm_client.py` | Groq request/reply translation, finite deadlines and safe provider failures. | HTTP fixtures and controlled real-provider check. |
| `backend/chat/prompts.py` | Task instructions, tool trust boundary and shop-date context. | Prompt-boundary and date fixtures. |
| Chat API adapter, location agreed in design | Session/Origin/CSRF-protected route and safe request/reply handling. | Isolated FastAPI request tests with identity stand-ins. |
| `tests/chat/` | Scripted model, gateway and identity fixtures plus independent regressions. | Separate module test command. |
| `scripts/m7/` | Reproducible isolated checks and explicit live-provider probe. | Safe evidence output and cleanup checks. |
| `docs/evidence/m7/` | Test output, observed provider/model, sanitized call traces and limitations. | Independent acceptance review. |

M6 owns catalog/dispatch interfaces; M5 owns identity checks and audit storage. Shared files/Helm values require a named owner in design. No M10 orchestrator or M8 frontend is added during M7.

## 8. Independent acceptance checks

All rows below are **planned**, not passed. Deterministic fixtures test behavior without spending provider quota; the real-provider row proves actual tool-calling interoperability.

| ID | Check | Observable pass criterion / evidence |
|---|---|---|
| C7-01 | API authentication and input | Missing/invalid session, bearer-only request, wrong Origin/CSRF, blank/extra/oversized fields rejected; zero model/tool calls. Valid request reaches the loop. |
| C7-02 | User attribution and revalidation | A/B genuine fixture identities stay distinct through each gateway call; browser/model spoofing rejected. Expiry/logout between rounds prevents the next dispatch. |
| C7-03 | Product creation | Scripted model sends the exact requested name and decimal-string price once; gateway result drives answer and activity/audit reference. No invented storefront proof. |
| C7-04 | Today's orders and pagination | Frozen-clock cases at shop midnight, differing UTC date, empty results and multiple pages keep fixed correct bounds; incomplete pagination is clearly partial. |
| C7-05 | Cross-server dependency | Product lookup followed by Inventory lookup uses the returned SKU, two public gateway names and one user. Warehouse data explicitly remains sample data. |
| C7-06 | Catalog and content compatibility | New message refreshes tools; disabled/stale name denied. Unsupported schema/content, malformed JSON and unknown calls never become guessed dispatch or false success. |
| C7-07 | Tool errors and audit uncertainty | Denial/error/timeout/unknown and both audit failure modes preserve actual attempts and safe explanations. No duplicate audit write and no automatic uncertain-write replay. |
| C7-08 | Loop/work limits and cancellation | Repeated model requests, many calls in a batch, large content, provider stalls and disconnects stop within chosen bounds; no further dispatch after cancellation. Already-dispatched write uncertainty stays visible. |
| C7-09 | Provider failures | Authentication/rate-limit/unavailability/invalid reply failures are safe, bounded and preserve completed earlier attempts; no fallback or leaked exception body. |
| C7-10 | Credential and trust boundary | Sentinel secrets absent from model payloads where prohibited, API replies and saved evidence/logs; upstream prompt instructions cannot replace principal or direct destination. Only fake gateway observes tool calls. |
| C7-11 | Real Groq tool loop | Explicit implementation-time run with approved account/model against the fake gateway requests a tool, consumes its known result and answers consistently. Record model, requested/executed call, outcome and duration without credentials. No real shop/upstream calls. |
| C7-12 | Module review and deployment boundary | Separate chat suite passes; clean resource shutdown and applicable isolated cluster configuration/Secret/probe checks are inspectable. Report fixtures versus live-provider evidence and M10 gaps separately. |

Use assertions appropriate to an agent tool loop: exact requested/executed tools, argument correctness, identity consistency, bounded counts/time and safe outcomes. Retrieval metrics such as recall@k do not evaluate these requirements.

## 9. Design decisions still requiring review

| Decision | What the design must make concrete |
|---|---|
| Provider transport and model | Groq first and M0 model candidate; exact SDK/HTTP approach, dependency pins, current support, account quota/free-use constraints and key source. No live call during specification work. |
| Loop counting and work limits | What counts toward eight rounds, calls per round/total, sequential versus parallel dispatch, deadlines, concurrency and message/result bounds. Prefer the smallest predictable approach. |
| Catalog adapter and unsupported tools | Exact read-only M6 interface; schema/content support; honest handling when the discovered catalog exceeds provider capacity. |
| Chat API adapter | Mounting, reuse of M5 protections, safe field bounds and pre-processing versus processed-chat error responses. |
| Activity metadata | Sources of server ID/duration/call ID without expanding the agreed three-argument invocation or exposing credentials; honest nullable fields. |
| Writes, retry and cancellation | Prevent uncertain replay within a message; distinguish genuine repeated user intent from model/protocol retries; no invented rollback guarantee. |
| Day calculations and pagination | How the captured clock/bounds are supplied and enforced across model requests/pages while respecting work limits. |
| Secret/harness ownership | Provider Secret reference, temporary runtime scope, cleanup and shared configuration ownership without early final integration. |

This specification does not add a write-confirmation feature, tool-search subsystem, saved conversation or new permission model. Any proposed scope/security/cost change must be explained and reviewed first.

## 10. Review gates and evidence limits

1. Review these functional and technical requirements with the user.
2. After approval, add concrete design inside this same file; independently review it and present the choices to the user.
3. After design approval, implement M7 independently and review the source.
4. Run deterministic checks and the controlled real-provider check; report exact commands, results, saved evidence and remaining gaps.
5. Obtain module acceptance before final real-system wiring in M10.

The [M0 model probe](../evidence/m0/model-probe.json) is historical evidence that the chosen provider/model could call one sample tool on 14 October. It does not prove M7 identity, routing, limits, current quota or live shop actions. Official [Groq tool-use documentation](https://console.groq.com/docs/tool-use/overview) and [model documentation](https://console.groq.com/docs/model/openai/gpt-oss-20b) support the proposed adapter direction; current account access and free allowance still require verification before live use.

M7 acceptance will not prove the browser experience, real product/order changes, real PostgreSQL attribution through the complete gateway, the external-client demo, final Kubernetes outage isolation or VPS deployment. Those require their owning modules and M10's observed end-to-end checks.

**Independent specification review, 17 October 2026:** READY FOR USER REVIEW, with no blocking issues. Review checked assignment scope, identity/gateway boundaries, call-ID pairing and replay prevention, partial results, planned checks and the separate design gate. Provider budgets, exact shared adapters and uncertainty handling remain concrete design-review items. No runtime acceptance is implied.

## 11. Concrete design for user review - 18 October 2026

**Gate:** The user's instruction to implement M6/M7 approves their specifications and implementation intent. This section makes the previously open choices reviewable before application code. Detailed-design approval is still pending; the existing implementation authorization is retained. All numbers below are proposed design limits, except the already approved eight-round maximum.

### 11.1 Smallest architecture and exact dependencies

Keep chat inside the Python backend: one asynchronous agent, one HTTP provider adapter, one route-mounting function, and ordinary pytest fixtures. Use existing HTTPX rather than introducing an agent framework or Groq SDK. M7 does not own an MCP client: it consumes M6's callable interface.

Reuse observed backend pins `fastapi==0.135.1`, `starlette==0.52.1`, `pydantic==2.12.5`, `httpx==0.28.1`, `anyio==4.15.1` and `pytest==9.0.2`; use M6's `jsonschema==4.26.0` dependency for local call validation. Resolve/check one compatible shared backend lock during implementation without downgrading M5. No independent package manager or extra database is introduced.

| Named file | Concrete responsibility |
|---|---|
| `backend/chat/agent.py` | `ChatAgent.run(principal,message)`, budgets, actual-call list, duplicate tracking and result pairing. Dependencies are passed into its constructor. |
| `backend/chat/llm_client.py` | Reused `httpx.AsyncClient`, bounded JSON request/response, Groq completion parsing and fixed safe failures. |
| `backend/chat/prompts.py` | Short fixed instructions, request clock/shop bounds, untrusted-tool-data warning. |
| `backend/chat/api.py` | `mount_chat(app,agent,identity,browser_config)` adds `/api/v1/chat`; no final application startup. |
| `backend/chat/day_window.py` | Captured-clock calculation and enforcement/pagination for the owned WooCommerce `list_orders` contract. |
| `tests/chat/` | Fake provider, contract-compatible identity and gateway; network/request fixtures with injected clock. |
| `scripts/m7/check-m7.py` | Isolated suite/evidence runner; real Groq probe is a separate explicit option against a fake gateway. |

Root owns shared dependency/Helm edits; M7 implementer owns these chat files and tests. M10 alone mounts this route on the final real backend. The test harness may mount it with stand-ins; it is not final integration.

### 11.2 Provider and finite budgets

Use `POST https://api.groq.com/openai/v1/chat/completions`, model `openai/gpt-oss-20b`, custom function tools only, `stream:false`, `max_completion_tokens:1024`, and `tool_choice:auto` during ordinary rounds. Use no Groq built-in browsing, remote MCP execution, automatic retries or provider/model fallback. Groq's documented 20b model lacks parallel tool use; accept at most one model-requested tool per response and execute sequentially. A response violating that limit fails safely before dispatch.

| Bound | Proposed exact behavior |
|---|---|
| Browser body / message | 16 KiB total JSON, matching M5; trimmed nonblank message maximum 4,000 Unicode characters and 12 KiB UTF-8. Reject invalid Unicode, extra fields and non-string input with 422. |
| Provider rounds | At most 8 HTTP completion requests, including the final answer. Rounds 1-7 allow a tool; round 8 sets `tool_choice:none` and omits tool definitions, reserving an answer opportunity. Any tool request on round 8 is a safe invalid-provider failure with zero dispatch. |
| Actual gateway dispatches | Maximum 12 per message, including automatically followed order pages. Count immediately before each invocation; local validation failures do not consume a dispatch slot. |
| Message deadline | 120 seconds from accepted processing; monotonic remaining budget bounds every awaited operation. Cancellation cleanup may use at most 2 additional seconds and dispatches no new work. |
| Provider network | 20 seconds total per completion, connect/pool 3 seconds, read/write 15 seconds within that total; also bounded by remaining message time. Zero retry, redirects off, TLS verification on, `trust_env:false`. |
| Provider response | Maximum 128 KiB while streaming bytes, despite non-streaming JSON format; request identity encoding, reject compressed response; parse only after cap. |
| Tool catalog | Maximum 64 compatible tools and 64 KiB serialized definitions. Reject an over-limit catalog as an explicit chat limitation before inference; do not silently select a subset. |
| Tool arguments / result | Maximum 8 KiB argument JSON; maximum 32 KiB supported serialized result per call and 96 KiB total retained tool-result text. Over-limit content is explicitly unavailable/partial, never silently truncated. |
| Provider payload / answer | Maximum 256 KiB serialized outbound JSON and 16 KiB final answer UTF-8. Exceeding either ends safely with an explicit limit explanation. Completion-token ceiling does not guarantee any token/byte equivalence. |
| Concurrency | Two chat messages per backend process, no waiting queue. Excess requests receive 503 `DEPENDENCY_UNAVAILABLE` before inference/tools. In-process bound matches the existing single-worker backend. |

If any work/time/content limit prevents completing the task, return `limit_reached` with a backend-generated partial/uncertainty explanation and actual calls. A reserved final model answer is optional if time or payload budget is already exhausted; it cannot create a ninth round. Normal empty-tool answers are allowed.

### 11.3 Identity, discovery and exact shared boundary

The route reads bounded JSON asynchronously. Run synchronous `Identity.session`, `Identity.revalidate` and `Identity.check_csrf` in the thread pool; use M5's exact Origin and cookie configuration without copying authentication algorithms. Reject bearer-only requests. Revalidate before each provider request as well as relying on M6's authoritative pre-dispatch revalidation. Blocking SQL/Kubernetes operations cannot run on the event loop.

Joint M6/M7 interface:

```text
await list_tools(principal) -> list of safe catalog dictionaries
  {name, server_id, server_slug, upstream_name, description, inputSchema,
   outputSchema?, annotations?, stale}
await invoke_tool(principal, tool_name, arguments)
  -> {request_id, audit_id, outcome, result: MCP CallToolResult}
```

`server_id` is a server UUID; `server_slug` is its immutable safe registry slug; `name` is the gateway public name. Catalog items expose neither URL nor credential reference. M6 privately checks registry changes; M7 does not need an exposed revision number. Revalidate once at catalog access, then obtain one fresh snapshot per message; execution-time state checks still govern subsequent changes.

Trusted request context supplies the request UUID and a bounded completion sink with `invocation_id`, `audit_id`, `server_id`, `duration_ms`, `error_code`. M7 sets a fresh in-memory invocation UUID for each call; M6 writes one metadata entry on reply or exception. This preserves the exact three arguments and four reply fields. Sink entries are consumed immediately and removed; maximum 12. No principal, arguments, results, URL or credential enters this sink. Invocation UUID permits matching when no audit row could be created.

Chat activity `call_id` is the backend invocation UUID, distinct from the provider's correlation ID. `server_id`, `audit_id` and `duration_ms` are nullable when unavailable. `AUDIT_UNAVAILABLE` yields a visible gateway attempt with `audit_id:null`, outcome `denied`, safe error code and an explicit “not dispatched; activity storage unavailable” summary. It is not claimed as a persisted audit event. Finalization failure yields outcome `unknown` and the known audit UUID; no success claim. M6 owns audit writes and cancellation finalization.

### 11.4 Schema, result and call accounting

Support JSON-object argument schemas using ordinary properties/required/types, arrays/items, enums, numeric/string bounds, `additionalProperties`, and nested `anyOf`/`oneOf`/`allOf`. Accept local definitions/references only when the bounded schema can be validated without network resolution; reject external references or schema formats the provider adapter cannot preserve. Send original accepted schemas unchanged. Unsupported tools are omitted with an explicit limitation note in the final answer; an over-limit overall catalog fails instead of selecting tools silently. Test owned tools and saved Microsoft Learn schemas; do not claim universal provider-schema support.

For results, accept sanitized text blocks and JSON `structuredContent`; preserve both as labeled data if both exist. Images, audio, embedded resource links/content and unknown block types cause an explicit chat-content limitation; never fetch links or pretend the model saw unsupported content. M6 preserves richer content for external MCP clients. No result truncation is passed off as complete. For an observed successful write whose result chat cannot represent, report “gateway reported success; chat could not display the complete result,” rather than repeat the write. Required limitation/partial notes are backend-generated and occupy reserved space within the 16 KiB answer cap; if the model answer cannot fit with them, replace it with a bounded factual summary of actual outcomes. Never omit a limitation to preserve model prose.

Before any dispatch, validate the entire model response's call structure, advertised public name, unique provider ID (nonblank, maximum 128 characters), JSON object arguments and schema. Keep a per-message set of provider IDs. A repeated ID or malformed batch stops without dispatch; IDs are never authorization. Each accepted provider call gets exactly one matching `role:tool` response with its original provider ID; do not send internal identity/audit fields to Groq.

Use a per-message set of `(public name, canonical argument JSON)` for writes. Treat only our known owned read tools matched by configured server slug and original name as read-only; all other tools are potentially writes. External `readOnlyHint` annotations are informational and cannot weaken replay protection. A duplicate write fingerprint stops with a clear failure/partial explanation rather than another dispatch. Identical writes intentionally repeated in one message are an explicit initial limitation. Successful distinct writes remain allowed. No retry of any provider HTTP request occurs, so provider errors cannot replay its previous batch.

After any timeout/unknown outcome, audit finalization failure or interruption, stop the message immediately with a backend-generated uncertainty explanation; do not give a model another chance to retry that action. Known execution errors may return to the model for a different valid next step. Any user retry in a new message is a new request and may duplicate a remote effect; explain uncertainty, without promising global idempotency.

### 11.5 Today's orders are enforced in code

Capture UTC `now` once and compute Asia/Kolkata midnight with `zoneinfo`; use those fixed inclusive bounds throughout the message. Recognize explicit English `today` / `today's` in the user's message as the initial supported shop-day intent. Supply the captured date and bounds to the model. This is deliberately a small language boundary, not a classifier inferred from the model's output.

For that intent, apply the guard only to the configured WooCommerce server slug (initial `woocommerce`) and original tool `list_orders`; neither a coincidentally named third-party tool nor a split public name selects the guard. Use catalog metadata. Require model arguments to supply the exact instant bounds, page 1 and no status filter. Initially, to keep enforcement unambiguous, a today query with a model-supplied status filter is rejected with an explicit chat limitation; filtered today queries remain a later enhancement. Wrong/missing bounds stop safely before dispatch; never silently repair a model-requested write or substitute an unknown date.

For an accepted first page, code follows `has_more` using the same bounds and `per_page` until false, dispatch budget, result budget or deadline. Require well-formed page metadata and forward progress; repeated/mismatched pages stop with a partial-result explanation. Each page is a real gateway attempt with its own invocation/audit reference. Append one aggregated, bounded tool response paired to the originating provider call, containing the observed items and an explicit `complete` flag. Derived chat aggregation is labeled and does not alter the upstream MCP result contract.

If pagination is incomplete, terminal state is `limit_reached` or `failed` as appropriate, and the backend adds an unambiguous partial warning even if a model answer says otherwise. Verify dates and returned order timestamps fall inside the agreed window; an out-of-window reply is a protocol/data error. Multilingual/implicit “today” interpretation is not claimed; ordinary explicit-date tool requests still use their discovered schemas. M10 must use the configured real WooCommerce registration slug.

### 11.6 Terminal responses, cancellation and provider key

Before processing: 401 session failure; 403 Origin/CSRF; 422 invalid body; 503 busy, missing provider configuration or required identity/catalog dependency unavailable. Use the existing safe HTTP envelope and no-store. Once a provider loop starts, return HTTP 200 with `completed`, `failed` or `limit_reached`, retaining all actual attempts. Only a valid nonblank final answer with no unresolved work is `completed`; a provider length/token stop is `limit_reached`, and provider errors/invalid calls/session invalidation are `failed`. Reject truncated tool arguments without dispatch. Safe code summaries are fixed backend strings, never raw provider bodies.

Run the loop and browser-disconnect watcher in a task group. On disconnect/deadline, cancel provider waits and stop before any new dispatch; wait up to two seconds for M6's protected cleanup of already dispatched calls. Already-running synchronous operations may outlast that wait; M6 tracks/fences those bounded late tasks rather than claiming they were forcibly stopped. Activity may end `unknown`; the browser may receive no reply after disconnect. Verify the gateway activity contract rather than claiming a delivery that did not occur. Release the concurrency slot and HTTP resources on every exit. A synthetic no-operation model reply cannot become a successful tool activity row.

Read `GROQ_API_KEY` from an explicitly supplied runtime environment value. Final Helm wiring will use `secretKeyRef` to a pre-created provider Secret; M7's isolated cluster harness, if used, gets a dedicated ignored/ephemeral Secret only. No automatic `.env` loading by backend application code. The host probe may explicitly load the existing ignored `.env` key in memory, never print it or write it into evidence; free-plan/account confirmation is required before the implementation-time real run. Missing/blocked free access is reported as a gap, with no paid switch.

Provider payload contains only fixed instructions, the user message, safe tool metadata, model call structure and sanitized supported results. Remove the actual configured provider key from answer/error surfaces and scan fixture upstream-key sentinels in provider requests; M7 never learns real upstream keys. Log only request UUID, fixed error code and elapsed time. No transcripts, tool argument/result payloads or raw HTTP bodies are logged.

### 11.7 Verification and review gate

Implement the C7-01 through C7-12 matrix using deterministic provider/gateway fixtures, frozen clocks and actual network delay/cancellation fixtures. Add boundary cases at 7/8/9 provider requests, 12/13 dispatches, duplicate IDs/write fingerprints, each byte cap, two/three simultaneous messages, invalid session between model and tool, exact midnight, multiple pages and false model claims of completeness. Assert zero unexpected dispatches and exact attempt/audit matching, not merely answer text.

Planned commands from the project root in PowerShell, using the isolated backend environment; the runner will establish project imports explicitly and avoid relying on shell activation:

```powershell
./.tools/m5/venv/Scripts/python.exe -m pytest tests/chat -q --assert=plain
./.tools/m5/venv/Scripts/python.exe scripts/m7/check-m7.py
# Only during implementation, with account/free access verified:
./.tools/m5/venv/Scripts/python.exe scripts/m7/check-m7.py --live-provider --confirm-free-plan
```

After source review and offline tests, run the explicit Groq probe once with the approved account/model against a fake gateway. Save sanitized model/call IDs, tool names, expected versus actual arguments, fixture answer and measured time; it proves provider interoperability only. A quota/auth/network block remains BLOCKED, not a mocked PASS. No real provider call, new Secret or workload is created during this design phase.

Official sources checked for this design on 18 October: [Groq local tool use](https://console.groq.com/docs/tool-use/overview), [20b model documentation](https://console.groq.com/docs/model/openai/gpt-oss-20b), and [HTTPX asynchronous clients](https://www.python-httpx.org/async/). These support transport/tool-pairing choices; they do not establish this user's billing state or remaining quota.

**User review focus:** the proposed finite budgets; one requested tool per model response; explicit English today guard with automatic page following; stopping on any uncertain outcome and duplicate writes; and supported text/JSON-only chat results. Implementation waits for review of these concrete choices. This design creates no extra plan file and adds no final gateway/dashboard wiring.

**Independent design review, 18 October 2026:** READY FOR USER REVIEW after synchronizing M6/M7's safe catalog and invocation metadata, preserving nullable audit references, and clarifying bounded cleanup waits and late synchronous work. No blocking design issues remain. This is a design verdict, not user approval or runtime acceptance.

## 12. Implementation evidence - 18 October 2026

The user subsequently approved both concrete designs, authorizing implementation and their independent checks. Chat source, test fixtures and explicit provider probe are implemented. The shared isolated verification environment is `.tools/m6/venv`, replacing the design's proposed reuse of M5's environment; no existing M5 environment was modified.

Observed final host result: **72 offline host tests passed in 5.05 seconds**, including actual loopback TCP timeout and ASGI disconnect checks. [Report](../evidence/m7/report.md), [runbook](../evidence/m7/runbook.md), [test output](../evidence/m7/unit-output.txt), [machine result](../evidence/m7/unit-results.json). These are stand-in identity/gateway checks, not real PostgreSQL or upstream integration.

Review corrections enforce UUID correlation at the real M5 boundary, retained capacity for cancelled blocking work, honest incomplete order pages and successful-write display limitations, and conservative stopping after connection/protocol errors that could follow a write. Schema validation has a documented safety subset: two known linear input patterns, 16 KiB schema size, 256 expanded visits/depth 10 and 512 generic JSON nodes/depth 20; unsafe patterns/reference expansion are disclosed as chat limitations. Final independent source review found no remaining blockers.

The frozen shared Linux image passed **119 combined tests in 43.66 seconds: 72 M7 chat plus 47 M6 gateway checks**. [Linux output](../evidence/m6/linux-module-tests.txt). Root verified parity for 35 copied runtime files. This establishes Linux execution of the separate module suites, not actual provider or final chat deployment behavior.

Current free-account confirmation is required before the separate real Groq probe. It remains unrun, and **C7-11/module acceptance is BLOCKED** on that prerequisite. No provider calls have been made. Source review and Linux checks are complete; user module acceptance remains pending. M8/M10 integration boundaries are unchanged.
