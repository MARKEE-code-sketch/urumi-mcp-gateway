# M6 specification: MCP gateway discovery and routing

**Status:** Specification/design approved and implementation authorized by the user's "approved please go ahead implement" instruction. Implemented with 52 distinct host cases, 47 M6 Linux cases and 12 live Kubernetes check groups passing. Independent acceptance review PASS for all 12 criteria; user module acceptance remains pending. Raw runtime evidence is preserved separately. Section 10 is the approved design; section 11 records implementation evidence. No separate parallel-plan/design specification.

## 1. What, why, and how

**WHAT:** Build the shared doorway to our MCP tools. A teammate gives an MCP client one gateway URL and their own personal key, then sees tools from every enabled server.

**WHY:** Teammates should not configure three separate connections or receive the shop and other upstream credentials. A broken server must not prevent them from using healthy servers.

**HOW:** The gateway is an MCP **server** to external clients and an MCP **client** to registered upstream servers. It checks the person, discovers tools, maps each public tool name to its real server/tool, saves an activity record, and makes the requested call. Dashboard chat will use this same execution function as the signed-in person.

Example: `woocommerce__list_orders` routes to the WooCommerce server's `list_orders`; `inventory__lookup_sku` routes to Inventory. The member's personal key stops at the gateway. The gateway supplies only that upstream's saved credential on the outgoing connection.

An upstream is a server behind the gateway. **Discovery** means asking it for its tool names and input checklists, called schemas. A **cache** is a temporary copy of that discovered information. A **deadline** limits how long an operation may wait.

## 2. Source of truth and existing decisions

The assignment DOCX is the product source of truth, especially Gateway, Team and access, and the two-user definition of done. The approved [blueprint](../../blueprint.md), [tool contract](../../contracts/mcp-tools.md), [identity/audit contract](../../contracts/identity-and-audit.md), [platform API contract](../../contracts/platform-api.md), and [decision record](../decisions.md) define our chosen boundaries. Older contract prose calling defaults "proposed" must be read with the later recorded M0 approval.

| Existing choice | M6 must preserve |
|---|---|
| Python + FastAPI, official Python MCP SDK | Reuse the backend stack; review actual SDK compatibility and dependency changes during design. |
| Three selected upstreams | Custom WooCommerce MCP, sample Inventory MCP, real Microsoft Learn. No provider-specific routing code. |
| Streamable HTTP | One external `/mcp`; independent registered upstream URLs. No legacy SSE-only transport requirement. Streamable HTTP can carry JSON or SSE responses. |
| Identity | External bearer key and browser login session remain separate. Both yield a server-verified identity for the same tool executor. |
| M0 defaults approved 14 October | Discovery 3 seconds per server, execution 10 seconds; status polling proposal 5 seconds. Changes require evidence and review. |
| Naming | Immutable slug; stable prefix/hash-alias mapping with 64-character public-name bound. |
| M5 lifecycle | One backend worker/replica, shared exclusive ownership fence; loss of ownership stops new dispatch. No second independent recovery owner. |
| Delivery boundaries | M6 uses contract-compatible identity/registry/Secret/audit stand-ins and controlled upstreams. M10 wires real M5 persistence and real deployment together. |

M4 has already exercised real Microsoft Learn discovery and a useful cluster tool call, reported at roughly 4.1 seconds across its bounded session. That evidence does **not** establish discovery-only latency against the 3-second deadline. M6 must measure discovery separately before deciding whether this approved deadline needs adjustment. A successful remote probe with a longer budget is not M6 timing evidence.

## 3. Scope and ownership

| Included in M6 | Remains with another module or outside scope |
|---|---|
| MCP endpoint, initialization, authenticated listing/calling and transport lifecycle | Accounts, invitation/key issuance, registry CRUD, Secret lifecycle and audit SQL: M5. |
| Dynamic tool discovery, naming, mapping, safe status and previews | Dashboard pages: M8; LLM reasoning/provider adapter: M7. |
| Bounded upstream connections, deadlines, credentials and failure isolation | Real production application wiring and two-user end-to-end proof: M10. |
| Per-call identity/server checks and audit lifecycle coordination | Multiple replicas, per-tool permissions, metrics platform, automatic paid services, dynamic OAuth and legacy transport support. |
| Connection-time enforcement of the already chosen destination restrictions | Arbitrary private URLs, automatic upstream container hosting and optional multi-store provisioning. |

This module does not change which tool actions members may perform: both roles may use all enabled tools, including shop writes. Admin-only management remains M5. It does not implement WooCommerce's business logic or reinterpret Inventory as live shop stock.

## 4. Functional requirements

### 4.1 One authenticated MCP endpoint

1. Expose `/mcp` using the SDK's standard initialization, protocol negotiation, message/result encoding and Streamable HTTP lifecycle. Save negotiated versions in later test evidence rather than claiming one universal upstream version.
2. Authenticate every external MCP request with `Authorization: Bearer <personal-gateway-key>`. A dashboard cookie, user ID in JSON, arbitrary role, or MCP session ID is not a replacement credential. Missing, incorrect and revoked keys return HTTP 401 and make no upstream tool call.
3. Bind any downstream transport session to its authenticated owner and key. Revalidate requests and the final pre-dispatch identity; a retained session cannot survive key revocation or switch users. If design selects stateless downstream transport, demonstrate the equivalent per-request protection without inventing a session requirement.
4. Authenticated listing returns tools from enabled servers, with healthy servers available even if another server is dead. Listing/discovery is not itself a tool execution and must not create fake tool-call audit rows.
5. SDK protocol/HTTP errors remain protocol/HTTP errors. Do not wrap a successful MCP result in the dashboard JSON envelope.

