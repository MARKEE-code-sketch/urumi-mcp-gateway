# M8 specification - React team dashboard

**Status:** Specification and concrete design approved by the user's "implement" instruction. M8 implementation, 23 unit/component checks, 16 distinct host browser cases and 15 isolated cluster browser cases have passing evidence. Independent acceptance review PASS for all 12 criteria; user module acceptance remains pending.  
**Date:** 18 October 2026.  
**Sources:** Assignment DOCX; [blueprint M8](../../blueprint.md#m8-react-dashboard); [decisions](../decisions.md); [platform API](../../contracts/platform-api.md); [identity and audit](../../contracts/identity-and-audit.md); [M5 specification](m5-spec.md); [M6 specification](m6-spec.md); [M7 specification](m7-spec.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Build the screens where admins manage connected MCP servers and teammates, and everyone manages their own gateway keys, chats with tools, and views permitted activity records.

**WHY:** The assignment needs a usable React dashboard, not just Python API endpoints. People must be able to see server failures, copy a newly generated key once, and understand which tools a chat actually called.

**HOW:** React displays data returned by the Python backend. The browser proves login with its session cookie, sends a CSRF token when changing something, and never contacts upstream MCP servers or Groq. During M8, controlled API fixtures supply the responses; M10 replaces those fixtures with the real backend.

| Term | Simple meaning |
|---|---|
| React | The required library for building interactive screens. |
| TypeScript | JavaScript with checks for the shapes of data used by those screens. |
| Vite | A tool that runs local frontend development and builds browser files. |
| API fixture | A controlled test response that lets us check a screen without connecting real modules. |
| CSRF token | A session-bound value the backend checks on changing requests to protect browser login. |
| Static web server | A container serving built HTML, JavaScript and CSS; it contains no backend credentials. |

Example: an admin disables Inventory. The screen sends a PATCH request, waits for success, and refreshes the server information. It shows Disabled and an empty tool preview. M8 verifies this with fixtures; M10 proves that real gateway tool execution is blocked.

## 2. Scope and approval boundaries

React, TypeScript and Vite are confirmed in the blueprint. Screens and behavior below implement existing assignment/API requirements. Exact layout, navigation/routing library, test packages, static-server image, package versions, browser request deadlines and refresh intervals belong to the later design review. No new frontend framework, styling system or cloud service is selected here.

| M8 owns | Owned elsewhere / excluded |
|---|---|
| Login, invitation redemption, servers/tools, members/invitations, personal keys, audit and chat screens | Authentication, authorization, persistence and Secret operations: M5. |
| Same-origin browser API client and safe display of API responses | MCP discovery/routing/execution: M6; model/tool loop: M7. |
| Frontend build/container and dashboard-owned Helm resources | Final release values/routes/runbooks: M9; real backend wiring/bootstrap: M10. |
| Deterministic screen tests and real-browser fixture evidence | Proof of real shop writes, real provider quality or final two-user acceptance: M10. |

No signup, password reset, role editor, user-disable page, email delivery, persistent chat history, streaming chat, direct tool-execution console, metrics dashboard, multi-store UI, per-tool permissions, hosted-server deployment or gateway OAuth is added. Member users can use all enabled tools, including writes; hiding management buttons does not impose tool permissions.

M5 and M6 have implementation evidence and independent PASS reviews, with user module acceptance still pending in their reports. [M7 evidence](../evidence/m7/report.md) records an unrun real-provider check, blocked pending free-plan confirmation. Writing or testing fixture-backed M8 screens does not accept those modules or close that gap. Real integration remains behind their review gates.

## 3. Requests, roles and common screen behavior

The browser uses relative `/api/v1` URLs on the dashboard origin and its login cookie. It does not use a personal gateway key to authenticate dashboard requests. `/mcp` is the external client's endpoint, not the frontend data API.

- On protected-page entry or reload, obtain the current user and CSRF token from `GET /auth/me`. Do not restore a claimed identity from browser storage.
- Keep current user/CSRF and transient form/chat state in memory. Never put passwords, raw keys, invitation tokens, upstream credentials or chat content in localStorage, sessionStorage, application logs or analytics.
- Attach `X-CSRF-Token` to authenticated changes. Browser-generated Origin and cookies remain subject to backend enforcement. Login and redemption require allowed Origin but do not fabricate an authenticated CSRF token.
- Each data view has a visible loading state, empty state, safe failure message and explicit refresh/retry action. Show API request ID when supplied for troubleshooting, without raw exception dumps.
- Disable duplicate submissions while an operation is pending. Do not automatically replay POST/PATCH/DELETE or chat after a network failure. Explain when the outcome is unknown and refresh safe metadata where useful.
- A protected API 401 clears user-specific state and asks the person to log in again. A failed login stays on the login screen. A 403 explains denied access without claiming a successful change. Handle 404, 409, 422 and 503 using existing safe API semantics; handle chat overload/429 without an automatic resubmit.
- Logout calls the agreed endpoint and clears user-specific state. If the response is lost, do not claim server-side logout was confirmed. Never leave another person's keys, audit rows or chat visible after an account switch.
- Lists use the existing `page`, `per_page`, `has_more` contract, default 20 and maximum 50. Provide bounded page navigation, reset page on filter changes, and preserve server ordering. Do not invent a total count when the API supplies none.
- Ignore late responses from an obsolete page/filter/owner or a previous session. A slow request must not replace a newer view or reveal the previous user's data.

| Capability | Admin | Member |
|---|---|---|
| Read server status and discovered tool previews | Yes, including URL/auth-type/header-name metadata | Yes, with no URL/auth configuration |
| Add/edit/disable/remove registered servers | Yes | No |
| Invite members and view member list | Yes | No |
| Issue/list/revoke own gateway keys | Yes | Yes |
| Issue/list/revoke another user's gateway keys | Yes, targeting that owner explicitly | No |
| Use chat and enabled tools | Yes | Yes |
| Read audit records | All team records | Own records only |

Use the role returned by the backend to choose navigation and controls. Direct navigation to an admin screen must show a safe denied view for members. These UI rules improve usability; only M5/M6's server checks authorize an operation.

## 4. Page requirements

### 4.1 Login and invitation redemption

`Login.tsx` accepts email/password and calls `POST /auth/login`. On success use the returned user and CSRF token. Provide labelled inputs, password masking and safe invalid-login feedback. Do not log or retain the password after submission completes. There is no public signup or default password.

`Invite.tsx` reads `/invite#token=...`, captures the token in memory and removes it from the visible/history URL before making requests or loading other page content. No token in query strings, referrers, screenshots, console or third-party assets. A page reload after removal may require reopening the original invite link; explain that simply rather than persist the token.

Accept a new password, submit exactly `{token,password}` to `POST /invitations/redeem`, and guide the person to normal login after success. Do not auto-login or invent an invitation-inspection endpoint. The current backend requires 12-128 password characters and at most 512 UTF-8 bytes; frontend guidance must match it. Missing/malformed, expired and consumed links use safe failure messages. Backend checks remain authoritative; a browser timer does not establish token validity.

### 4.2 Registered servers and tool previews

`Servers.tsx` reads `GET /servers`, `GET /servers/{id}` and `GET /servers/{id}/tools`.

- Show name, slug, enabled state, Connected / Unreachable / Disabled, last checked time and safe status reason. Explain NOT_CHECKED without falsely claiming a prior successful connection. Missing timestamps stay unknown.
- Show gateway tool names, upstream names, descriptions and input schemas as safe text. Tool descriptions/schemas are untrusted content. Do not turn them into executable UI instructions or add a direct call button.
- Mark a retained Unreachable preview as stale; it is previously discovered information, not proof that the tool currently works. Never-discovered servers may have no tools. Disabled previews are empty and not stale.
- Refresh from the backend after successful management changes and offer status refresh. This screen reads stored/discovered status; it does not ping upstreams. The approved design will choose any bounded automatic polling and stop it when the view/session is inactive.
- First-login fixtures include WooCommerce already registered, alongside Inventory and Microsoft Learn. M8 does not create these registrations; M10 owns actual bootstrap and reconciliation.

Admin forms use existing create/PATCH/delete routes. Creation includes name, unique slug, URL, enabled state and optional none/bearer/header credential. Editing treats slug as immutable. Saved credential values are never fetched or prefilled: offer explicit keep current, replace, or clear actions, mapping to omitted `credential`, a replacement object, or `{type:"none"}` respectively. Display only returned auth type/header name. Mask newly entered values, clear them after submission/cancel, and do not echo them into validation errors.

The browser necessarily handles an admin's newly entered credential long enough to submit it to the backend; it must never receive an existing saved credential back. Backend URL/header validation and connection-time destination checks remain authoritative. Explain that disabling stops gateway access, while removing a registration does not delete the remote application. Confirm destructive removal and credential clearing; failed changes must not appear saved.

### 4.3 Members and invitations

`Members.tsx` is admin-only. Show the paginated member list with safe user fields. Create invitations using `{email,role:"member"}`; invitation duration is the existing 24-hour policy. There is no role-changing control.

Display the newly returned invitation link and expiry once in the current page state, with an explicit copy action and a warning to share privately. Do not persist or retrieve it later, render it as an automatically followed external link, or capture it in evidence. Email delivery is excluded. Duplicate-account/pending-invite conflicts must be understandable. Clearing or leaving the creation result discards the link; do not silently create another invitation after a lost response.

Allow an admin to open the selected member's key controls. Clearly show that selected owner's email/UUID so a key is not accidentally issued or revoked for the admin instead.

### 4.4 Gateway keys

`Keys.tsx` defaults to the signed-in user's owner UUID and uses `GET/POST /members/{user_id}/keys` and `DELETE /members/{user_id}/keys/{key_id}`. Admin-targeted ownership is explicit; members cannot select another owner.

Show label, non-secret prefix, created time and active/revoked state, including revoked entries returned by the API. Raw keys appear only after issuance, in a clearly marked once-only result with an explicit copy action. Explain that leaving or refreshing loses that value, and future list responses cannot retrieve it. Do not put the value into a URL, downloadable file, persistent store, fixture screenshot or copied diagnostics. Clipboard copy occurs only on user action; if unavailable, provide a selectable value without claiming copy succeeded.

Show the configured gateway `/mcp` URL and short instructions to supply that URL plus the newly issued key to an external client. Never use that key to call the dashboard or an upstream. Confirm revocation and refresh metadata after success. Explain that the next external request is blocked after revocation, while a separately valid browser login remains usable and already dispatched work may finish. M8 fixtures prove the display, not real MCP revocation.

### 4.5 Audit activity

`Audit.tsx` calls `GET /audit`. Show caller user/key/auth source where provided; server UUID, public/upstream tool name; started/finished timestamp; duration; outcome; safe error code/summary; request/audit correlation IDs. Nullable values stay visibly unknown, not zero or fabricated names. Removed users/servers must not make historical records disappear or display a guessed label.

Support existing server and outcome filters, plus admin-only user filter. Member visibility is enforced by the backend before filters; the UI must not fetch all records and hide other users locally. Outcomes include running, success, error, timeout, denied and unknown. Explain running as unfinished and timeout/unknown as possible remote effects, without a retry button. Timestamp display must identify its timezone; preserve access to exact UTC values for correlation. No arguments, result payloads, secrets or audit export feature is added.

### 4.6 Chat

`Chat.tsx` posts exactly `{message}` to `/chat`, with the signed-in session/CSRF protection. No browser-submitted user identity, tool output, gateway key or provider credential is accepted or added.

- Allow one pending message in this screen, disable duplicate send and show that work is pending. M7 returns one final JSON response; do not invent streamed progress or tool activity before that reply arrives.
- Match the implemented message limits: nonblank trimmed text, at most 4,000 characters and 12,288 UTF-8 bytes within the 16 KiB request-body bound. Backend validation is authoritative. UI/request timeout design must accommodate M7's bounded 120-second work period and cleanup; it must not silently retry after disconnect.
- Render the answer as plain text by default. Show terminal state completed / failed / limit_reached separately from each tool outcome. Completed does not mean all tools succeeded.
- List every returned actual attempt with public tool name, server when known, outcome, duration when known, audit ID when saved, and safe error code/summary when present. Do not invent an audit ID for a locally rejected request or label a proposed tool as executed.
- Preserve failed/denied/timed-out/unknown attempts and partial answers. Do not hide an earlier failure because a later call succeeded. Preserve M7's backend warnings about uncertain writes and incomplete today's-order pagination; do not offer an automatic replay.
- Chat is transient. Any messages kept on screen during this visit are not a saved conversation and are not sent back as additional history: each API request contains only its new message. Clear chat on logout/session change.
- Handle provider failure, session expiry, overload, input errors and lost connection safely. A lost response does not prove that no product/order change happened. The frontend never contacts Groq or an upstream MCP server.

## 5. Safe rendering and usable interactions

Use React's normal text escaping for user text, server/tool names/descriptions, model answers and safe API messages. Do not inject HTML, execute tool-provided code, fetch result links, or automatically render remote images/embeds. Markdown support is not required; adding a sanitizer/renderer would need a specific later design justification.

Use local assets with no third-party scripts/fonts/analytics. No secrets in Vite build-time variables, source maps, static bundles or web-server config. Static serving/proxy rules must not log credential-bearing bodies; fixture capture must sanitize request bodies as well as responses. Do not add a service worker/offline cache for authenticated data.

Forms need labels, keyboard operation, visible focus, readable contrast, clear required fields, and error messages associated with the relevant controls. Status/outcomes must have text, not color alone. Check a desktop viewport and a narrow mobile viewport; tables may scroll without hiding primary actions or breaking forms. Keep the layout small and task-focused, without a large component framework or decorative dashboard scope.

## 6. Proposed file and resource ownership

These names describe module boundaries for later design, not permission to implement now.

| File / location | Responsibility | Inputs -> outputs |
|---|---|---|
| `frontend/src/api.ts` | Typed, same-origin API calls; cookie/CSRF; safe errors and cancellation | UI intent -> existing API request/reply |
| `frontend/src/App.tsx` | Session lifecycle, navigation and role-aware page access | Current verified user -> permitted screens |
| `frontend/src/pages/Login.tsx`, `Invite.tsx` | Login and one-use redemption | Credentials/token -> safe login/redemption state |
| `frontend/src/pages/Servers.tsx` | Status, preview and admin management forms | Redacted registry/catalog replies -> safe server UI |
| `frontend/src/pages/Members.tsx`, `Keys.tsx` | Invitations and explicit own/admin-targeted key controls | User/key metadata and one-time responses -> private transient display |
| `frontend/src/pages/Audit.tsx`, `Chat.tsx` | Visible records and completed chat/tool activity | Safe API replies -> honest outcomes/correlation |
| `frontend/package.json`, lockfile, build config | Reproducible React/TypeScript/Vite build | Pinned dependencies/source -> browser assets |
| `frontend/Dockerfile`, static-server config | Serve built assets and health checks | Built assets -> non-secret HTTP responses |
| `frontend/tests/` | Component/API fixture and browser checks | Controlled roles/replies/failures -> deterministic assertions |
| `deploy/charts/urumi/templates/dashboard/` | Dashboard Deployment/Service and owned configuration | Shared chart values -> static workload |
| `scripts/m8/`, `tests/dashboard/` if needed | Isolated fixture/runtime/browser runner | Test scenarios -> sanitized observed results |
| `docs/evidence/m8/` | Report, runbook, screenshots and check outputs | Observed runs -> reviewable proof |

Avoid duplicating business logic from Python. UI form guidance may mirror existing input constraints, but role/ownership checks, credential policy and authoritative schema validation stay on the server. Shared release values/schema edits are coordinated narrowly with M9; final backend entry points are M10-owned.

## 7. Independent verification and evidence

Use controlled same-origin API fixtures for screen behavior. These fixtures must reproduce the actual contract, including HttpOnly cookie behavior where a browser test claims it, required CSRF headers, member-redacted responses, one-time outputs and exact error envelopes. Do not embed fixture secrets/roles into a production build or let the real app silently fall back to fixtures.

| ID | Acceptance requirement | Observable proof |
|---|---|---|
| C8-01 | Reproducible build and browser startup | Locked clean install, TypeScript/build results, built-app entry/deep-link reload. |
| C8-02 | Login/session/logout and expiry states | Real-browser login, protected-page reload, cookie/CSRF fixture exchanges, expiry and account-switch clearing. |
| C8-03 | Safe invite creation/redemption | Admin creates one-time link; fragment removed before requests; member redeems; invalid/expired/spent cases; no token in saved traces. |
| C8-04 | Admin/member boundaries | Both browser roles, direct admin-page navigation denied for member, exact permitted API requests; no UI claim that this proves backend authorization. |
| C8-05 | Status/tools and failures | Connected, Unreachable with stale preview, never-discovered empty, Disabled empty; pending/error states; changed filters/pages and obsolete-response tests. |
| C8-06 | Server CRUD and credential semantics | Create/edit/disable/remove fixtures; immutable slug; keep/replace/clear bodies; safe failure without false saved state; zero saved credentials in replies. |
| C8-07 | Key ownership, one-time display and revoke | Own/member-targeted key flows, copied-value handling, dismiss/reload absence, active/revoked metadata, no automatic issuance replay. |
| C8-08 | Audit visibility, filtering and honest fields | Member receives own records only; admin filters; running/success/error/timeout/denied/unknown and nullable/removed-owner cases. |
| C8-09 | Chat answer and actual tool activity | No-tool, product creation, today's orders and cross-server fixture replies; failed/partial/limit/unknown/provider-failure/429/expired-session/lost-response states. |
| C8-10 | Browser trust and disclosure boundaries | Injection strings remain text; network destinations limited to dashboard origin; no saved upstream/provider credentials or Secret refs returned, and no caller-identity overrides; newly entered admin credentials appear only in the intended submission, never logs/cache/storage. Inspect requests and responses. |
| C8-11 | Usability in an actual browser | Keyboard forms/navigation/focus, labelled errors/status, desktop and narrow viewport screenshots with credentials hidden. |
| C8-12 | Dashboard deployability without final wiring | Dashboard-only image and Helm lint/local+production renders; isolated static workload Ready with probes/resources, browser assets served, original shop/PVCs preserved. |

C8-12 uses a temporary opt-in namespace or equivalent guarded isolated release, not the existing shop release. A Pod is a running container instance; a Service gives it a stable internal address, like a named Docker network service. Probes let Kubernetes check that the static server is alive and ready; resource requests/limits reserve and cap its resources. The static workload needs no PVC and no credential Secret/API-token mount. Exact image/security/resource values and same-origin fixture serving arrangement belong to design. Any fixture workload also needs bounded resources/probes and must remain test-only. Final public Ingress routing and live backend connection remain M9/M10; a temporary guarded port-forward is sufficient for isolated static-browser evidence.

The future runner must record exact PowerShell commands, versions, exit codes, sanitized browser interactions/screenshots and observed runtime resources. Preserve existing Pods/PVCs and clean only explicitly owned temporary resources. Screenshot evidence must contain dummy/sanitized values, never raw issued keys or full invitation links. Machine-readable acceptance results distinguish PASS, FAIL and BLOCKED; a fixture PASS is labelled fixture evidence. Browser build/unit tests alone are not live UI or cluster proof.

## 8. Traceability and done criteria

| Source requirement | M8 responsibility | Checks / later real proof |
|---|---|---|
| Admin sees registered servers, first Woo server, tools/status | Server list/preview/status screen | C8-05; real registration/bootstrap/outage M10 |
| Admin adds/edits/disables/removes URL+static credential | Management forms, write-only credential input | C8-06/C8-10; real routing/Secret effect M10 |
| Admin invites/issues/revokes; member generates own key | Member/invite/key screens | C8-03/C8-04/C8-07; real validator/client rejection M10 |
| Audit log visible with attribution/timing/outcome | Audit screen and safe filters | C8-08; every real demo attempt M10 |
| LLM chat shows tools and acts as current user | Session-based request and honest returned activity | C8-02/C8-09; actual provider and shop evidence M7/M10 |
| React dashboard runs in Kubernetes, stable Ingress URLs | Build/container/dashboard templates | C8-01/C8-12; complete same-chart release M9/M10 |
| Saved upstream credentials never reach members/browser/client | Safe serialization usage, transient admin input, rendering/storage controls | C8-10; real traffic/log/source inspection M10 |

M8 is ready for module review only after all twelve criteria have observed results, evidence states fixture/runtime scope accurately, no production fixture fallback exists, and no outstanding critical defect is hidden. User acceptance is a separate gate. No end-to-end success, completed M7 provider check or live VPS deployment is implied.

## 9. Design review items after specification approval

1. Agree on a small navigation/layout and form/error flow, including confirmation and once-only result handling. Keep plain text answers unless a concrete need justifies richer rendering.
2. Select minimal locked frontend/test/static-server dependencies, development fixture setup and real-browser test tool; explain each choice before implementation.
3. Set request/response limits, cancellation/stale-response handling and bounded status refresh. Accommodate M7's existing chat duration without automatic replay.
4. Set dashboard container probes, resource/security settings and test-only namespace/fixture ownership; coordinate narrowly with the separate M9 release spec.
5. Review the concrete design inside this same file, then ask for implementation approval. Do not create a separate parallel-plan or design-spec document.

**Review verdict:** READY FOR USER REVIEW. There is no new architecture/security/cost decision silently approved here. The user can approve or revise these requirements before detailed design.

## 10. Concrete design for review

This section records the concrete choices independently reviewed and then approved by the user's "implement" instruction. M8 now implements these choices; final real-module integration remains M10.

### 10.1 WHAT, WHY, HOW and the visible layout

**WHAT:** One small React application, seven page components, one browser API client and one static container. **WHY:** These give the required team controls without duplicating backend rules or adding a second application framework. **HOW:** A verified browser session selects permitted screens; forms call the existing `/api/v1` endpoints; React displays their escaped text replies. M8 tests use a separately started fixture server, and M10 supplies real modules.

Use a white/off-white content area, dark text, one restrained blue action color, a compact left navigation on desktop, and wrapping top navigation below 720 px. Keep status words next to color indicators. The top bar identifies the signed-in email and role, with Logout. Page headings explain one task in a sentence; loading/error/empty feedback sits beside the affected content. No decorative charts, animation library, component framework or external fonts are needed.

| Browser path / file | Visible task and access |
|---|---|
| `/login` / `Login.tsx` | Email/password form; public. Protected pages redirect here after a failed session check. |
| `/invite` / `Invite.tsx` | Redeem the fragment token, then go to normal login; public. |
| `/servers` / `Servers.tsx` | Paginated status list with a selected server's details/tools below; all users. Admins additionally see create/edit/disable/remove forms. |
| `/members` / `Members.tsx` | Paginated teammates, member invitation form and once-only invitation result; admin only. |
| `/keys` / `Keys.tsx` | Own keys by default. An admin selects a teammate from Members and sees that owner's email/UUID above every key action. |
| `/audit` / `Audit.tsx` | Paginated activity with outcome/server filters and admin-only user filter; role visibility remains backend-enforced. |
| `/chat` / `Chat.tsx` | Message box, pending state, final answer, terminal state and all actual tool attempts; all users. |

Choose the browser History API with a fixed path switch rather than a router package: there are seven flat paths and no nested routing. `App.tsx` handles `popstate`, ordinary same-origin navigation and session gating; unknown paths show a small Not found view. `/` redirects to `/servers`. The static server returns `index.html` for known application paths, not for missing assets or `/api`/`/mcp`. Fragments are reserved for invitation capture, not navigation. No next-URL parameter or open redirect is added.

Use native labelled inputs/buttons, table captions/column headers and a small shared confirmation panel for destructive actions. It presents the exact server/key owner/action with Confirm and Cancel, restores focus on close, and never substitutes for authorization. Errors use an accessible live region and field associations. Successful navigation focuses the page heading. Dialog-like one-time disclosures contain a clearly labelled Copy button, selectable value and Dismiss; do not auto-copy.

### 10.2 Stack, exact versions and deliberate limits

Runtime dependencies are only `react=19.2.4` and `react-dom=19.2.4`. Build dependencies are `typescript=5.9.3`, `vite=7.3.1`, `@vitejs/plugin-react=5.1.4`, `@types/react=19.2.14`, `@types/react-dom=19.2.3` and `@types/node=24.10.1`. Test dependencies are `vitest=4.0.18`, `jsdom=27.4.0`, `@testing-library/react=16.3.2`, `@testing-library/dom=10.4.1`, `@testing-library/user-event=14.6.1` and `@playwright/test=1.58.2`. Pin direct versions without caret ranges and commit the generated package lock; use `npm ci` thereafter. These are chosen compatible versions, not claims to be the latest releases.

Read-only `npm.cmd view <package>@<version> name version engines peerDependencies --json --offline=false --cache .tools/m8/npm-cache --fetch-retries=0` verified these releases against the primary npm registry on 18 October 2026. Installed host Node `24.18.0` and npm `11.16.0` were observed; this Node meets the returned Vite/plugin requirement `^20.19.0 || >=22.12.0` and the jsdom/Vitest requirements. [Vite's own guide](https://vite.dev/guide/) explains its build/runtime separation and Node support. No installation or compatibility test has run yet. Use this host Node for implementation, and `node:24.18.0-alpine` as the proposed build stage; resolve and record its immutable image digest before the first build. A missing tag or incompatible lock is an explicit design correction, not a silent substitution.

Use plain CSS in `styles.css`, React state/effects and the native Fetch API; no state library, CSS framework, router, Markdown renderer, Groq SDK or browser MCP SDK. Vitest checks pure API/lifecycle/form behavior; Testing Library checks labelled interactions; Playwright runs a real Chromium browser. These separate short logic checks from proof of visible browser behavior.

The runtime image uses the [NGINX unprivileged image](https://github.com/nginx/docker-nginx-unprivileged), which already supports a non-root listener on 8080. Select a currently available stable Alpine tag and pin its exact manifest digest during the approved implementation before building; record both in the evidence. This bounded image-resolution step does not approve floating `latest`, a different server or a paid service. The runtime contains built files and a fixed static config only; Node and test fixtures remain outside it.

### 10.3 File ownership and data flow

| File | Concrete responsibility |
|---|---|
| `frontend/src/main.tsx` | Before mounting React or starting API effects, capture a valid `/invite#token=...` token in memory and synchronously remove the entire fragment using `history.replaceState`; then mount the app. |
| `frontend/src/App.tsx` | Fixed routes, verified session, role navigation, session epoch, page lifecycle and logout. |
| `frontend/src/api.ts`, `types.ts` | Existing route wrappers, bounded Fetch decoding, minimal runtime response-shape checks and typed public data. No internal Secret-reference type. |
| `frontend/src/components/Feedback.tsx`, `Pagination.tsx`, `Confirm.tsx`, `OneTimeValue.tsx` | Only repeated feedback/pagination/confirmation/disclosure behavior, not a generic component system. |
| `frontend/src/pages/*.tsx`, `styles.css` | The seven page tasks and small responsive style rules above. |
| `frontend/vite.config.ts`, `tsconfig*.json`, `package.json`, `package-lock.json` | Pinned build, strict TypeScript and local test scripts. Production source maps disabled. |
| `frontend/Dockerfile`, `nginx.conf`, `.dockerignore` | Multi-stage build; static serving, security/cache headers and health responses; no fixture or credentials copied. |
| `frontend/tests/*.test.tsx`, `playwright.config.ts`, `tests/browser/*.spec.ts` | Isolated logic/component and real Chromium tests, using explicit fixture endpoints only. |
| `scripts/m8/fixture_server.py`, `check-m8.py`, `verify_cluster.py` | Controlled same-origin test service, evidence runner and guarded runtime inspection. Fixtures do not mount real M5/M6/M7 or access providers. |
| `tests/dashboard/values-check.yaml`, test-only fixture chart resources | Only the owned `urumi-m8-check` namespace/release; test fixture proxy forwards asset GETs to the dashboard Service. |
| `deploy/charts/urumi/templates/dashboard/` | Dashboard Deployment, Service and fixed NGINX ConfigMap only. |
| `docs/evidence/m8/` | Exact command outputs, sanitized browser screenshots, machine-readable results and review/runbook. |

M9 owns shared values/schema and final Ingress routes: `/api/v1` and `/mcp` Prefix to backend port 8000, `/` Prefix to dashboard Service port 80, without rewrites. Coordinate `dashboard.enabled`, `dashboard.image.{repository,tag,pullPolicy}` and `dashboard.resources`; M8 supplies only its narrowly scoped template requirements. No backend entry point, M5/M6/M7 wiring or actual bootstrap is added in M8.

### 10.4 Browser request boundaries and session lifecycle

`api.ts` accepts only known relative `/api/v1/...` routes assembled by wrappers; UUID path segments and supported filter values are validated/encoded. Fetch uses `credentials:'same-origin'`, `cache:'no-store'`, `redirect:'error'`, JSON content type for bodies and the current CSRF header on authenticated changes. It never accepts an arbitrary destination, sets Authorization, fabricates Origin, or follows redirects. Login/redemption have no CSRF header until a session exists. An empty 204 is success without JSON parsing.

| Bound | Concrete value / behavior |
|---|---|
| Outgoing JSON | UTF-8 encoded body at most 16,384 bytes, checked after serialization, matching actual M5/M7 body caps. No truncation or split submissions. |
| Chat input | Trim, require nonblank, maximum 4,000 Unicode code points and 12,288 UTF-8 bytes; use code-point counting rather than JavaScript UTF-16 length for consistency with Python. |
| Response body | Stream and count at most 1 MiB raw decoded bytes before JSON parsing; reject excessive Content-Length when supplied, cancel reader on overflow. Enforce JSON content type, shallow route shape, list length at most 50 and bounded recursive schema display depth 32/node count 2,000. |
| Normal request deadline | 15 seconds total including reading response body; AbortController with explicit timeout classification. |
| Chat deadline | 130 seconds total, accommodating M7's 120-second work period plus up to two-second cancellation cleanup and delivery margin. No automatic retry. |
| Status refresh | Manual Refresh only. No periodic polling; this avoids hidden traffic and overlapping refresh while retaining a clear way to observe M6's stored status. |
| In-memory chat | Last 10 completed exchanges, plus at most one pending message; oldest exchange is discarded with an explanatory note. New API calls still contain exactly `{message}`, without history. |

The response cap is a browser resource boundary, not a promised backend maximum. A legitimate unusually large tool preview can exceed it; show an explicit bounded-response error and offer a smaller page size down to 1. Do not silently truncate schemas or label a partially decoded response complete. A chat reply that exceeds the boundary is a lost response with possible effects, not evidence that no tool ran.

Initial protected entry renders a session-check state and calls `/auth/me`; no user-specific page data is requested first. Keep user/CSRF and forms only in React memory. Every session replacement/logout/401 increments a session epoch, aborts outstanding reads, resets page keys/forms/disclosures/chat and clears owner selection. Each request also captures a per-view sequence and owner/filter/page tuple. Ignore a late result unless both the session epoch and the view sequence still match; abort alone is insufficient because an already completed response may still settle.

While a write or chat is pending, disable duplicate submission and warn before route navigation/logout because its remote result may already have taken effect. Choosing to leave discards private page state and aborts delivery locally; never label this remote rollback. Browser unload cannot guarantee cancellation. For an ambiguous write result, show "The response was lost. The change may have happened. Refresh the list before trying again." For chat, explain possible tool effects and link to Audit. A lost key/invitation issuance cannot recover its raw value; refresh metadata where possible and do not automatically issue again.

On logout, first clear private state and suspend page access, then submit with the captured current CSRF token; success confirms server logout. A lost logout response shows "Local data cleared; server logout could not be confirmed" and a specific retry-logout action, keeping only the minimum transient token needed for that action until page close. Do not automatically call `/auth/me` and reopen the previous user's data. Login changes the epoch before rendering the new account. Protected 401 clears state; login 401 is simply invalid-login feedback. Safe error handling preserves request IDs but never renders arbitrary HTML/raw upstream content or raw request bodies.

### 10.5 Forms, disclosure and truthful results

Use the actual current API fields from `backend/api.py`, `backend/identity/{auth,members,api_keys}.py`, `backend/registry/servers.py`, M6 preview API and `backend/chat/api.py`. No invite-inspection, role-change, status-ping or credential-read API is introduced.

- Creation/server edit: name at most 100 characters, slug `[a-z][a-z0-9-]{0,23}` only at creation, URL at most 2,048 ASCII characters. Credential value at most 4,096 characters with no CR/LF, custom header at most 100 characters. Backend still enforces destinations/header policy. The encoded 16 KiB body limit applies independently. Keep/replace/clear are separate radio choices in edit; keep omits `credential`, clear sends `{type:'none'}`, replace sends the entered object. Clear replacement/password inputs after completion or cancellation, including failed submissions; re-entry is intentional.
- Invitation: member role fixed, returned URL displayed once in memory and never rendered as a clickable external link. Capture `/invite` token only if it has a single bounded token parameter, remove fragment even when malformed, never persist it, and submit only `{token,password}`. Password guidance matches 12-128 characters and maximum 512 UTF-8 bytes. No auto-login.
- Keys: label at most 100 characters; own UUID by default, admin target explicit. Once-only key result disappears on dismissal/navigation/session change. The client endpoint is `new URL('/mcp',window.location.origin)`; no upstream URL enters client instructions. Copy is on explicit user action; catch Clipboard API failure and show selectable text without claiming success.
- Audit: preserve all six actual outcomes, exact UTC timestamp available alongside labelled Asia/Kolkata display, null fields visibly Unknown. Retain UUIDs for deleted entities rather than guessing names. Page/filter changes reset stale results and sequence. Never show tool arguments/results.
- Chat: plain text answer, separately labelled terminal state and attempts. Keep actual supplied call/audit/server IDs, null duration/identity as Unknown, safe errors and partial/uncertain warnings. No inferred streaming progress, hidden failures, auto-replay or proposed-tool execution claims.

Sensitive fixtures and evidence use dummy values. Test report hooks exclude password/credential/key/invite bodies, cookies, CSRF and raw responses containing one-time values. Screenshots happen only after one-time results are dismissed, or with those selectors masked. Disable automatic Playwright traces/videos/HAR/screenshots on failure for secret-bearing tests; save explicit sanitized screenshots and allowlisted request summaries (method/path/status plus redacted field names). Test-only control APIs are reachable only within the owned loopback/test namespace path and are absent from the production image/config.

### 10.6 Static workload and fixture isolation

Static NGINX listens on 8080; Service port 80 targets 8080. `/livez` and `/readyz` return fixed 200 text independently of the backend: frontend readiness checks asset-serving capability, not Groq/upstream health. Set Pod non-root UID/GID 101, no privilege escalation, drop all capabilities, RuntimeDefault seccomp, read-only root, no ServiceAccount token, no Secret mounts and no PVC. Use bounded memory-backed `/tmp` emptyDir (16 MiB) for PID/temp files. Requests 25m CPU/32 MiB; limits 250m/128 MiB. Both probes HTTP on 8080, period 10 seconds, timeout 2, failure threshold 3; readiness initial delay 2 seconds, liveness 5. Verify these values with the actual image; adjust only in response to observed evidence.

Set `Cache-Control:no-store` for HTML and same-origin authenticated fixture responses; content-hashed assets may be immutable cached. Add `X-Content-Type-Options:nosniff`, `Referrer-Policy:no-referrer`, and a CSP limited to local scripts/styles/connect/images with `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`. No inline executable scripts, third-party assets, service worker or source maps. `/api`, `/mcp` and missing assets return 404 in this standalone static server instead of HTML; final Ingress routes those API prefixes elsewhere.

For tests, `fixture_server.py` binds loopback `127.0.0.1:18080`, serves built assets from a configured local `frontend/dist`, and implements the exact small fake API with HttpOnly SameSite=Lax session cookies, allowed-Origin/CSRF checks, member-redacted responses and scripted delays/errors. No real API/provider/cluster credentials are used. Playwright points the unchanged production-built UI to that one origin. Explicit test scenario controls are server-side test helpers, not UI environment flags or fallback code.

The isolated Kubernetes check uses namespace/release `urumi-m8-check` with ownership label `urumi.dev/module=m8-check`. Deploy the same frozen dashboard image plus a separate fixture/proxy image: fixture `/api/v1` routes are fake, other safe asset GETs proxy only to the fixed dashboard Service. This preserves one browser origin while exercising actual static files in the cluster. The fixture uses the already locked Python backend image dependencies without mounting real adapters, no Kubernetes token/Secrets, non-root/read-only filesystem, probes and requests 25m/32 MiB, limits 250m/128 MiB; bounded `/tmp` volume. It exposes `/livez` and `/readyz`; readiness also checks the static Service. It is disabled/absent from normal chart values. Port-forward only the fixture Service to loopback 18080 for the browser; do not create public Ingress.

The runner refuses a conflicting namespace/release without exact ownership labels, records original shop Pod/PVC identities, and cleans only its own test namespace after evidence capture. It never upgrades the existing `urumi` release. M9's final origin is `https://dashboard.urumi.test` using operator-supplied trusted local TLS because actual M5 permits HTTP only for loopback; the independent M8 loopback fixture does not weaken that restriction. Installing local certificate trust later is a separate machine change, not part of this design approval.

### 10.7 Implementation sequence, commands and evidence

1. Build typed client/session/route shell and form primitives; verify byte/deadline/error/epoch logic with focused Vitest cases.
2. Implement the seven pages against explicit fake contracts, not real adapters; verify role/owner/credential bodies and honest outcome states.
3. Run Chromium against the built files/fixture service; inspect actual keyboard, narrow layout, requests/cookies, injection escaping and state clearance. Save sanitized evidence.
4. Freeze dashboard/fixture images, render local and production chart values, deploy only the owned test release, inspect probes/security/resources and repeat a small browser smoke against actual cluster-served assets. Preserve shop/disks, collect evidence, cleanup and independent module review. No M10 wiring.

Planned PowerShell commands from repository root (paths/scripts are to be implemented after approval):

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run test -- --run
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend exec -- playwright install chromium
npm.cmd --prefix frontend run test:browser
./.tools/m6/venv/Scripts/python.exe scripts/m8/check-m8.py --cluster --context k3d-urumi --cleanup
```

`test:browser` starts/stops the explicit loopback fixture with a health check; `check-m8.py` records exact Docker/Helm/kubectl commands, image digests, actual browser run and cleanup. No passing artifact is prefilled. Save build/test/version outputs, an allowlisted network summary, safe desktop/mobile screenshots, deployed-resource JSON and baseline/after identity comparison in `docs/evidence/m8/`. Independent reviewer separates fixture PASS, static-runtime PASS, pending user acceptance and pending M10 flows.

| Acceptance | Concrete planned cases / evidence |
|---|---|
| C8-01 | Clean `npm ci`, strict typecheck, production build; fresh protected load verifies `/auth/me` precedes user-data requests. |
| C8-02 | Admin/member direct navigation, expired-session 401, 403, owner switch, delayed old session/view reply; zero previous-user data after epoch change. |
| C8-03 | Valid/malformed/expired/consumed fragment invitations; URL fragment cleared before requests; password limits and lost redemption response. |
| C8-04 | Admin invite success/conflict/503; member denial; once-only link copy/dismiss; selected member identity shown. |
| C8-05 | Connected/stale Unreachable/never-checked/Disabled previews; manual refresh, page change, late response and safe schema boundary error. |
| C8-06 | Create/PATCH/delete/disable with exact bodies, keep/replace/clear, immutable slug, failure/unknown response, no saved credential replies. |
| C8-07 | Own/admin-target keys, one-time copy/failure/dismiss/reload, revoke and unknown issuance; no automatic replay. |
| C8-08 | All audit outcomes and nullable/deleted entities; server/outcome/user filters and actual member-only fixture response. |
| C8-09 | No-tool/create-product/today/cross-server/partial/limit/unknown replies, failed attempts, 429/provider failure/session expiry, 130-second timeout policy and lost-response warning. |
| C8-10 | Escaped hostile HTML/tool text, no remote requests/embeds, cookies inaccessible to JS, required CSRF, no caller overrides, no persistent secrets/chat or unsafe captures. |
| C8-11 | Real Chromium keyboard/focus/errors/contrast review, desktop 1440x900 and narrow 390x844, sanitized screenshots with primary actions accessible. |
| C8-12 | Helm lint/local+prod renders, frozen runtime image Ready with both probes/security/resources, actual assets/browser smoke, owned cleanup, shop/PVC identity unchanged. |

### 10.8 Choices and review gate

The main tradeoffs are intentionally modest: a seven-path switch instead of a router dependency; manual refresh instead of polling; plain text instead of Markdown; a 1 MiB client response boundary instead of unbounded parsing; bounded transient chat instead of saved conversations; and a separate test proxy instead of pretending fixtures prove real backend integration. These keep the application small while preserving visible uncertainty and security boundaries.

**Design verdict:** Approved by the user after independent design review. Approval of this section permits the scoped implementation and isolated fixture/runtime checks above, including exact package installation and immutable image resolution. It does not accept prior modules, run the pending M7 provider probe, install machine certificate trust, deploy a VPS or start M10. After M8 checks, report observed results and gaps for user module acceptance.


## 11. Implementation and evidence

The user approved the concrete design with "implement". The seven page components, same-origin typed API client, invitation-fragment handling, session/view generations, bounded transient state, static Dockerfile/NGINX and isolated fixture/chart resources are implemented.

[Implementation report](../evidence/m8/report.md) and [PowerShell runbook](../evidence/m8/runbook.md) record the observed tests and limits. The browser and static workload are independently tested against controlled fixtures. Real M5/M6/M7 wiring, actual store/provider behavior and final two-user acceptance are still M10. Module/user acceptance remains separate from implementation permission.

One design consistency correction coordinates M9's release contract: dashboard startup probe checks `/livez` every two seconds with threshold 30, readiness checks every five seconds, and liveness stays ten seconds. Other approved dashboard resources/security settings remain unchanged. The Pod has the shared `app.kubernetes.io/name=urumi` label so M9's NetworkPolicy selects it correctly.


Observed closure: clean locked install, strict TypeScript and production build passed; 23 unit/component checks passed; 16 distinct host Chromium cases passed (fourteen together and two focused follow-ups); the actual frozen Kubernetes workload passed its fifteen-case Chromium run with image/configuration identities and all three static asset hashes verified. Both test Pods were Ready with zero restarts. Owned cleanup and preservation of seven original resource identities passed. The sixteenth host-only preview check is not counted as a cluster run. [Report](../evidence/m8/report.md) separates these results, operational import issues and remaining M10/user review gates.
