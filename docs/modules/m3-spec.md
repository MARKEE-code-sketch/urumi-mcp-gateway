# M3 specification — our shop tool translator

**Status:** Specification and design approved by the user. Implementation independently reviewed and verified: 18 local tests and six live Kubernetes check groups PASS. Awaiting user module acceptance; real shop integration remains M10. See [verification report](../evidence/m3/report.md).  
**Date:** 15 October 2026.  
**Sources:** Assignment DOCX, [blueprint M3](../../blueprint.md#m3-our-woocommerce-mcp-server), [approved M0 tool contract](../../contracts/mcp-tools.md), [exact schemas](../../contracts/mcp-tools.schema.json), and [decisions](../decisions.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Write a small server that offers the five shop actions required by the assignment.

**WHY:** WooCommerce understands shop API requests. Our gateway understands MCP tool requests. This server is the translator between them.

**HOW:** Receive a named tool and its inputs, check them, call the shop API, and return only the agreed product/order fields. For example, create_product with “Blue Mug” and “299.00” becomes a request to create a simple published product priced in INR.

**What you will see at the end:** A test client discovers five tools and exercises them against a pretend shop. This proves our translator independently. Connecting it to the real M2 shop is an explicit M10 integration check.

## 2. The few words you need now

| Word | Simple meaning |
|---|---|
| MCP | The standard conversation used to discover and call tools. |
| Tool / schema | A named action / the checklist defining its accepted inputs and replies. |
| Streamable HTTP | The required web transport carrying MCP messages. |
| REST API | WooCommerce’s existing programmatic shop interface. We use its v3 API, not database queries. |
| SDK | A library handling the MCP protocol so we can focus on shop behavior. |
| Fixture | A pretend shop returning controlled examples, including failures. |
| Pagination | Returning a small page of results at a time instead of the entire shop. |
| ClusterIP / Secret | An internal Kubernetes service address / a credential object. A Secret is not automatically encrypted at rest. |

## 3. One request, in order

~~~text
Gateway (later, in M10)
         |
         v
Our WooCommerce MCP server
         |
         v
Validate tool inputs
         |
         v
WooCommerce REST API
         |
         v
Return the agreed fields
~~~

For M3 checks only, replace the gateway with a temporary MCP test client and WooCommerce with a fake REST server. These are testing stand-ins, not early integration. Browser pages, AI models, and payment providers are unnecessary for M3.

## 4. Scope and module boundary

| Responsibility | Owner | Boundary |
|---|---|---|
| Run/configure the real shop and save its data | M2 | M3 must not change its chart templates, setup scripts, or live products/orders. |
| Implement five tools and REST translation | M3 | Use the already approved M0 contracts; do not silently change tool names or schemas. |
| Identity, key checks, audit, server registry | M5/M6 | Not duplicated inside the shop tool translator. |
| Connect the real shop, translator, gateway, and chat | M10 | Real-store behavior and two-user evidence remain future checks. |

M2 and M3 can proceed in parallel because M3 uses a fake REST API. No installed WooCommerce MCP server/plugin is allowed: we write this server ourselves. Inventory lookup belongs to M4, not M3.

## 5. The five tools

The linked M0 JSON schemas are authoritative for exact types, bounds, and reply fields. The table is a reading guide.

| Tool | What it accepts | What it returns |
|---|---|---|
| list_products | Optional search, exact sku, page, per_page | Product items plus page, per_page, has_more. |
| create_product | Required name, regular_price; optional sku | The created Product. |
| list_orders | Optional created_from, created_to, status, page, per_page | Order items plus page, per_page, has_more. |
| get_order | Required positive integer order_id | One Order. |
| update_order_status | Required positive integer order_id and permitted status | The updated Order. |

### Inputs and replies

- Reject unknown arguments and wrong types before any REST request; do not turn text IDs or booleans into integer IDs silently.
- Trim names, search, and SKUs; reject blank values. Name/search maximum 200 characters; SKU maximum 100.
- Page starts at 1. per_page defaults to 20, maximum 50. Empty results succeed; has_more must reflect additional matching results without skipping them.
- Prices are nonnegative decimal **strings**, at most 32 characters and two fractional digits. Example: “299.00”. Reject floats, negative numbers, exponent notation, and extra fractional digits. Normalize returned prices to two digits; preserve allowed null product prices.
- Create a simple published product. A duplicate SKU fails clearly. Update only the requested order status; it does not promise a payment refund.
- Accepted write/filter statuses: pending, processing, on-hold, completed, cancelled, refunded, failed. Preserve an existing source status string in replies; custom status writes and trash are excluded.
- Return only the Product/Order fields in the contract. Orders include line items; product_id may be 0 for deleted/manual items. Omit billing/shipping addresses, emails, phone numbers, payment tokens, and raw metadata.
- Tool arguments cannot select a destination URL, supply a credential, or override a caller identity. Read/write effects must be clear in tool descriptions and annotations.

### “Today” and dates

created_from and created_to are optional offset-aware ISO8601 timestamps; reject invalid dates, missing offsets, and reversed ranges. Bounds are inclusive; an omitted bound leaves that side open.

M3 accepts timestamps rather than guessing what “today” means. M7 captures one current time, converts Asia/Kolkata midnight to UTC, and supplies fixed bounds across pages. Example: 15 October midnight IST is 14 October 18:30 UTC.

Use the v3 orders API with dates_are_gmt=true, normalize date_created_gmt to UTC, and test before/exactly-at/after boundary records. If WooCommerce excludes a boundary, widen its query and filter to the agreed interval without losing matching records during pagination. M10 must confirm this against the installed shop; fixtures alone cannot prove its behavior.

## 6. Protocol, credentials, and failures

Use the official Python MCP SDK over Streamable HTTP. Reuse M0’s proven Python dependency baseline as design evidence, not as an automatic application dependency lock. Record negotiated protocol/package versions. Section 11 specifies proposed pins, lifecycle, limits, and container settings for design review.

Successful calls have isError=false, structuredContent matching the advertised outputSchema, and the same object serialized in a text block. Execution failures use isError=true with a safe text error object and omit success-shaped structuredContent. Malformed protocol messages and unknown tools use standard SDK/MCP errors.

| Situation | Required behavior | Check |
|---|---|---|
| Invalid arguments / missing order | INVALID_ARGUMENT / ORDER_NOT_FOUND; no raw shop error body. | Invalid inputs make zero REST calls. |
| Duplicate SKU | Clear safe execution error; no fabricated successful product. | Observe one failed creation request. |
| Bad store credential | UPSTREAM_AUTH_FAILED without exposing credential or response body. | Fake 401/403 responses. |
| Unavailable / invalid shop response | UPSTREAM_UNAVAILABLE / UPSTREAM_PROTOCOL_ERROR. | Connection failure, invalid JSON, invalid required fields. |
| Slow shop / uncertain write | UPSTREAM_TIMEOUT; explain a write may have completed. Never automatically retry writes. | Delayed read and write; exactly one write attempt. |

Use finite REST deadlines within the approved 10-second tool budget; precise internal timings belong in design. Bound payload/work sizes and return an explicit failure rather than silently truncate a complete-looking reply. Avoid retry machinery unless independently justified and reviewed.

The configured shop REST credential comes from a Kubernetes Secret, not tool arguments or Helm values containing plaintext keys. M2 prepares the real credential; M3 checks use fake keys until M10. Never forward a member’s gateway key/cookie to WooCommerce. Do not log authorization headers, credential-bearing URLs, raw API bodies, or customer contact data. Test sentinel secret and personal fields to prove their absence in outputs/logs.

### Approved authentication choice

The user selected signed OAuth 1.0a over local HTTP. This authenticates our server to the shop without a browser login; it is separate from gateway users' API keys and optional gateway OAuth. Put the signature parameters in the Authorization header. M2 checks the real REST credential independently; M3 uses fake keys until M10. HTTP still exposes data and does not protect the JSON request body from modification: signing is authentication, not encryption. Production transport changes must be explicitly designed with trusted HTTPS; never fake an HTTPS indicator, disable certificate verification, or put raw secrets in URLs.

## 7. Kubernetes boundary

The server runs as one workload with a ClusterIP Service, readiness/liveness probes, and CPU/memory requests/limits. It has **no Ingress, NodePort, LoadBalancer, or routine host port-forward**. NetworkPolicy permits the gateway workload to reach its MCP port and blocks unrelated Pods; the server needs no Kubernetes API permissions or database connection.

Readiness means the translator can accept requests with valid local configuration; liveness checks its own process. A shop outage must produce safe tool failures without a restart loop. Section 11 specifies probe endpoints and container settings.

An isolated M3 test harness may temporarily stand in for the gateway caller to test this boundary against a fake shop. Its labels/selectors and namespace must be explicit; it is not the real gateway. Remove that client, fake shop, and temporary permissions afterward. No direct client access exception remains in the final system. M10 separately proves the boundary with the real gateway.

## 8. Planned files and ownership

| M3-owned paths | Purpose |
|---|---|
| services/woocommerce_mcp/server.py | Register the five tools and HTTP/probe endpoints. |
| services/woocommerce_mcp/tools.py, schemas.py | Validate inputs, shape safe replies, preserve the approved schemas. |
| services/woocommerce_mcp/woocommerce_client.py | Configured REST access, deadlines, safe error mapping. |
| services/woocommerce_mcp/Dockerfile and dependency files | Reproducible translator image and pinned dependencies. |
| tests/woocommerce_mcp/ | Fake REST fixture, real MCP transport checks, validation/security checks. |
| deploy/charts/urumi/templates/woocommerce-mcp/ | Translator workload, internal Service, and scoped network policy. |
| docs/evidence/m3/ | Commands, schemas, test results, cluster observations, review, limitations. |

The main agent owns shared chart values/helpers and cross-module documents. M3 supplies a reviewed values fragment/change proposal rather than editing shared files concurrently with M2. M3 owns no shop PVC or platform database migration. Disposable test resources must have a separate, explicit cleanup list.

## 9. Measurable acceptance

All checks below are planned; none is currently PASS. Unit checks alone do not prove MCP transport or cluster enforcement.

| ID | Required result | Saved evidence |
|---|---|---|
| M3-01 | Real MCP client initializes and discovers exactly the five tools with contract-matching schemas/annotations. Record negotiated version; a direct call before list also works. | protocol.txt, discovered-tools.json |
| M3-02 | Exercise all five successes through real Streamable HTTP against fake REST. Match method/path/query/body, output schemas, and text/structured equality. | tool-calls.json, rest-observations.json |
| M3-03 | Unknown fields, blanks, length bounds, bad IDs/types/prices/statuses/dates and reversed dates fail safely with zero REST dispatches. | validation-results.json |
| M3-04 | Two or more pages, empty results, search/exact SKU, and final has_more=false work; inclusive UTC bounds include exact endpoints without skipped results. | pagination-and-dates.json |
| M3-05 | Missing order, duplicate SKU, 401/403, connection failure, malformed JSON, and invalid source fields produce safe distinct failures; next healthy request succeeds. | failure-results.json |
| M3-06 | Delayed read/write respect configured finite deadlines; timed-out write makes exactly one REST attempt and warns of uncertain completion. | timeout-results.json |
| M3-07 | Sentinel credential/contact fields are absent from results/logs; only configured fake REST auth is sent. Input cannot override destination, auth, or identity. | redaction-check.txt |
| M3-08 | Same shared chart renders local/production translator resources; image starts in isolated Kubernetes harness with probes/resources, Ready status, and observed liveness behavior. | helm-checks.txt, workload-status.yaml |
| M3-09 | Permitted gateway stand-in can initialize/call; unrelated Pod cannot connect within a deadline; allowed call succeeds again. No public translator exposure exists. | exposure-and-policy.txt |
| M3-10 | Clean up all temporary clients/fake-shop/permissions. Review exact commands, results, schema alignment, and remaining M10 gaps before user acceptance. | cleanup.txt, report.md |

## 10. Work order and review gate

1. **Completed:** The user approved M2/M3 specification scopes and selected OAuth 1.0a local REST authentication.
2. **Now:** Review the concrete design below alongside M2. Independently review and obtain user design approval before application implementation, following AGENTS.md.
3. **After design approval:** Implement only M3-owned files. Coordinate shared values through the main agent; independently review, then run approved checks.
4. **Handoff:** Explain one read and one write from MCP to REST and back. Report PASS/FAIL/BLOCKED honestly; user accepts M3 before integration.

**Known gaps:** Fake REST proves translator logic, not installed WooCommerce compatibility, real credential validity, storefront visibility, timezone API behavior, gateway audit, or two-user access. Those remain M10 checks. M0 Inspector shutdown and live Codex compatibility are also deferred to M10.

**Specification review:** The earlier [independent specification review](m2-m3-spec-review.md) found no blockers; the user subsequently approved the scopes. The detailed design below has its own review gate. Future modules keep their specification and design in their own module file; no additional parallel-plan specification is needed.

### Technical references

The assignment defines the requirements; these primary references explain protocol/API behavior: [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools), [WooCommerce products](https://developer.woocommerce.com/docs/apis/rest-api/v3/products/), [WooCommerce orders](https://developer.woocommerce.com/docs/apis/rest-api/v3/orders/). [WooCommerce authentication](https://developer.woocommerce.com/docs/apis/rest-api/authentication/) defines the transport/auth constraints above. The M0 contract remains the agreed application message boundary.

## 11. Detailed design for review

### 11.1 WHAT, WHY, HOW

**WHAT:** One Python process translates the five agreed tools into WooCommerce REST requests. **WHY:** The SDK supplies MCP plumbing while our code supplies the assignment's shop behavior. **HOW:** SDK dispatch -> strict schema/semantic checks -> signed REST request -> allowlisted fields -> output-schema check -> MCP result. A fake shop and a real MCP client check that whole path independently before the real shop is connected in M10.

Use one small server, not a separate service for every file. A Deployment is Kubernetes' instruction to keep this Docker container running; its Service supplies a stable internal address. NetworkPolicy is the checked caller restriction, not user authentication. Gateway roles, keys, and audit remain M5/M6 responsibilities.

### 11.2 Runtime and file responsibilities

| File / dependency | Concrete responsibility |
|---|---|
| `server.py` | Construct low-level SDK Server, list five contract definitions, dispatch calls, manage lifespan, expose `/mcp`, `/livez`, `/readyz`. |
| `schemas.py` | Load only the five approved M0 definitions; strict Draft 2020-12 validation with format checking and semantic date validation; validate normalized output too. Package the unchanged contract JSON in the image. |
| `tools.py` | Dispatch the five operations; pagination/filtering; normalize Product and Order; produce safe success/error envelopes. |
| `woocommerce_client.py` | Validate fixed configuration, sign canonical requests, send to fixed internal origin, enforce streamed byte/time limits, classify safe errors. Keep signing in this file rather than a new service. |
| `requirements.in`, `requirements.lock.txt`, `Dockerfile` | Reproducible direct and transitive dependencies and image; generate Linux lock during implementation and run `pip check`. |
| `tests/woocommerce_mcp/` | Unit checks, independent fake REST service, real Streamable HTTP client, Kubernetes harness definitions; fake credentials only. |
| `scripts/m3/check-m3.ps1` | Later evidence runner: prerequisite checks, explicit harness creation/checks, cleanup, honest PASS/FAIL/BLOCKED report. |

Proposed pins reuse M0's tested baseline: Python `3.13.5-slim-bookworm`, `mcp==1.26.0`, `httpx==0.28.1`, `jsonschema==4.26.0`, `starlette==0.52.1`, `uvicorn==0.40.0`. Add `oauthlib==3.3.1` for standard signing instead of inventing cryptography. Resolve the base image to its immutable digest before building. These are compatibility candidates, not a claim of a current vulnerability audit or Linux runtime PASS; a broken/incompatible candidate blocks implementation acceptance and must be reported before changing the design.

The translator needs an ASGI web wrapper for MCP/probes only; use Starlette already present in the SDK baseline. FastAPI remains the selected dashboard/backend stack and adds no needed behavior to this translator. This keeps schemas equal to M0 rather than regenerating different ones from Python function signatures.

### 11.3 MCP lifecycle and validation

Create `StreamableHTTPSessionManager(app=server, stateless=True, json_response=True)`. Start `manager.run()` and one shared `httpx.AsyncClient` in ASGI lifespan; close both on shutdown. Stateless mode needs no stored session ID or event replay and fits short request/reply tools. The real client still runs initialize; record actual negotiated protocol and installed versions instead of claiming an unobserved protocol version. Return all five tools in one tools/list reply, with original names, descriptions, inputSchema, outputSchema, and annotations copied from M0. No inventory/diagnostic tool is registered.

Use `call_tool(validate_input=False)` because our validator must return safe `INVALID_ARGUMENT` without echoing invalid values. Extend jsonschema's integer type checker to require `type(value) is int`: the default JSON Schema validator can accept `1.0` as an integer, while this approved contract requires strict Python/JSON integer input and source fields. Booleans/floats/text are not integer IDs; money stays a string. Apply the same checker to outputs and test `1.0`/true for IDs, page, per_page, product_id and quantity. Trim only name/search/sku before schema validation, then check timestamps/range. Register an outer name guard producing SDK invalid-params for unknown tools; SDK's inner decorator catches handler exceptions, so raising only inside it is insufficient. Handle list-tools' internal cache lookup without a request; test a direct call after initialization before tools/list.

On success validate the exact object against its copied outputSchema before returning `CallToolResult(isError=False, structuredContent=object, content=[TextContent(JSON(object))])`. On execution failure return `isError=True`, one text JSON `{"error":{"code":"...","message":"..."}}`, no structuredContent. Unexpected source values produce `UPSTREAM_PROTOCOL_ERROR`; never invent missing required data or trim source fields to make them fit. Log fixed codes, tool name, duration and a local correlation ID only; error messages and SDK logging must not include raw arguments, bodies, headers, URLs with credentials, or exception text containing them.

Limit incoming `/mcp` body to 64 KiB with an ASGI streamed-body guard (not merely Content-Length); return HTTP 413 on overflow. Reject browser Origin requests; allow absent Origin for gateway SDK traffic. Check Host against exact service DNS names configured by Helm; no CORS wildcard or public-origin access is needed. These transport checks complement the tested NetworkPolicy.

### 11.4 Fixed shop settings and OAuth signing

| Setting | Real value for eventual M10 handoff | M3 check value |
|---|---|---|
| `WOO_CANONICAL_ORIGIN` | `http://shop.urumi.test` | `http://fake-shop.urumi.test` |
| `WOO_TRANSPORT_ORIGIN` | `http://urumi-wordpress.urumi.svc.cluster.local` | `http://m3-fake-shop.urumi-m3-check.svc.cluster.local:8080` |
| REST path | `/wp-json/wc/v3` | Same path |
| `WOO_CURRENCY` | `INR` | `INR` |
| Credential Secret | `urumi-woocommerce-rest`: `consumer-key`, `consumer-secret` | Separate `m3-fake-woocommerce-rest` with deliberately public fake values |
| Shop identity | M2's dedicated `urumi-integration` shop_manager; read_write key | No real account or key |

Canonical origin means the shop's configured public identity; transport origin means the internal network address we actually connect to. Validate origins at startup: http/https only, no userinfo/query/fragment, no trailing application path; REST path and destination come from configuration, never arguments. For local real-shop requests, sign `http://shop.urumi.test/wp-json/wc/v3/...` including exactly the outgoing query, then send that same path/query to the internal Service with fixed `Host: shop.urumi.test`. WooCommerce builds its verification URL from its configured home URL; do not sign the Kubernetes DNS URL. M2 proves the configured home URL and header reach the installed API unchanged; M3 reproduces the expected verification with fake keys. Redirects are disabled and are an upstream protocol failure, preventing credentials from being sent onward or signatures from silently changing.

Use OAuthlib one-legged client, HMAC-SHA256 and Authorization-header signature placement. Its 3.3.1 client includes oauth_version by default: a small `get_oauth_params` override filters oauth_version before signature calculation, not after. Sign with no body, then attach the JSON body for dispatch, avoiding OAuthlib's optional oauth_body_hash extension, which WooCommerce does not require. Generate fresh 32-character random nonce and current Unix timestamp per REST request. Include method, canonical URL and query parameters in the signature; JSON bodies are not signed in this WooCommerce scheme. Never forward gateway Authorization/cookies. Fixed vectors freeze nonce/time and independently verify WooCommerce's actual encoding (spaces, Unicode, ampersands), query sorting, method differences and canonical-versus-transport origins. Disable OAuthlib debug logging because it includes signing parameters. Assert no consumer-secret appears in headers/URLs/logs; the consumer key/signature are also redacted from evidence. Fake verifier must not simply call the same production signing function. Generic OAuth-library compatibility is not assumed: failure of WooCommerce-specific vectors blocks this design choice; M2's actual shop REST check remains essential independent evidence.

HTTP does not encrypt responses or authenticate JSON body integrity. This is the user's approved local-development tradeoff; no signature-only design is described as end-to-end transport security. A VPS HTTPS route must use matching canonical scheme/host and verified TLS, supplied through values and checked before production claims.

### 11.5 Exact REST mapping and normalization

| MCP operation | REST operation | Translation |
|---|---|---|
| list_products | `GET /products` | Send search/sku if supplied, `orderby=id`, `order=asc`, `per_page=100`, source page starting at 1. Apply exact trimmed SKU equality locally before logical pagination. |
| create_product | `POST /products` | JSON `{name, regular_price, type:"simple", status:"publish"}`, plus sku only when supplied. Return `{product: Product}`. |
| list_orders | `GET /orders` | `dates_are_gmt=true`, `orderby=id`, `order=asc`, `per_page=100`; supplied status plus widened after/before bounds below. Return logical filtered page. |
| get_order | `GET /orders/{order_id}` | Validated positive integer only. Return `{order: Order}`. |
| update_order_status | `PUT /orders/{order_id}` | JSON contains only status. Return `{order: Order}`; no refund endpoint or payment action. |

Build query/body from this allowlist. Product projection is exactly `id,name,sku,price,regular_price,currency,status,permalink`; currency comes from `WOO_CURRENCY` because WooCommerce's product object does not include it. Preserve absent-price `null` (empty price string becomes null), normalize valid decimal strings to two places with Decimal, reject negative/nonfinite/malformed amounts. Order projection is exactly `id,number,status,currency,total,date_created,line_items`; each line item exactly `product_id,name,sku,quantity,total`. Preserve custom source order status but accept only the seven contracted statuses for filter/write. Null/missing required data or incompatible IDs/quantities/field lengths fail safely; do not supply guessed SKU/number/date values. Parse `date_created_gmt` as UTC even when WooCommerce omits its timezone suffix, then return a `Z` timestamp. Never fall back silently to store-local date_created.

Both list tools use a small bounded scan so post-filtering cannot leave gaps between pages: scan source pages in ascending ID order, discard nonmatching records, skip `(page-1)*per_page` matching records, gather `per_page+1` matches. Return the first per_page; extra match means has_more=true. A short source page (fewer than 100) means exhausted. Validate WooCommerce's `X-WP-TotalPages` integer header and use it only to detect source exhaustion, including an exactly-full final page; this avoids requesting an invalid extra page. Missing/malformed required pagination headers fail as an upstream protocol error. Do not use raw source totals to calculate filtered has_more. Cap at 20 source pages / 2,000 source records per tool call; if the requested logical page or lookahead cannot be established within that cap, return safe `UPSTREAM_LIMIT_EXCEEDED`, never a complete-looking truncated reply. No snapshot guarantee during concurrent shop edits; fixed bounds and ID ordering make the demo reproducible with a quiet fixture/store.

Normalize input timestamps to UTC. For a lower bound send after=floor-to-second(lower)-1 second; for upper bound before=ceil-to-second(upper)+1 second, as UTC ISO8601 values with dates_are_gmt=true. Enforce the original inclusive timestamps locally on every source record before logical pagination, preserving fractional-second caller bounds. Reject bounds that cannot be safely widened because they exceed datetime range before REST dispatch. Test matching records at both endpoints, extra surrounding records, and a boundary excluded from a source page. The installed shop's timezone/filter behavior remains an M10 acceptance check.

### 11.6 Deadlines, payloads, and failures

Set a whole-tool deadline of 8 seconds, leaving margin inside the approved 10-second gateway budget. httpx phase limits: connect/pool 1 second, read/write 3 seconds, bounded by the remaining whole-tool deadline across all scan requests. Cap each decoded REST body at 2 MiB while streaming, total REST bytes at 8 MiB per tool call, normalized serialized result at 512 KiB. Oversize data returns `UPSTREAM_LIMIT_EXCEEDED`; no successful truncation. No automatic read or write retries, and no retry on connection errors or redirect. Each additional list source page is a different request, not a retry.

Map 401/403 to UPSTREAM_AUTH_FAILED; order lookup/update 404 to ORDER_NOT_FOUND; known WooCommerce duplicate-SKU code to PRODUCT_SKU_CONFLICT; other rejected validated writes to UPSTREAM_REJECTED with fixed wording. 5xx/connection failures map UPSTREAM_UNAVAILABLE; invalid JSON/types/required fields/redirects map UPSTREAM_PROTOCOL_ERROR. Do not copy arbitrary shop messages into errors. A timed-out or connection-lost dispatched write warns that it may have completed and needs checking before a manual retry. Validate HTTP status before treating a body as success, and verify the next healthy call still works after every injected failure.

### 11.7 Container and Helm resources

Real resources use release `urumi`, namespace `urumi`, Deployment/ClusterIP Service `urumi-woocommerce-mcp`, port 8000. Shared Helm values add `woocommerceMcp.enabled` (false by default until owning module activation), image digest, canonical/transport origins, currency, existingSecret, resource limits and gateway selector. Root agent merges these shared values; this module owns only `templates/woocommerce-mcp/`. No chart-created plaintext real credential.

Run one uvicorn worker as UID/GID 10001, non-root, readOnlyRootFilesystem, allowPrivilegeEscalation=false, drop all capabilities, RuntimeDefault seccomp; writable `/tmp` emptyDir only if needed. Disable service-account token mounting and create no RBAC. Requests 100m CPU/128Mi RAM; limits 500m/256Mi initially, report actual restarts/OOM before claiming enough capacity. No PVC/database/API permissions. No Ingress/NodePort/LoadBalancer/host networking.

`/livez` checks process responsiveness only. `/readyz` becomes healthy only after configuration, schemas, HTTP client and manager startup succeed; neither calls the shop. Probe period 10s, timeout 2s, failureThreshold 3; startup probe period 2s/failureThreshold 30. A fake-shop outage must cause tool errors while these probes remain healthy. Prove liveness restart by an explicit temporary probe-failure fixture in the isolated harness, then restore and observe Ready, rather than killing the production store.

Ingress NetworkPolicy selects name=urumi, instance=`<release>`, component=woocommerce-mcp, and permits TCP8000 only from same-namespace Pods with the same release/name and component=gateway. Exact final gateway labels are a contract to M6/M9. Restrict egress to kube-system DNS (UDP/TCP53) and configured shop-Pod selectors/port; harness overrides shop selectors/port to its fake shop. Namespace and Pod selectors must be combined when cross-namespace access is intended, never separate OR entries. This label-based rule trusts cluster administrators able to create/relabel Pods; it does not authenticate hostile administrators. Check no broader policy accidentally grants callers access.

### 11.8 Isolated Kubernetes check and cleanup

Use **namespace `urumi-m3-check`, Helm release `urumi-m3-check`**, same chart, foundation/shop/MariaDB disabled. Namespaced resources never target M2's namespace/release/PVC. Fresh root preflight found the Docker engine unavailable and existing Kubernetes API refusing connections; therefore live checks currently need the existing engine/cluster started, not a replacement cluster created. Import image `urumi/woocommerce-mcp:m3` into existing k3d cluster after confirming its exact name from M1 settings. Fake shop is a separately named test Deployment/Service `m3-fake-shop:8080` with probes and requests 50m/64Mi, limits 250m/128Mi. Client Jobs use the translator image, requests 50m/64Mi, limits 250m/128Mi, restartPolicy Never and activeDeadlineSeconds 90.

Allowed client Job: name=urumi, instance=urumi-m3-check, component=gateway. Denied client: same release/name, component=unrelated. Test finite connection timeout (3s) from denied client, successful initialization/all calls from allowed client, then allowed success again; a failure alone is not proof of enforcement. The fake shop permits only translator Pod REST traffic. Temporary Jobs execute an actual MCP SDK client through ClusterIP, without host port-forward or bypass. Harness creates only fake Secret data. Check node allocatable/resources and M2 state before creation; if capacity is insufficient, run module checks sequentially rather than resize the cluster silently.

Planned commands from project-root PowerShell, after design approval and creation of the named runner:

~~~powershell
python -m unittest discover -s tests/woocommerce_mcp -v
helm lint deploy/charts/urumi
helm template urumi deploy/charts/urumi -n urumi -f deploy/charts/urumi/values-local.yaml --set woocommerceMcp.enabled=true
helm template urumi deploy/charts/urumi -n urumi -f deploy/charts/urumi/values-prod.yaml --set woocommerceMcp.enabled=true
.\scripts\m3\check-m3.ps1
~~~

Runner resolves portable Helm/kubectl paths from M1 conventions if commands are not on PATH; captures actual resolved invocations. It deploys the separate harness with reviewed test values, waits for readiness, saves discovery/transcripts/REST observations and policy/probe evidence, then uninstalls only `urumi-m3-check` in `urumi-m3-check` and deletes only that dedicated namespace after confirming its ownership labels. No wildcard deletion or deletion of the k3d cluster. Record before/after M2 resource identities/PVCs and assert unchanged. Remove every temporary fake shop/client/Secret/policy; evidence remains under docs/evidence/m3. Failure also triggers scoped cleanup while preserving diagnosis; cleanup failure stays FAIL/BLOCKED.

### 11.9 Review and acceptance boundary

M3-01/02 prove real MCP envelopes/lifecycle against fake REST; M3-03 proves validation with zero dispatch; M3-04 exercises at least three source/logical pages, exact SKU and UTC endpoints; M3-05/06 check each safe failure and deadline with one write attempt; M3-07 checks secret/contact sentinel absence from results and captured logs; M3-08/09 prove rendered chart and observed process/probe/policy behavior; M3-10 proves scoped cleanup. Include signatures with fixed vectors and canonical/internal hostname mismatch in M3-02/07. Test oversized streamed bodies, work-limit failures, direct call before list, unknown tool, and fractional-second date bounds. Results are planned, not PASS.

**Independent design review:** READY FOR USER REVIEW with requested clarifications applied: strict integer checker/regressions; WooCommerce-version-specific OAuth fixtures; inclusive filtered pagination and finite work failure; SDK validation/name-guard behavior; real-store wiring deferred to M10. Against M2's selected WooCommerce 11.2.1, signature vectors must reproduce that tag's PHP normalization for literal `%20`, literal `%25`, plus versus space, Unicode, and ampersands, not only standard OAuth vectors. If OAuthlib's standard normalization differs, stop for design review rather than silently write a custom signer or claim authentication works.

**Design gate:** The user reviews this section together with M2 before implementation, as required by AGENTS.md. Implementation permission for the earlier scopes does not silently approve newly specified limits/settings. M10 alone connects the real translator to M2 and proves real product/order changes, gateway identity/audit, and external clients. No application implementation or live check result is claimed here.

Primary references checked for this design: [SDK v1.26.0 low-level server](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/src/mcp/server/lowlevel/server.py) and [session manager](https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/src/mcp/server/streamable_http_manager.py) document the APIs selected here. [WooCommerce authentication](https://developer.woocommerce.com/docs/apis/rest-api/authentication/) and [verification source](https://github.com/woocommerce/woocommerce/blob/trunk/plugins/woocommerce/includes/class-wc-rest-authentication.php) explain canonical URL signing; the selected installed plugin version must be verified in M2. [WooCommerce orders](https://developer.woocommerce.com/docs/apis/rest-api/v3/orders/) documents UTC filters and sorting. [OAuthlib client](https://oauthlib.readthedocs.io/en/latest/oauth1/client.html) explains standard signing; exact 3.3.1 behavior remains covered by fixed-vector tests rather than inferred from latest documentation.