### 4.2 Discovery and public names

1. Read all `tools/list` pages for each enabled server. Bound concurrency, pages, tool counts, bytes and total discovery time; detect repeated cursors. Exact limits are design review items, not permission to ignore pagination or silently return a supposedly complete partial catalog.
2. Preserve input schemas, descriptions, optional output schemas and relevant annotations. Validate malformed metadata/schemas safely. Tool descriptions and annotations are untrusted data, not instructions or authorization.
3. Use `slug__original_name` when the original matches ASCII `^[A-Za-z0-9_.-]+$`, does not start with reserved `h_`, and the complete public name fits 64 characters. Slugs match a lower-case letter followed by up to 23 lower-case letters, digits or hyphens.
4. Otherwise use `slug__h_` plus the first 32 hexadecimal characters of SHA-256 of the original UTF-8 name. Names are case-sensitive. Keep an explicit mapping to server UUID and the exact original name; never guess a route by splitting a supplied public name.
5. Detect duplicate/alias collisions and reject that server's new discovery snapshot safely. A bad server cannot overwrite another server's mapping. Preserve the previous valid snapshot only under the stale-data rules below.
6. Upstream tool-list change notifications trigger bounded refresh when supported. Invalidation must work even without notifications; document when a client needs refresh/reconnect.

### 4.3 Registry changes, status and previews

1. Discover/check servers independently. Use `Connected`, `Unreachable`, and `Disabled` exactly; disabled wins immediately. A newly enabled, never-checked server begins `Unreachable` with `NOT_CHECKED`.
2. Preserve a last successful catalog during temporary unreachability and mark its preview `stale:true`. Never-discovered failed servers contribute no invented tools. A stale name can attempt a new bounded call; cached discovery never overrides the current identity/server checks.
3. Disabled servers contribute no tools to a fresh listing; previews return empty items and `stale:false`. Removed servers cannot be called, including through a previously known name or open client session.
4. URL/credential edits invalidate the old connections/catalog. An in-flight old discovery must not overwrite the new configuration's catalog or status. Disable/removal must also prevent a late refresh from restoring routability.
5. Implement the M6-owned `GET /api/v1/servers/{id}/tools` behavior using session authentication and safe pagination: `items`, `page`, `per_page`, `has_more`, plus top-level `stale`. Defaults are page 1, per_page 20, maximum 50. Each item includes gateway name, original name, description and input schema. Exact item field names and stable discovery ordering are design items; do not pretend they were specified by M0.
6. Use M5's existing finite safe status vocabulary: `NOT_CHECKED`, `AUTH_FAILED`, `TIMEOUT` and `CONNECTION_FAILED` (or no reason for a connected server). Map malformed discovery/protocol failures to a reviewed existing reason or explicitly review an adapter extension; do not invent unsupported values. Never return raw upstream exceptions, credentials or Secret references. Status is available through the M5 server summaries. Tools-preview replies never expose hidden URL/auth configuration to members.

### 4.4 The shared execution path

The exact shared entrypoint is:

```python
invoke_tool(principal, tool_name, arguments)
```

The principal is a proof-backed backend identity, not a plain object supplied by a browser/model. Gateway request context generates correlation. Do not add a caller-controlled fourth request-ID argument.

The internal reply contains exactly the contracted fields:

```text
{request_id, audit_id, outcome, result: <MCP CallToolResult>}
```

M7 receives a read-only discovered catalog and calls this function. A proposed `list_tools(principal)` adapter will be specified jointly during design; its signature and catalog wrapper are not yet an approved contract. M7's safe activity display also needs server/duration metadata; agree how it receives that information without silently changing the four-field execution reply.

For each attempt:

1. Resolve the explicit tool mapping; revalidate identity and current server state. A fabricated principal cannot grant access. Check the shared owner fence; loss of ownership or required dependency failure prevents dispatch.
2. Persist one durable `running` audit attempt before the outgoing tool execution. Discovery/initialization may make protocol connections, but cannot execute a tool before this audit write.
3. Immediately before sending the tool request, recheck identity and routing configuration so queued work cannot use revoked access or disabled/edited destinations. The design must define the ordering/locking boundary for concurrent edits and dispatch.
4. Use only the selected server's URL and resolved owned credential. Call the original upstream tool with the supplied arguments; do not rewrite its schema or implement a provider-specific branch.
5. Preserve standard MCP result content, including structured/text content and other supported MCP blocks, within reviewed bounds. Do not silently omit unsupported blocks or advertise truncation as a complete result. M7 may separately disclose a model limitation.
6. Finalize the one attempt and return the honest result. No automatic replay of an uncertain tool call, including during session reconnection or timeout handling.

Already-dispatched work may finish after revocation or disabling. These controls prevent future dispatch; they cannot roll back a remote action. A reconnect may safely rebuild protocol state, but must not replay a request whose execution is uncertain.

### 4.5 Audit and error behavior

Audit fields follow M0 exactly: UUID correlation/attempt IDs; verified user/key/source; nullable server/original tool; public tool; UTC timestamps; duration milliseconds; outcome and safe error fields. Do not save full arguments/results or customer payloads. M5 owns persistence; M6 coordinates it once per execution attempt.

