# M0: identity and audit agreements

**Status:** Design approved by the user on 14 October 2026. Application behavior is not implemented; local M0 fixtures exercise only the documented sample messages.

## WHAT, WHY, and HOW

**WHAT:** Identify the person asking for an action, check permission, and keep an honest activity record.

**WHY:** A shop action must belong to the correct teammate. A lost response must not make us claim that an order update succeeded or safely repeat it.

**HOW:** The dashboard presents a login cookie; an external MCP app presents a personal gateway key. The backend checks either credential and creates a trusted identity. Every tool action then uses the same gateway function and activity-recording path.

Example: A logs into dashboard chat and asks for today's orders. The chat calls the gateway as A. B's Codex app asks the same question using B's key. Both reach the shop with the shop credential, but their activity records name A and B separately. Neither receives the shop credential.

## Shared message rules

| Item | Agreement |
|---|---|
| Dashboard HTTP API | Prefix /api/v1; MCP stays a separate protocol endpoint. |
| Record identifiers | UUID strings, including users, keys, servers, invitations, sessions, audit attempts, and request IDs. |
| Time | ISO8601 UTC timestamps, for example 2026-10-14T10:30:00Z. Shop-day queries separately use Asia/Kolkata. |
| HTTP API errors | {"error":{"code":"KEY_REVOKED","message":"This key has been revoked.","request_id":"<uuid>"}}. Messages omit credentials and private payloads. |
| Trusted identity | {"user_id":"<uuid>","role":"admin","auth_source":"session","key_id":null}. Role is admin or member; source is session or api_key; API-key identity includes its key UUID. |
| Tool entrypoint | invoke_tool(principal, tool_name, arguments). Only backend authentication creates principal; never accept it from browser JSON, a model, or upstream output. |

An MCP tool error uses MCP's error/result conventions; it is not replaced by the dashboard HTTP envelope. Both paths retain a request ID for audit correlation.

## Login, invitations, and sessions

Local email/password accounts and manually shared one-use invitation links are confirmed. Admin creates member invitations; redemption sets a password and creates the account. Normalize email consistently and enforce uniqueness. Passwords use an established password-hashing library and its supported password algorithm; no home-made hashing.

Proposed defaults, awaiting approval: invitation expiry **24 hours**; session expiry **8 hours**, fixed from login. An expired or consumed invitation cannot be used. Invitation consumption and account creation occur in one database transaction with an atomic unused-to-used change: two simultaneous redemptions cannot create two accounts.

Invitation and session tokens are high-entropy random values stored only as cryptographic hashes. Login rotates the session token. Logout revokes the server-side session and clears the cookie. Use an HttpOnly, SameSite=Lax cookie; Secure on HTTPS. Local HTTP development is an explicitly documented exception. Check request origin and apply CSRF protection to cookie-authenticated state-changing actions. Session cookies, invitations, and passwords never appear in URLs except the invitation token in its one-use link; redact that link from logs and avoid third-party assets on redemption pages.

Recheck session expiry/revocation and the current account/role for every protected request and every chat tool execution. A conversation cannot preserve permission after its session becomes invalid. Member disabling, if implemented, invalidates all access paths.

## Personal gateway keys and permission boundary

Generate a high-entropy personal key and show its raw value once. Store key UUID, non-secret lookup identifier, owner UUID, hash, created_at, and revoked_at. Verify the whole presented key using a safe comparison; a guessed lookup identifier alone proves no ownership. Never store raw keys, place them in query strings, or return them later.

External clients send Authorization: Bearer <gateway-key>. The backend checks the stored hash, owner, and revocation state on every MCP request and immediately before each tool dispatch, including calls in an already-open MCP session. An MCP session ID is not authentication and cannot switch owners. Cookie authentication supplies dashboard/chat identity separately; revoking B's external key does not log B out of a valid dashboard session.

| Action | Admin | Member |
|---|---|---|
| Use all enabled tools and chat; inspect safe server/tool information | Yes | Yes |
| Register/edit/disable/remove servers; invite/manage members | Yes | No |
| Generate/revoke own keys | Yes | Yes |
| Issue/revoke another member's keys | Yes | No |
| See all team audit records | Yes | No |
| See own audit records | Yes | Proposed, awaiting approval |
| Retrieve raw saved credentials, another user's session/private chat | No | No |

Core members can create products and update orders through enabled tools. Per-tool restrictions are optional scope. Upstream credentials remain server-side. The gateway constructs upstream authentication from that server's saved configuration; it never forwards caller cookies, bearer keys, or caller-chosen headers.

Revocation stops calls that have not passed the final pre-dispatch check. A call already dispatched when revocation commits may finish and is audited normally; revocation cannot undo a remote action. Verify this boundary with a concurrent-call check rather than promise instant cancellation.

## One durable activity record per attempt

For each attempted tool execution, allocate one audit UUID and persist state running **before contacting the upstream**. Fields:

| Field group | Values |
|---|---|
| Correlation | audit_id, request_id |
| Caller | user_id nullable, key_id nullable, auth_source nullable |
| Destination | server_id nullable, public_tool_name, upstream_tool_name nullable |
| Timing | started_at UTC, finished_at nullable, duration_ms nullable |
| Outcome | running, then success / error / timeout / denied / unknown |
| Explanation | safe error_code and redacted error_summary, nullable |

Denials before dispatch follow the same one-record lifecycle; create running and finalize denied in one transaction without any upstream call. Unknown keys have null user/key IDs; do not trust a claimed owner or a key prefix. A cryptographically verified revoked key can be attributed to its stored owner/key. Unknown tools may have null server/upstream-tool fields. Never save raw credentials, full arguments/results, or unnecessary customer information in these records.

If the initial audit write is unavailable, fail closed: return AUDIT_UNAVAILABLE and do not execute. That unavailable database cannot itself save the rejected attempt; report the evidence gap honestly and emit only a sanitized operational error with request ID.

After dispatch, success requires an observed successful upstream result and committed audit finalization. Known tool failures become error; deadline expiry becomes timeout and may still leave a remote write uncertain. No automatic retries for uncertain writes. An interrupted running attempt becomes unknown during recovery, with duration unknown when timing cannot be reconstructed.

If finalization fails, do not report verified success: return AUDIT_FINALIZATION_FAILED with outcome uncertainty. The durable running row remains until recovery marks it unknown; do not claim the unknown transition was saved while the database is unavailable. Retrying a user request is a new attempt, never silent recovery of the previous action.

## Ownership and checks before implementation approval

M5 owns account/session/key validation, invitations, permissions, audit storage and visibility. M6 owns the execution entrypoint and dispatch audit lifecycle. M7 passes verified session identity for each chat tool action. M8 displays safe records and one-time key/invite outputs. Modules use samples independently; final integration follows their review gates.

Planned acceptance: duplicate invitation redemption; session expiry/logout; own/other-user authorization; missing/wrong/revoked key; existing-session revocation; concurrent revocation; chat attribution; audit rejection before dispatch; successful/failed/timed-out/denied calls; interrupted writes; failed finalization; credential redaction; member audit filtering.

**Open approval items:** 24-hour invitations, 8-hour sessions, and members viewing only their own audit records. This file defines proposed behavior, not test results.
