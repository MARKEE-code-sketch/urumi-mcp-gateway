# Platform API agreement — M0 design draft

**Status:** Design approved by the user on 14 October 2026. Application behavior is not implemented; local M0 fixtures exercise only the documented sample messages.

## What, why, and how

**WHAT:** Agree on messages between the React dashboard and Python backend. An API is the doorway through which programs ask each other for things.

**WHY:** Separately built modules can use the same example messages.

**HOW:** The browser asks, the backend checks the person, performs an allowed action, and replies. M5 owns accounts, keys, registry, and audit storage; M6 owns tool discovery/execution; M7 owns chat; M8 owns screens. M10 connects the real modules.

## Shared rules

Dashboard root: /api/v1, accepting login cookies only. External MCP root: /mcp, accepting Authorization: Bearer <personal-gateway-key> separately. IDs are UUIDs; timestamps are UTC ISO 8601, e.g. 2026-10-14T09:30:00Z. Shop-day calculations use Asia/Kolkata.

JSON successes return direct objects. Resource creation returns 201; reads/updates and login return 200; delete/logout/revoke return 204 without a body. Lists accept page (default 1), per_page (default 20, maximum 50), with stable newest-first ordering by created timestamp then ID; audit uses event timestamp then ID.

    {"items":[],"page":1,"per_page":20,"has_more":false}

Failures never include credentials or exception traces:

    {"error":{"code":"FORBIDDEN","message":"Admin access is required.","request_id":"811266b5-0dba-46ee-a850-3061d90ea661"}}

| HTTP | Meaning / code |
|---|---|
| 401 | Missing/expired session or incorrect login: UNAUTHENTICATED. |
| 403 | Disallowed action: FORBIDDEN; failed origin/CSRF check: REQUEST_REJECTED. |
| 404 | Missing or non-visible resource: NOT_FOUND. |
| 409 | Duplicate email/slug, spent invite, conflicting change: CONFLICT. |
| 422 | Invalid input, expired invite, forbidden URL/header: INVALID_INPUT. |
| 503 | Required database/Secret operation unavailable: DEPENDENCY_UNAVAILABLE. |

Proposed browser protection: HttpOnly, SameSite=Lax cookie; Secure on HTTPS production. Authenticated changing requests require allowed Origin and session-bound CSRF token; login/redemption validate Origin too. Never log cookies, credential-bearing bodies, or invite links/tokens.

## Accounts and invitations

No public signup/bootstrap route. Operator supplies first-admin email/password through a Kubernetes Secret. An explicit bootstrap command hashes the password and creates an admin only if none exists; it never resets existing accounts. Remove bootstrap Secret after success. Password/identity details belong to [identity-and-audit.md](identity-and-audit.md).

| Route | Caller | Request → response |
|---|---|---|
| POST /auth/login | Public | {email,password} → user, csrf_token; sets cookie. |
| POST /auth/logout | Session | Empty → invalidates session, clears cookie; 204. |
| GET /auth/me | Session | → user, csrf_token. |
| POST /invitations | Admin | {email,role:"member"} → id,expires_at,invite_url; 201. |
| POST /invitations/redeem | Public | {token,password} → user; 201, then login normally. |
| GET /members | Admin | → paginated users. |

User: {id,email,role,created_at}, never password hashes. Roles: admin/member. Invitations create members; no role-editing feature. Proposed lifetimes: invite 24 hours; fixed session 8 hours. Invite binds email, stores only token hash, and consumes atomically. Existing account/pending invite returns 409. Invalid/spent tokens receive safe generic failure; expired token returns 422. Invite URL appears only at creation, using a browser fragment; browser submits token in redemption body. Share manually; email delivery is excluded.

## Personal gateway keys

Members issue/list/revoke their own keys; admins may target any user. Verify ownership from session, never trust the path's user ID. Multiple keys per owner are supported.

| Route | Input → response |
|---|---|
| POST /members/{user_id}/keys | {label:"Codex demo"} → metadata plus raw_key, 201. |
| GET /members/{user_id}/keys | → paginated metadata, including revoked keys. |
| DELETE /members/{user_id}/keys/{key_id} | → revoke, 204; repeating an owned existing key remains 204. |

Metadata: {id,user_id,label,prefix,created_at,revoked_at}. Raw key appears only in issuance response with Cache-Control: no-store; only hash persists. Missing key returns 404. An admin-issued key belongs to target user. Revocation blocks the next MCP request after revocation commits, even in an existing MCP session. Already-dispatched upstream work may finish; see the in-flight exception in [identity-and-audit.md](identity-and-audit.md).

## Server registry and tool preview