| Situation | Required response/outcome |
|---|---|
| Missing/wrong/revoked external key | HTTP 401, no dispatch. For a safely identifiable attempted tool call, record denied; unknown key has null identity, verified revoked key may be attributed. Malformed/oversized bodies must not be parsed without bounds just to fabricate an audit row. |
| Unknown tool | Standard MCP/JSON-RPC error and attributed attempted-call denial with safe `TOOL_NOT_FOUND`; server/original name may be null. |
| Disabled cached tool | `TOOL_DISABLED`, denied; no dispatch. |
| Upstream configured credential rejected | `UPSTREAM_AUTH_FAILED`, error; hide upstream body/credential. |
| Connection or invalid protocol | `UPSTREAM_UNAVAILABLE` or `UPSTREAM_PROTOCOL_ERROR`, error; healthy servers continue. |
| Valid upstream result with `isError:true` | Error outcome; preserve a sanitized execution-error result. Do not promote an upstream failure to success. |
| Deadline expired | `UPSTREAM_TIMEOUT`, timeout; explain possible remote write effects. |
| Initial audit unavailable | `AUDIT_UNAVAILABLE`; no execution. Disclose that an unavailable database cannot save that denial. |
| Finalization unavailable | `AUDIT_FINALIZATION_FAILED`; do not report verified success or retry. Persisted running attempt remains until shared recovery can mark it unknown. |
| Process interrupted | Shared exclusive-owner recovery marks prior-run attempts unknown; never mark current active work unknown. |

No extra denial audit row should be added after a running attempt already exists: finalize that same attempt. The design must specify safe protocol encoding for these cases and correlation without changing standard MCP envelopes.

## 5. Technical and security requirements

- Use the official SDK for MCP framing. The upstream client must handle the JSON/SSE response forms and stateful upstream lifecycle required by compatible Streamable HTTP servers; POST-only stateless local fixtures do not establish full hosted compatibility.
- Enforce actual end-to-end operation deadlines, including initialization, paging and cleanup as applicable. Bound background refresh and connection pools; a slow server cannot monopolize the event loop or serially delay unrelated servers. Blocking M5 adapters must not run on the async event loop.
- Construct outgoing headers from registry configuration only: none, saved bearer, or named static API-key header. Never forward incoming gateway Authorization, cookies, MCP session IDs or caller-chosen destinations/headers. Continue M5's reserved-header and CR/LF rules; SDK generates upstream transport headers independently.
- Apply M5's exact operator-allowlisted internal URL exceptions for WooCommerce and Inventory. Otherwise require public HTTPS, trusted TLS, no URL credentials/fragments/query strings, no redirects and no implicit environment proxies. Reject forbidden private/loopback/link-local/metadata destinations and ambiguous IP forms.
- Validate all resolved addresses at connection time and prevent a later unchecked resolution from selecting a forbidden destination. Design must explain how the actual connector uses the checked address while preserving hostname/TLS checks; a preflight DNS lookup alone is insufficient. Test DNS rebinding, mixed public/private answers and redirect attempts with deterministic fixtures. Controlled localhost tests use a separate explicit test policy, never a production wildcard exception.
- Remove known configured secret values from diagnostics and echoed tool results/metadata before clients, models or saved evidence receive them. Do not promise protection against every transformed secret or a compromised upstream. Limit error summaries and log only safe correlation/error codes.
- Review request/response/decompressed-size limits, schema depth, tool-list bounds, session counts/lifetimes and concurrency limits in design. Exhaustion returns an explicit safe failure, never silent data loss. Avoid speculative enterprise features.
- Follow M5's one-worker/one-replica ownership lifecycle. Upstream failure alone must not fail backend readiness/liveness or restart healthy work. Isolated test workloads have probes, resource requests/limits, internal Services and non-secret Helm values; retain actual production Ingress/wiring for M9/M10.

## 6. Proposed files and dependencies

These are ownership proposals for design, not instructions to create application code now.

| File/resource | Responsibility |
|---|---|
| `backend/gateway/server.py` | Authenticated MCP transport adapter and M6 tools-preview route adapter. |
| `backend/gateway/discovery.py` | Independent discovery, immutable snapshots, names and status refresh. |
| `backend/gateway/router.py` | Shared executor, current access/server checks and audit lifecycle. |
| `backend/gateway/upstream_client.py` | Safe MCP connections, upstream headers, bounded I/O and cleanup. |
| `tests/gateway/` | Stand-in identity/registry/Secret/audit, controlled MCP servers, protocol and race tests. Reuse M4 fixtures only where their existing behavior fits. |
| `scripts/m6/` | Reproducible isolated acceptance harness and sanitized evidence capture. |
| `tests/gateway/values-check.yaml` | Disposable cluster configuration, separate from existing shop and platform records. |
| `docs/evidence/m6/` | Future measured results, protocol versions, error/audit transcripts and limitations. |

The parent agent owns reviewed shared dependency/chart edits. Do not alter M3/M4/M5 source or common contracts to make a test pass without review. M6 can be tested with stand-ins while M7 uses a fake gateway; M10 remains the final orchestrator.

## 7. Independent acceptance plan

All rows are **planned**, not observed PASS. Use assertion-based tests and real MCP transport evidence; recall/precision or model-quality metrics do not measure gateway correctness.

| ID | Traceability | Check and required evidence |
|---|---|---|
| M6-01 | Assignment: one endpoint/all enabled servers | A real SDK client initializes against gateway and lists/calls three controlled Streamable HTTP servers through it; save negotiated versions and safe routing transcripts. Include JSON and SSE/stateful upstream fixtures. |
| M6-02 | Gateway: collisions; M0 naming | Duplicate `service_info` names route separately; unsafe/long/reserved names map stably; case preserved; injected hash collision and malformed schemas isolate the affected discovery snapshot. |
| M6-03 | Gateway: discover external tools | Multiple pages, empty catalog, repeated cursor, excessive pages/bytes/tools and partial page failure. Preserve valid schema/output metadata and explicit completeness; no invented tools or silent truncation. |
| M6-04 | Gateway: optional static credential; secrecy | None/bearer/custom-header correct and incorrect cases; capture fixture-side headers to prove no incoming user key/cookie/session forwarding. Echo sentinel secrets in results/metadata/errors and scan safe replies/evidence/logs for leaks. |
| M6-05 | Team: revocation; two-user demo foundation | Two distinct stand-in verified users/keys, wrong/unknown/revoked keys, existing-session revocation, cross-owner session attempts, browser-cookie rejection on MCP. Assert zero dispatch when rejected and honest denial attribution. |
| M6-06 | Team: current identity; M7 boundary | Genuine session principal succeeds internally; fabricated principal, expired/revoked session and changed current role are rechecked. Block a call before dispatch, revoke/disable, then release: it must not execute. Already-dispatched case may finish once. |
| M6-07 | Team/control: edit/disable/remove | Fresh lists/previews hide disabled tools; stale direct names denied; removed routes cannot execute. Slow old discovery finishing after edit/disable/remove cannot restore old mapping/credentials/status. |
| M6-08 | Gateway: slow/dead isolation/status | Controlled healthy, slow, dead, malformed and wrong-credential fixtures; measure listing/healthy-call/deadline/status latency and recovery independently. No successful healthy call waits behind a dead peer. |
| M6-09 | Team: every call audited | Exactly one attempt/finalization for success, tool error, protocol/connection error, timeout, denial and interrupted uncertainty. Audit-write failure sends zero tool calls; finalization failure never reports verified success or retries. Shared-owner fence prevents new work. |
| M6-10 | M0 API: safe previews; role boundary | Session-authenticated paginated preview with correct names/schemas/stale flags; unreachable retains old valid preview, never-discovered/disabled empty. No values/references/hidden member config or unbounded exception text. |
| M6-11 | Approved destination policy/threat model | Mixed/private DNS, rebinding, forbidden addresses, redirects, implicit proxies and TLS failures rejected by the actual connector. Exact built-in/test allowlist exceptions do not permit arbitrary private traffic. |
| M6-12 | Kubernetes requirement/failure demo foundation | Disposable gateway/upstream Pods with probes/resources/internal endpoints; kill one controlled upstream Pod and prove other tools work/status changes, then restore it. Save resource/log/timing evidence; delete only owned fixtures and preserve all existing shop/PVC identities. |

Approved/default timing to validate: discovery 3 seconds per server; execution 10 seconds. Existing blueprint acceptance targets are fresh listing within 5 seconds, controlled healthy call within 2 seconds, timed-out call by deadline +2 seconds processing allowance, and sustained outage reflected within 15 seconds. These acceptance targets and the 5-second polling proposal must be confirmed during design against local and hosted evidence; failures cannot be hidden by quietly widening limits.

Independent controlled three-server evidence is not proof that the real WooCommerce, Inventory and Microsoft Learn are integrated. Live registration/remote calls, Codex plus Inspector interoperability, browser display, persistence-backed revocation and the actual two-user shop demonstration remain M10 evidence.

## 8. Design questions to review next

1. **Transport/session lifecycle:** Downstream stateless versus stateful mode; upstream ownership/reconnect/cleanup; bounded refresh scheduling and exact resource limits. Retain SDK semantics and support hosted stateful connections whichever downstream mode is chosen.
2. **Discovery timing:** Separately measure Microsoft Learn discovery and assess the approved 3-second budget. Recommend any change with measured evidence, without adding a hidden provider-specific timeout.
3. **Configuration races:** M5 currently exposes `set_server_status(server_id, status, reason=None)` without a configuration revision argument. Design snapshot invalidation and conditional updates so old work cannot overwrite new state. Any small M5 adapter extension needs explicit review; do not pretend that compare-and-set already exists.
4. **Long original names:** Hash aliases allow long upstream names, but M5 audit currently accepts original/public tool strings only up to 200 characters. Agree a safe interoperability bound or reviewed storage-contract adjustment; never silently truncate an original name and route/audit it as if unchanged.
5. **Chat catalog/activity adapter:** Agree read-only catalog shape and safe server/duration/error metadata access with M7 while retaining the exact three-argument invocation and four-field reply.
6. **SSRF connector and response limits:** Explain exact address pinning/TLS behavior and bounds, including compressed/SSE data, malformed metadata and credential sanitization of rich content. Review the security tradeoff before implementation.

## 9. Review gate and done criteria

This draft is READY FOR USER REVIEW because scope, existing contracts, acceptance evidence and unresolved design choices are explicit. That verdict is not user approval.

Next: user reviews/approves this specification; prepare detailed design here and independently review it; obtain design approval; implement M6; independently review and run its checks; present exact commands, results, evidence and gaps for module acceptance. M7 can be designed against the agreed interface independently. No final integration begins before the module gates.

M6 is complete only when reviewed requirements have passing independent evidence, timing and trust limitations are disclosed, and owned temporary resources are cleaned up without changing the existing store/disks. A successful Python test suite alone does not prove a working Kubernetes gateway or the final assignment flow.

**Independent specification review, 17 October 2026:** READY FOR USER REVIEW; no blocking revisions. Review checked the assignment boundary and actual M5 identity, registry/status and audit interfaces. Approved 3-second discovery/10-second execution defaults remain intact; phase-specific timing evidence, configuration-version/status races, the audit's 200-character original-name bound and the shared M7 catalog/activity adapter remain detailed-design items. This review records document readiness, not user approval or runtime success.