| Route | Caller | Purpose |
|---|---|---|
| GET /servers | Session | Paginated redacted summaries. |
| GET /servers/{id} | Session | One redacted summary. |
| POST /servers | Admin | Create name, unique immutable slug, url, enabled, credential. |
| PATCH /servers/{id} | Admin | Edit name/url/enabled/credential; slug change returns 422. |
| DELETE /servers/{id} | Admin | Remove registration and owned Secret; 204. |
| GET /servers/{id}/tools | Session | Paginated discovered names, descriptions, input schemas. |

Placeholder example; never put real credentials in documentation:

    {"name":"Example MCP","slug":"example","url":"https://mcp.example.test/mcp","enabled":true,"credential":{"type":"header","header_name":"X-API-Key","value":"<upstream-key>"}}

Credential alternatives: {type:"none"} or {type:"bearer",value:"<upstream-token>"}. Creation defaults to none. PATCH omission retains credentials; type none explicitly clears them. Inputs are write-only. Internal records hold a Kubernetes Secret reference. Responses expose neither values nor references. Member summaries omit URL/auth configuration; admin summaries additionally show URL, auth type, and configured header name.

Summary: {id,name,slug,enabled,status,last_checked_at,status_reason,created_at,updated_at}. States: Connected / Unreachable / Disabled. Disabled wins immediately. New enabled record starts Unreachable/NOT_CHECKED. Other safe reasons include AUTH_FAILED, TIMEOUT, CONNECTION_FAILED, never raw upstream errors. Valid registration may save while remote server is unreachable. Checks are bounded per server. An Unreachable server retains its last successfully discovered preview when cached, marked stale:true in the top-level paginated reply; never-discovered servers return empty items. Connected previews use stale:false. Disabled previews always return empty items and stale:false. GET /servers/{id} supplies status. Preview items include gateway and upstream names. A stale preview is information, not permission to execute; disabled execution is always rejected.

Proposed header rules: valid HTTP header name; reject CR/LF and reserved headers: Host, Cookie, Authorization (use bearer mode), Proxy-Authorization, Content-Length, Connection, Transfer-Encoding, Origin, Accept, Content-Type, and MCP session/version headers. Never forward the caller's cookie/key upstream.

Proposed URL policy: public HTTPS; operator-allowlisted internal MCP Services may use HTTP. Reject embedded credentials, fragments, other schemes, loopback, cloud metadata, and non-allowlisted private/link-local destinations. Validate resolved destination when connecting and refuse redirects. This permits our Services while limiting access to unrelated internal resources. DNS defenses require review; this is not a claim of complete SSRF protection.

Credential update must not activate partial new state: stage replacement Secret, commit registry reference, retire old Secret. Failure preserves previous usable configuration or leaves new registration inactive; return 503. Removal disables routing first, then removes owned Secret/row. Failed cleanup leaves disabled retryable record, never usable partial state. Removing registration does not delete the remote application.

Shared internal registry adapter: get_server, list_servers(enabled_only), create_server, update_server, remove_server, set_server_status. Internal get/list include credential reference; public serialization strips it. Secret adapter resolves/writes/deletes owned credentials only. M5 supplies adapters; M6 cannot retrieve arbitrary Secrets.

## Activity and chat

GET /audit returns paginated entries from the identity agreement. Proposed visibility: member own events, admin all. Filters: server_id, outcome; user_id is admin-only. Enforce visibility before filters.

POST /chat takes {message:"What orders came in today?"}; no caller-provided user ID, role, credential, or tool-result fields. M5 supplies verified principal {user_id,role,auth_source:"session",key_id:null}; external MCP uses auth_source api_key and key ID. Chat calls M6's internal invoke_tool(principal,tool_name,arguments), never upstream directly or through a fabricated key. Gateway request context supplies correlation rather than a caller-supplied fourth argument. Internal reply: {request_id,audit_id,outcome,result:<MCP CallToolResult>}; identity agreement defines trusted principal creation.

Reply: {request_id,state,answer,tool_calls:[]}. Each actual call includes call_id, tool_name (public gateway name), server_id, outcome, duration_ms, audit_id, and optional safe error code or sanitized result summary. Outcomes: success, error, timeout, denied, unknown; never imply a timed-out write definitely failed. Failed attempts stay visible. Proposed terminal states: completed, failed, limit_reached. Maximum eight model/tool rounds; exhausted budget/provider failure returns honest partial results. Failures before processing use HTTP error envelope. Chat is transient per request; no saved conversation feature. Provider keys come from server-side Secrets, never replies/model-visible tool arguments.

## Planned checks

Independently check role/ownership rules, cookie/key separation, one-use invites, key disclosure/revocation, redaction, failed Secret operations, disabled/unreachable previews, and chat attribution with fixtures. These are plans, not observed evidence. Design approval precedes experiments and application implementation.