Technical references: [official MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [official MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [official Python SDK](https://github.com/modelcontextprotocol/python-sdk). These explain protocol behavior; they do not add new product scope or claim current interoperability.

## 10. Detailed design for review — 18 October 2026

**Gate history:** The user requested M6/M7 implementation on 18 October, then explicitly approved these concrete designs and asked to implement. That authorizes this design, its implementation, independent review and planned checks. The design text below records those reviewed choices; observed runtime evidence is in section 11.

### 10.1 The simple structure

Keep one Python backend process. M6 is a set of Python files inside that backend, not another permanent microservice. Like functions inside one Docker application, chat can call the gateway function directly while external clients enter through HTTP. A Kubernetes Deployment keeps that application running; a Service gives other Pods a stable internal address. The isolated acceptance Deployment is temporary and will not replace the existing shop or M5 data.

| Owner | Concrete responsibility |
|---|---|
| `server.py` | ASGI factory, bearer middleware, low-level MCP handlers, safe preview route, request context and probes. |
| `discovery.py` | Versioned catalog snapshots, deterministic names, five-second refresh coordinator and safe previews. |
| `router.py` | `invoke_tool`, pre-dispatch checks, single audit lifecycle and completion metadata. |
| `upstream_client.py` | One bounded SDK session per discovery/call; custom address-checked HTTPX transport. |
| `tests/gateway/` | Contract-compatible stand-ins, deterministic DNS/TLS/stream fixtures and SDK clients. |
| `scripts/m6/harness.py`, `scripts/m6/check-m6.py` | Isolated application and host-driven acceptance/evidence runner. |
| `deploy/charts/urumi/templates/gateway-check/` | Disabled-by-default temporary Deployment, fixtures, Services and test-only network rules; main agent owns shared values. |

Use MCP **1.26.0**, HTTPX **0.28.1**, HTTPCore **1.0.9**, JSON Schema **4.26.0**, dnspython **2.9.0** for cancellable DNS I/O, plus existing locked FastAPI/Pydantic/AnyIO/Starlette versions. Add required transitive pins to the backend lock after a clean isolated dependency resolution; never downgrade the existing Starlette security pin. Reuse the existing pinned Python 3.13.5 image digest. Verify `pip check` and existing M5 tests for the small adapter changes. New dependency resolution failure is a reported blocker, not permission to choose an unreviewed SDK.

### 10.2 Downstream protocol and request context

Use `StreamableHTTPSessionManager(..., stateless=True, json_response=True)` and the low-level SDK server. External POSTs receive standard JSON MCP replies; authenticated GET returns 405 because this design does not offer a persistent downstream event stream. There is no downstream session ID to authorize or transfer between users. SDK clients must still initialize/negotiate correctly; demonstrate existing-client revocation on the same client connection. Tools change when clients list again; do not advertise downstream list-change notifications without an event stream.

Bearer middleware authenticates every `/mcp` request, including initialization/listing, before SDK processing. It buffers at most 64 KiB, rejects non-JSON or oversized requests safely, and uses a gateway-generated request UUID. Bounded parsed `tools/call` denials use M5-compatible `record_denial`; malformed requests without a safely recoverable tool name receive a protocol/HTTP rejection without invented tool execution. No access/body/header logging. Require configured Host values and reject an unapproved supplied Origin; absent Origin is permitted for native MCP clients. Browser preview uses existing session validation; cookie authentication never substitutes for bearer at `/mcp`.

Register a direct `server.request_handlers[types.CallToolRequest]` handler returning `types.ServerResult` instead of the convenience `call_tool` decorator. Source inspection shows the decorator also catches exceptions and converts their text into tool errors, even with input validation disabled; that would obscure authoritative JSON-RPC errors and risk diagnostic leakage. The direct handler preserves `McpError` for unknown tools, maps all other exceptions to fixed safe responses, and delegates bounded schema validation/auditing to the router. SDK retains envelope/protocol validation. Unknown tool is JSON-RPC invalid params with one safe denial row. Reject supplied name over 64 characters before routing; do not store unbounded malicious name strings in audit. Names that exceed this bound cannot identify one of our public tools.

Request context is a `ContextVar` containing request UUID and a private bounded completion sink. External HTTP requests own their context; M7 creates a per-chat context and each invocation gets a distinct audit UUID. No browser/model fields can populate trusted context. Synchronous M5 adapter calls run in a bounded thread pool; token creation/reset follows `try/finally` so concurrent users never share context.

### 10.3 Catalog, bounds and status

Read enabled registry rows as immutable snapshots keyed `(server_id, version)`; M5 already increments its integer `version` on edits. A catalog snapshot is replaced atomically only after every page validates and the current row still has that version and remains enabled. Cache only metadata/mapping, never resolved credential values. Keep one last successful snapshot per server/version in memory; it is lost on restart and then rediscovered.

Initial authenticated listing refreshes missing snapshots concurrently under a three-second per-server deadline. Later listings use available snapshots and current enabled/version state; a coordinator refreshes every five seconds without overlapping a refresh for the same server. Maximum four simultaneous discoveries, with separate call capacity. Three controlled servers therefore have no serial deadline multiplication. Removal/version changes immediately evict connections/snapshots on the next registry read. Refresh cannot republish a removed/disabled/edited version.

Bounds: at most 20 registered enabled servers processed; at most 20 pages and 200 tools per server, 1,000 tools/8 MiB across the merged catalog; schema nesting 32, one tool definition 64 KiB. These are explicit supported limits, not silently truncated catalogs. An over-limit server discovery is Unreachable with `CONNECTION_FAILED`, retains only a valid same-version prior snapshot as stale, and supplies a safe diagnostic code to operational logs. A registration-count/merged-catalog overrun returns a clear catalog-limit failure rather than quietly hiding enabled servers. Bound refresh tasks; overload never starts an unbounded queue.

Original tool names must be valid UTF-8, 1–200 Unicode characters. Preserve case and exact spelling. The existing prefix/hash rule handles unsafe names and names too long for the 64-character public limit within this bound. Longer names fail that server's discovery explicitly: this documented compatibility limit preserves M5's exact audit strings without a schema/storage change. Do not truncate. Successful schemas use JSON Schema validation, no remote `$ref` retrieval; unresolved/external references are a safe unsupported-schema discovery failure, never an outbound fetch. Detect hash collisions before publishing.

Safe chat catalog adapter:

```python
async list_tools(principal) -> list[dict]
# item: name, server_id, server_slug, upstream_name, description, inputSchema,
#       optional outputSchema/annotations, stale
```

`name` is the gateway name, `server_slug` is the safe immutable configured slug, IDs are UUID strings, `stale` is boolean. No URL, configuration version, Secret reference or credential enters this catalog. Revalidate principal for each list. Sort by `(server_id, name)` for deterministic discovery pagination; preview items use `gateway_name`, `upstream_name`, `description`, `inputSchema`, optional `outputSchema`/`annotations`. Preview is the M0 page wrapper plus `stale`, sorted by gateway name. The external SDK list handler serves the same bounded tools without chat-only item fields.

### 10.4 Small M5 seam adjustments

Extend `Registry.set_server_status(server_id, status, reason=None, *, expected_version=None)`: M6 always supplies the observed version. Conditional SQL updates only that version; return false for a changed/removed row and discard that refresh. Existing M5 callers without the keyword preserve their behavior. No migration is needed; `version` already exists. Keep the finite M5 reasons; malformed metadata/protocol/connectivity maps to `CONNECTION_FAILED`, credentials to `AUTH_FAILED`, deadline to `TIMEOUT`, success to null reason.

Coordinate dispatch with M5's existing `Database.server_lock(server_id)` advisory lock, which management already uses. Use a bounded lock bridge: at most eight worker threads retain their own database connection/session lock and announce readiness to the async task after rereading enabled/version/credential reference and checking identity/owner. The async task alone performs SDK network I/O after checking the live operation deadline/cancellation flag again. A late worker may only release its lock, never trigger dispatch. The worker waits for a release event, with an absolute deadline plus two-second grace, then exits its lock context in `finally`; the async task signals release on every exit. Do not hold a database transaction while waiting for network. Hold the session advisory lock until the bounded call completes; therefore a concurrent admin edit may return bounded conflict/unavailability and be retried rather than commit midway through an execution. This deliberately simple single-worker boundary avoids a new distributed lease. A blocked server's lock cannot block calls to another server. M6 stand-ins model this same ordering; M10 must verify the real lock seam.

No audit-name storage adjustment is proposed. Reuse the existing fixed safe audit codes; unsupported schema/bounds/input-validation failures use `UPSTREAM_PROTOCOL_ERROR` or `TOOL_NOT_FOUND` as appropriate and fixed summaries. Exact client-facing safe detail may distinguish validation from lookup without placing arbitrary exception text in the database. Changes to M5 are limited to version-conditional status and exposing the already existing lock to the M6 adapter; rerun relevant M5 status/ownership/regression checks.

### 10.5 Safe upstream transport

Create a fresh `httpx.AsyncClient` and SDK `streamable_http_client(url, http_client=client)` / `ClientSession` for each discovery or invocation. Discovery lists all pages in one session; a call initializes then sends one `tools/call` in its own session. This costs an extra handshake but avoids long-lived shared credential/session state and provides a small independent test surface. Handle upstream JSON and SSE and SDK-managed upstream session IDs; do not copy any downstream session/header. Polling replaces notifications across these short sessions. No transport retry of POST; resumable GET may retrieve the original response within the same deadline and must never resend the tool execution.

HTTPX does not expose the custom network backend directly in `AsyncHTTPTransport`. Implement one small `AsyncBaseTransport` adapter using the public `httpcore.AsyncConnectionPool(network_backend=...)` API and HTTPX request/response stream adapters. Do not monkey-patch HTTPX's private `_pool`. Its checked `AsyncNetworkBackend.connect_tcp` (DNS API: [official dnspython async resolver](https://dnspython.readthedocs.io/en/stable/async-resolver-class.html)):

1. Accepts only the operation's configured hostname/port. Rechecks the exact allowed URL before opening a socket.
2. Resolves A and AAAA through `dns.asyncresolver.Resolver.resolve_name(..., lifetime=1, search=False)` with at most four DNS operations and the remaining operation deadline. Read cluster nameservers from `/etc/resolv.conf`; use fully qualified Service names and no search-domain expansion. Inspect **all** addresses, rejecting any non-global address for public HTTPS. Exact internal/test URL exceptions permit their resolved Service/test addresses, with no suffix/wildcard bypass. Numeric literals skip DNS. This uses cancellable DNS socket I/O rather than uncancellable OS resolver worker threads; `/etc/hosts` aliases are not an upstream discovery mechanism.
3. Connects the underlying AnyIO backend to a selected checked numeric address, not the hostname. If that address fails, another already-checked address may be tried only before any HTTP request and within the same deadline. No second unchecked DNS lookup.
4. Returns the stream unchanged so HTTPCore performs TLS with the original request hostname and default trusted certificate context. Keep original Host/SNI/certificate hostname checks. HTTP/1.1 only; no proxy, Unix socket or caller-supplied socket path.

Pool capacity three connections per ephemeral session permits POST plus an SDK GET event stream; retries zero, TLS verification true, `trust_env=False`, redirects false. The SDK may send background GET; it uses this same checked transport and budget. Redirects are rejected before forwarding credentials. Header values are registry-owned only. Use connect/pool/write timeouts at most two seconds, reads bounded by the remaining overall operation deadline.

Wrap response byte streams before SDK JSON/SSE parsing: 2 MiB per HTTP response, 8 MiB total operation, including all streams/pages; request 64 KiB maximum; set `Accept-Encoding: identity` and reject compressed responses explicitly rather than risk decompression expansion. Count raw bytes/SSE events incrementally even on streams without Content-Length. An SSE line/event is at most 256 KiB. On overflow close the stream and return a safe protocol/bounds failure. Bounded failure is preferable to an apparently complete truncated response.

Remove exact known configured secret values from textual metadata/results recursively before public/catalog/model serialization; if sanitization invalidates an advertised structured success schema, return an explicit safe error instead of a falsified success. For binary content or embedded resource bytes, never silently alter/drop blocks: if credential safety cannot be checked within supported decoding limits, return an explicit unsupported-content error. Preserve otherwise supported SDK content objects. Disable verbose `mcp`, HTTPX, HTTPCore and Uvicorn access logs; operational logger emits only UUIDs, fixed codes and durations. Exception strings/raw MCP messages are never logged.

The network seam is supported by [HTTPCore's official custom network-backend API](https://www.encode.io/httpcore/network-backends/); the protocol forms follow [official Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports). Installed SDK 1.26.0, HTTPX 0.28.1 and HTTPCore 1.0.9 source were read on 18 October to check these API choices. This is a design feasibility check, not an observed TLS/DNS defense test.

### 10.6 Dispatch, audit and cancellation

Run the shared three-argument executor asynchronously. External adapter and M7 supply the same genuine identity. Capacity is eight concurrent tool executions globally, at most two per server, with at most one second to acquire capacity; overload returns an audited safe denial, never waits indefinitely. Discovery uses separate capacity. Do not cache authorization decisions.

Pipeline: validate bounded request/name -> resolve mapping -> authenticate/revalidate -> acquire capacity and per-server ordering lock -> reread current server/version -> validate arguments -> persist running attempt -> resolve credential/create session -> initialize -> final identity/owner/server/version check -> send exactly one tool request -> sanitize/validate observed result -> finalize audit -> return four-field reply. Denials before a running attempt use one atomic denial operation; failures afterwards finalize that same attempt. No duplicate audit row for a late revocation.

Keep discovery at **3 seconds** and the tool operation at **10 seconds**, measured monotonically from executor entry (including capacity wait, lock, credential resolution, initialization and response). Audit/preflight dependency failures remain bounded by M5's adapter timeouts; separately record total wall time. Reserve at most **2 seconds** of response waiting after the tool deadline for shielded cleanup/finalization; no new remote execution during cleanup. M5's blocking SQL can outlast this response allowance: retain its task in a bounded tracked set until it actually exits, never release its worker capacity early, and never let a late completion start network I/O or change an already returned uncertain result. At most eight tracked dispatch/lock jobs and eight finalization jobs are allowed; exhausted capacity rejects new work safely. Session-lock owner connection closure and supervisor fencing stop new dispatch if release cannot be established. A later committed final audit update remains truthful evidence; do not falsely claim cleanup completed within two seconds. Initial audit must be committed before tool dispatch, and success is withheld until finalization commits. If a synchronous adapter cannot finish inside the remaining deadline, return safely and fence its completion from starting any later network execution.

Timeout finalizes `timeout/UPSTREAM_TIMEOUT`. If HTTP/chat cancellation or process shutdown occurs after possible dispatch, shield a best-effort `unknown/INTERRUPTED` finalization and session close within the cleanup allowance; never claim rollback. Cancellation definitely before submission may record a denied/error result instead. Failed finalization leaves the durable running row for M5's next exclusive-owner recovery and returns/records `AUDIT_FINALIZATION_FAILED` uncertainty. User retry is a new request/attempt; neither SDK reconnect nor our router replays a write.

Populate the private request-context completion sink once per attempt, including exception paths, with nullable unavailable fields. Include `invocation_id` as a fresh UUID supplied through trusted per-invocation context by M7 (external adapter creates its own). The complete sink shape is `{invocation_id,audit_id,server_id,duration_ms,error_code}`; invocation ID pairs exceptions even when no audit ID was available. Bound it to the owning request's call budget; external requests need only one item. M7 uses this sink plus the exact `{request_id,audit_id,outcome,result}` reply to build visible call activity. No extra reply fields or fourth invocation argument. M7 must retain failed/unknown activity even when no normal result is returned.

### 10.7 Isolated cluster and checks

Use separate namespace/release `urumi-m6-check`, disabled-by-default `gatewayCheck.enabled`, no Ingress, a loopback port-forward for the external SDK test client. Never reuse real shop/platform credentials or issue real shop writes. Deploy the temporary gateway and three deterministic fixture servers (no-auth, bearer, named header); fixture controls additionally supply dead/slow/paged/SSE/stateful/echo cases. Test-only URL allowlist names those exact fixture Services. This fixture policy is never copied into production values.

Gateway request/limit: **100m/256 MiB -> 1000m/512 MiB**; fixture **25m/32 MiB -> 250m/128 MiB** each. One worker/replica, non-root UID 10001, read-only filesystem, dropped capabilities, no Kubernetes API token for stand-in harness. `/livez` verifies the process; `/readyz` verifies initialized adapters/owner and catalog coordinator, not all upstream reachability. Initial delay 3 seconds, period 5 seconds, timeout 2 seconds, failure threshold 3. Internal Services port 8000. NetworkPolicy permits gateway->fixtures and DNS only, fixture ingress from gateway/test-labelled Pods only; no external egress required for mandatory isolated acceptance.

Run the twelve acceptance groups in section 7 with deterministic clock/barrier tests for concurrency, plus real TCP/SDK sessions and live Kubernetes controlled failure. Add TLS fixture with a test CA to prove original-host certificate checks alongside checked-address dialing; test mixed DNS answers/rebinding with injected resolver and actual numeric dial capture. SDK stateful SSE fixture records that one `tools/call` was submitted despite stream interruption. Input-validation audit regression, byte-stream bounds, task/context cleanup and log sentinel scans are mandatory.

Planned PowerShell commands (scripts/values are future files, not present success evidence):

```powershell
& .tools/m6/venv/Scripts/python.exe -m pytest tests/gateway -q --assert=plain
docker build -t urumi/gateway-check:m6 -f backend/Dockerfile .
& .tools/m1/k3d.exe image import urumi/gateway-check:m6 -c urumi
& .tools/m1/helm.exe upgrade --install urumi-m6-check deploy/charts/urumi --kubeconfig .tools/m1/kubeconfig.yaml --kube-context k3d-urumi -n urumi-m6-check --create-namespace -f tests/gateway/values-check.yaml --wait --timeout 180s
& .tools/m6/venv/Scripts/python.exe scripts/m6/check-m6.py --cleanup
```

The check runner verifies namespace ownership and captures original store/Pod/PVC identities before mutation; cleanup removes only its owned release/namespace. Save safe protocol versions, timings, dispatch/audit counts, error outcomes, resource IDs, exact commands and scans under `docs/evidence/m6/`. Check all tools/results without storing credentials or full customer payloads. Compare actual image runtime configuration digest as in M4/M5, not OCI index versus image configuration.

No public endpoint, real M5 integration, browser UI or VPS deployment is proven here. Optional fresh Microsoft Learn timing uses no secret and must be separately labeled; it cannot replace controlled timeout/isolation evidence or silently change the three-second budget. If this reviewed simple ephemeral-session design cannot meet the measured targets, report the finding and review a change rather than bypass deadlines.

**Independent detailed-design review, 18 October 2026:** READY FOR USER REVIEW; no blocking revisions remain. Review verified the shared M7 catalog/completion shapes, direct SDK request handler, version-conditional status, cancellable DNS and checked-address/TLS design, bounded lock bridge, audit/cancellation uncertainty and independent fixture boundary. Concrete limits, the 200-character original-name compatibility cap, stateless downstream/ephemeral upstream sessions and these security choices still await user design approval. Dependency resolution, transport exception/stream-close behavior and all runtime acceptance claims remain to be tested during implementation.

## 11. Implementation and evidence

The user's subsequent concrete-design approval closed the historical review gate above. Implementation remains inside the existing M6 boundaries: one stateless external MCP endpoint, short-lived checked upstream sessions, version-bound discovery, shared three-argument execution, trusted per-invocation metadata and one audit lifecycle. M10 still owns real platform/upstream integration.

Implemented files: `backend/gateway/{server,discovery,router,upstream_client,context,common,schema}.py`, independent `tests/gateway/`, and `scripts/m6/`. The only M5 source seam is keyword-only `expected_version` status compare-and-set using the existing version column; no migration. Actual PostgreSQL regression checks passed: 42 cases, including this seam. Shared Helm/dependency/image ownership remained with the parent agent.

Implementation refinements:

- Direct SDK request handling preserves protocol unknown-tool errors and prevents pre-audit validation or raw exception-text shortcuts. Upstream tool invocation uses SDK `send_request` so untrusted result schemas are checked only by the bounded gateway validator.
- The schema subset explicitly rejects all references, patternProperties and unreviewed patterns; supports the five reviewed linear local-tool patterns; bounds nodes, depth, composition and argument structure. Unsupported schemas fail clearly. This avoids unbounded regex/reference CPU behavior while preserving advertised supported schemas unchanged.
- Trusted request IDs normalize to UUID objects required by M5. Completion metadata pairs with invocation UUID even when audit start is unavailable. Delayed audit starts cannot create duplicate attempts; cancellation and failed finalization retain honest uncertainty.
- HTTP API errors include request UUIDs. Safe upstream execution-error payloads are preserved; invalid successful output schemas cannot be returned as `isError:false`. SDK child logging is suppressed, and multiline SSE events share the reviewed byte limits.

Observed checks: **52 distinct host cases** (41 full run, six catalog additions, three isolation/identity additions, two actual wrong-upstream-credential cases); **47 M6 Linux cases** within the combined 119-case M6/M7 run; **12 live cluster check groups**. Host tests include real TCP JSON/stateful SSE, actual test-CA TLS original-host validation, forbidden/mixed/rebound DNS, pagination/bounds/collisions, current identity, concurrent peer isolation, audit-stage failures and cancellation. The five later host evidence additions do not increase the recorded Linux count.

Live measurements: tool list six items in **0.066 seconds**, timeout in **10.031 seconds**, outage status in **1.129 seconds**; other peers remain usable, stale preview is honest, restored header Pod has a new UID and succeeds, disabled names are denied and revoked key returns 401. Actual allowed-denied-allowed NetworkPolicy evidence is saved. All four observed Pod image IDs match the verified Docker configuration digest. Original shop/Pod/PVC identities are unchanged, and generated credential scans found zero matches in saved artifacts/logs.

See [report](../evidence/m6/report.md), [runbook](../evidence/m6/runbook.md) and [raw cluster results](../evidence/m6/cluster-results.json). Raw results retain their historical `PASS_RUNTIME_REVIEW_PENDING` status. The separate [independent review](../evidence/m6/acceptance-review.md) and [derived acceptance results](../evidence/m6/acceptance-results.json) mark all 12 criteria PASS, with user acceptance pending. The owned M6 namespace has been removed; the final root check confirms seven original identities unchanged and both disposable M5/M6 namespaces absent. Neither these controlled fixtures nor unit tests prove real M5 persistence-backed dispatch, actual shop writes, Codex/Inspector, dashboard UI or the final two-user flow.
