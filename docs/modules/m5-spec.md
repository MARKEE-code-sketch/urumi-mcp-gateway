# M5 specification — accounts, keys, registry and activity storage

**Status:** Implemented and independently reviewed PASS on 17 October 2026: 12 specification groups, 41 real-PostgreSQL host tests and 11 live runtime checks. User module acceptance is pending; final application integration remains M10.
**Date:** Specification/design 16 October 2026; runtime verification completed 17 October 2026.  
**Sources:** Assignment DOCX, [blueprint M5](../../blueprint.md#m5-accounts-keys-registry-and-audit-storage), [decisions](../decisions.md), [platform API](../../contracts/platform-api.md), [identity and audit](../../contracts/identity-and-audit.md), and [tool agreement](../../contracts/mcp-tools.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Build the backend's memory and access checks: accounts, invitations, login sessions, personal gateway keys, upstream registrations and tool-activity records.

**WHY:** A tool gateway must know who is asking, what that person may manage, and what happened. Restarting the backend must not lose users, revoked keys or activity history.

**HOW:** Python/FastAPI handles agreed dashboard requests; PostgreSQL saves platform records. An upstream credential goes into a Kubernetes Secret, while the database saves only its reference. Identity checks create a trusted principal for later gateway/chat modules.

**Result you can inspect:** Two test users can log in, manage only permitted records, and see appropriately filtered activity. Their personal keys are shown once and remain revocable after restarts. These checks use a dedicated test database and Secret setup, independently of a real MCP server.

| New word | Meaning here |
|---|---|
| Session | A server-side login record identified by a browser cookie. |
| Principal | The verified user ID, role and authentication source passed between backend modules. |
| Hash | A one-way fingerprint used to verify a password/token without saving its original value. |
| Registry | Saved descriptions of upstream MCP servers and their credential references. |
| Transaction | Database changes committed together or rolled back together. |
| ServiceAccount / RBAC | A workload's Kubernetes identity / rules limiting its Kubernetes API actions. |
| PVC | A persistent disk claim, comparable to a Docker volume that outlives its container. |

## 2. Request and data paths

| Input | M5 does | Output / storage |
|---|---|---|
| Email/password login | Verify password, create hashed-token session | HttpOnly cookie; safe user and CSRF token. |
| Protected dashboard request | Check current session, role, ownership and browser protection | Allowed operation or safe API error. |
| Personal key presented to the later gateway | Verify full key, current owner and revocation | Trusted principal or rejection; no upstream request in M5. |
| Admin submits server/credential | Validate metadata, stage owned Secret, commit registry state | Redacted server summary; credential stays server-side. |
| Later gateway supplies an activity attempt/outcome | Persist/finalize one record; apply visibility when read | Durable activity records without arguments, results or secrets. |

M5 supplies callable adapters and an isolated API test application. M6 supplies discovery, protocol authentication responses and tool dispatch; M10 wires the real backend application. A browser cannot submit a principal to grant itself a role.

M5 owns the account/key, registry metadata and audit routes. Discovered-tool preview (`GET /servers/{id}/tools`) belongs to M6, and `/chat` belongs to M7; listing these in the shared API contract does not authorize implementing their business logic in M5.

Three credentials serve different doors: the **browser cookie** proves dashboard login; the **personal key** proves an external client's identity to the gateway; an **upstream Secret** lets the gateway authenticate to one upstream. None substitutes for another. The separate M2/M3 OAuth 1.0a signature still authenticates the shop REST connection.

## 3. Scope, existing decisions and boundaries

Confirmed stack: Python/FastAPI and PostgreSQL, deployed through the existing Helm chart. Password hashing uses an established library; exact library/version, database access/migration library and resource sizes are design-review items.

The M0 design approval recorded in [decisions](../decisions.md#m0-design-approval) confirms **24-hour invitations, fixed 8-hour sessions, members viewing own audit records and admins viewing all**. Older contract text labels these proposed; this spec follows the recorded approval without rewriting M0 contracts.

| Owns M5 | Owned elsewhere / excluded |
|---|---|
| Local accounts, member invitations, sessions and permission checks | React screens M8; optional gateway browser OAuth is excluded. |
| Personal gateway-key issuance, hashing, validation and revocation | MCP transport/session handling and per-dispatch enforcement M6. |
| Registry CRUD, safe serialization and restricted Secret adapter | Tool discovery, preview caches, status polling, routing and timeouts M6. |
| Audit persistence, safe querying and recovery operations | Starting/finalizing actual execution attempts M6; chat identity propagation M7. |
| PostgreSQL migrations, PVC, Secret RBAC and isolated verification | Registering real WooCommerce/Inventory/Learn and final wiring M10. |

No email delivery, password-reset workflow, role editor, account-disable UI, tool-specific permissions, multi-team tenancy, multi-store provisioning, extra replicas, or rate-limit feature is added. Admin/member are the two roles. Members may use all enabled tools, including writes; hiding upstream credentials does not reduce the authority of those tools.

## 4. Account and browser-login requirements

- Implement the exact `/api/v1` routes, request/reply shapes, pagination, statuses and error envelope in the platform contract. Dashboard routes accept login cookies; a gateway bearer key cannot substitute for a cookie. `/mcp` bearer handling belongs to M6.
- Bootstrap the first admin through an explicit operator command reading an existing Kubernetes Secret. No public bootstrap/signup route or source default password. Create only when no admin exists; rerunning never resets an existing account. Serialize concurrent bootstrap attempts so they cannot create competing first admins. Remove the bootstrap Secret after confirmed success; failed runs remain safely retryable.
- Normalize email consistently; enforce database uniqueness. The admin invites a member for one email; no invitation can grant admin. Existing accounts and active pending invitations conflict. Design must define how an expired invitation permits a fresh invitation without ambiguous token reuse.
- Invitation tokens are high-entropy random values stored only as hashes, expire after 24 hours and redeem once. Account creation and invitation consumption are atomic: simultaneous redemption yields exactly one account. The token is returned once in a fragment-based invite link, manually shared; redemption submits it in the body and then requires normal login.
- Passwords use established password hashing, never reversible storage or homemade hashing. Invite/session/key tokens use cryptographic randomness and suitable hash verification. Exact algorithm, input bounds and work factors are specified and checked during design.
- Login rotates its session token; fixed expiry is 8 hours. Logout revokes the server-side session and clears the cookie. Recheck current account/role, expiry and revocation on every protected request and expose revalidation for every later chat tool execution.
- Cookie: HttpOnly, SameSite=Lax, Secure for production HTTPS. Local HTTP is limited to documented loopback development and carries unencrypted credentials; do not expose this mode on a LAN/VPS. Validate allowed Origin on login/redemption and changing requests; authenticated changes also require a session-bound CSRF token. Exact host/origin/cookie configuration must be reviewed in design.
- Never log credential-bearing bodies, passwords, cookies, CSRF tokens or invitation links. One-time outputs use no-store caching. M8 must avoid third-party assets on redemption pages; M5 tests API disclosure and origin rules without claiming full browser-UI proof.

## 5. Personal gateway keys and role checks

| Operation | Admin | Member |
|---|---|---|
| Invite members; list members; change upstream registrations | Yes | No. |
| Issue/list/revoke own keys | Yes | Yes. |
| Issue/list/revoke another user's keys | Yes | No. |
| Read safe server information | Yes; extra safe configuration metadata | Yes; no URL/auth configuration. |
| Read activity | All team records | Own records only. |

The API checks permission and ownership directly, including when a client guesses another UUID or calls a hidden UI action. Follow contract 403/404 visibility semantics; missing/non-visible owners or keys return safe NOT_FOUND without revealing another user's existence. Never trust a path's user ID without checking it.

Generate high-entropy keys; return `raw_key` only on issuance with `Cache-Control: no-store`. Persist UUID, owner, label, non-secret prefix/lookup identifier, hash and timestamps; no plaintext retrieval endpoint. Multiple keys per owner are allowed. An admin-issued key belongs to its target user. Verify the entire presented key with safe comparison; a prefix alone proves nothing.

Revocation is persistent and idempotent for an existing owned key. The next request and final pre-dispatch check after commit must reject it. M5 proves the validator behavior, including concurrent revocation; M6/M10 prove an existing MCP session cannot bypass it. Already-dispatched remote work may finish. Revoking a personal key leaves a separately valid browser session and other active keys usable.

## 6. Upstream registrations and credential protection

Store UUID, name, unique immutable slug, URL, enabled flag, status/timestamps, safe status reason and optional owned Secret reference. Preserve M0 names, status vocabulary and internal registry adapters. New enabled registration starts Unreachable/NOT_CHECKED; disabled wins immediately. Unreachable is not equivalent to disabled. M5 exposes status storage but performs no network discovery.

Credential modes are **none**, static bearer, or named static header. Credential values are write-only. Creation defaults to none; PATCH omission retains the existing credential and explicit none clears it. Member summaries omit URL/auth configuration; admin summaries may show URL, auth type and header name. Neither response reveals Secret names/references or saved values. Reject CR/LF and contract-reserved header names; only bearer mode sets Authorization.

URL policy from M0: public HTTPS otherwise exact operator-allowlisted internal MCP Services may use HTTP. Our built-in WooCommerce MCP address is an explicit allowlisted exception, never an arbitrary internal URL. Reject embedded credentials, fragments, other schemes, loopback, metadata/link-local and non-allowlisted private destinations. Require connection-time resolution checks and no redirects in M6; registration string validation alone is not complete SSRF protection. Design specifies hostname/port/path matching and DNS-rebinding boundary before code.

The selected shop OAuth 1.0a credential belongs to M2/M3's shop REST connection. It is not a new gateway registry mode or gateway browser-login feature. Upstream credentials never become member gateway keys or model inputs.

### Database and Secret changes cannot be one transaction

PostgreSQL and Kubernetes commit independently. Use staged replacement Secrets and recoverable operations, rather than claiming atomicity across both:

1. Stage a newly owned Secret; commit its reference and metadata together in PostgreSQL; retire the old owned Secret only after commit. A failure preserves the previous usable configuration, or leaves a new registration inactive; return safe 503 rather than report partial success.
2. Removal disables routing first, then deletes its owned Secret and registry row. Failed cleanup leaves a disabled retryable record. Delete registration only; never delete the upstream application, shop credentials or database credentials.
3. Commit a durable database operation intent, including the predetermined owned Secret name, **before** any Kubernetes Secret creation. Recovery can then get that exact name and verify ownership even if the process stopped immediately after creation, without needing Secret list/watch permissions. Retain non-secret operation/ownership state until cleanup completes. Cleanup must target positively identified M5-owned objects; no namespace-wide delete. Design defines finite retries, timeout and explicit operator reconciliation.
4. Serialize conflicting edits/removal or detect a version conflict. A late update cannot resurrect a removed/disabled record or delete the replacement credential. Cover DB failure before/after Secret write, commit failure, retire failure, removal failure and restart recovery.

## 7. Durable activity storage

Use the exact identity-contract fields: audit/request UUIDs; verified user/key/source (nullable where unknown); server and upstream/public tool names; UTC start/finish; duration; running then success/error/timeout/denied/unknown; safe error code/summary. Do not save full arguments/results, passwords, tokens or unnecessary customer data.

- One durable running record before dispatch. M5 exposes persistence operations; M6 coordinates actual dispatch. Initial storage failure means AUDIT_UNAVAILABLE and no execution. An unavailable database cannot save that denial: disclose the gap and emit only a sanitized operational error/request ID.
- Identifiable denials use one running-to-denied transaction with no upstream call. Unknown keys have no trusted user/key ID; cryptographically verified revoked keys may retain attribution. Unknown tools may have no server/upstream name.
- Success needs observed upstream success and committed finalization. Failed finalization returns AUDIT_FINALIZATION_FAILED, with honest uncertainty; the durable running row remains until recovery can commit unknown. Interrupted attempts become unknown, never inferred success. Do not automatically retry uncertain writes.
- Recovery must distinguish abandoned attempts from active ones; design specifies a single-process lifecycle or equivalent ownership rule so recovery cannot finalize live work. Completion and recovery must not overwrite each other silently.
- Paginated activity reads apply member ownership before optional filters; admin-only user filters never widen member visibility. Preserve honest timeout/unknown values. Constraints and indexes support stable ordered pages and one final outcome per attempt.

## 8. Persistence and Kubernetes boundary

PostgreSQL persists users, invitations, sessions, key hashes, registry state, recovery metadata and audit records on a dedicated PVC. Versioned migrations support a clean database and an existing supported schema. Reapplying setup preserves records, passwords and revocations. Document backup/restore and migration/rollback limits: Helm rollback does not reverse database changes.

Use the existing chart with local/production values; passwords come from existing Secrets, not values or command history. PostgreSQL has an internal Service only. An isolated M5 backend harness and PostgreSQL both need readiness/liveness probes and CPU/memory requests/limits. Backend readiness checks required database/schema access; liveness must not create a restart storm during a database outage. Specify storage/network ownership and exact deployment resources during design, without changing M2/M3 workloads or PVCs.

The proposed concrete credential boundary is a dedicated `urumi-upstream-secrets` namespace, for user review with this spec/design. Give only the backend/test adapter identity a namespaced Role/RoleBinding with required Secret get/create/update/delete verbs, no cluster-admin, workload verbs, broad list/watch or access to platform/shop/provider namespaces. Create permission cannot be narrowed to future names using `resourceNames`; namespace isolation and adapter ownership checks are both necessary. Other workloads need no Kubernetes API token. A compromised backend can read the dynamic credentials allowed by this Role; Secrets are not automatically encrypted at rest. See [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) and [Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).

## 9. Proposed file/resource ownership

Names below reserve understandable responsibilities; exact contents and dependency pins follow design review in this same file.

| Files/resources | Responsibility |
|---|---|
| `backend/identity/auth.py`, `members.py`, `api_keys.py` | Password/session/key validation, invitations, roles and ownership. |
| `backend/registry/servers.py`, `secret_store.py` | Registry state, safe serialization and owned Secret operations. |
| `backend/audit/records.py` | Durable attempt/finalization/recovery and visibility. |
| `backend/db/models.py`, `migrations/` | PostgreSQL schema, constraints and migrations. |
| `scripts/m5/`, `tests/backend/` | Bootstrap, isolated fixture app/checks, failure/concurrency tests and bounded cleanup. |
| `deploy/charts/urumi/templates/platform-db/`, `access/` | Database/PVC, internal Service, Secret namespace and scoped RBAC. |
| `docs/evidence/m5/` | Exact commands, sanitized results, review and remaining gaps. |

Shared chart values/helpers/dependency locks require coordinated edits. M5 does not implement `main.py`/`orchestrator.py` final wiring or M6/M7/M8 business logic. Test credentials use a dedicated disposable namespace/database; cleanup preserves the existing shop and all retained application data.

Implement/check small parts within this one module: **M5A identity** (accounts, sessions, keys and ownership); **M5B registry** (metadata and Secrets); **M5C audit** (attempt storage and visibility); **M5D deployment** (real database durability and scoped RBAC). Test each part before assembling the isolated M5 harness. This is one spec and acceptance gate; real application integration remains M10.

## 10. Planned acceptance checks and evidence

The table defines the original planned acceptance criteria; observed PASS results are recorded in the linked evidence report and derived acceptance file. Use real PostgreSQL for transactions and persistence; mocks alone cannot prove concurrency or RBAC. A fake Secret adapter injects precise failures; live Kubernetes verifies actual scoped permissions.

| Check | Required observable result |
|---|---|
| M5-01 Bootstrap/migrations | Clean schema creates first admin; repeated/concurrent bootstrap and migration preserve existing accounts. No source default or public bootstrap route. |
| M5-02 Invitations | One member from concurrent redemption; expiry/spent/duplicate/invalid cases reject safely; hashed token only; repeat invitation after expiry follows reviewed rule. |
| M5-03 Login/session/browser protection | Correct/wrong login, fixed expiry, rotation/logout, cookie flags, Origin and CSRF cases, cookie/bearer separation; safe error shapes. |
| M5-04 Direct API permissions | Admin/member matrix; another user's UUID cannot expose/change keys or widen activity; caller-supplied role/principal cannot grant authority. |
| M5-05 Keys | Raw only at issuance; hash-only persisted; wrong/missing/revoked rejected; multiple keys/target owner, idempotent revoke and concurrent validator boundary. |
| M5-06 Registry | CRUD, duplicate/immutable slug, redacted admin/member summaries, enabled/status transitions, all static credential modes and PATCH retention/clear. |
| M5-07 Destination/header policy | Allowed built-in Service/public HTTPS; reject forbidden URLs/headers. Connection-time DNS/redirect proof explicitly deferred to M6. |
| M5-08 Secret failure/recovery | Inject each stage failure/interruption, including a crash immediately after Secret creation and before registry-reference commit; recover using the precommitted intent/name. No usable partial creation, lost prior credential, resurrected removal, leaked secret or unrelated-object cleanup; retry recovery converges. |
| M5-09 Effective RBAC | Actual adapter get/create/update/delete allowed only in dedicated namespace; list/watch, foreign namespaces and workload operations denied. Record `auth can-i` and real positive/negative Secret calls. |
| M5-10 Activity lifecycle | Success/error/timeout/denied/unknown fixtures; initial-write/finalization failure; one row/finalization; member filters; interrupted recovery does not mark active work unknown. No real tool dispatch claimed. |
| M5-11 Durable restart | Replace PostgreSQL and harness Pods separately: accounts, active/revoked sessions/keys, registry/credential references and audit persist; PVC UID unchanged; migrations repeat safely. |
| M5-12 Deployment/redaction/cleanup | Probes, resource limits, internal DB exposure, both Helm renders, secret-free source/replies/logs/dumps; temporary assets removed with retained data intact. |

Evidence includes test counts/results, sanitized schema/hash presence checks without dumping hashes/tokens, exact resource identities, failure-stage results and restored healthy state. Keep artificial activity fixtures clearly labeled. Revocation enforcement inside an existing MCP session, actual dispatch audit behavior, browser pages and the two-user demo belong to M6/M8/M10; real M5 logout/session-validator behavior is required here.

## 11. Original design questions and current acceptance gate

The original design questions below were resolved in section 12 before implementation: password library/work factor and input bounds; email normalization; cookie/origin hosts for loopback versus HTTPS; database/migration pins; exact RBAC/Secret naming and ownership; staged-operation recovery/concurrency rules; URL allowlist/resolution handoff; finite request/body/credential/list/retry limits; migration rollback and Pod resources. Subsequent implementation refinements are recorded in section 12.6.

**Done for M5:** Independently reviewed implementation passes all applicable checks with durable real-database and scoped live-Secret evidence; limitations are explicit and user accepts the module. A specification or successful unit suite alone is not a working gateway.

**Current gate:** Review the [implementation report](../evidence/m5/report.md), [12-group acceptance results](../evidence/m5/acceptance-results.json) and [independent review](../evidence/m5/acceptance-review.md) for user module acceptance. No next module or final wiring is authorized by this evidence.

**Independent review:** READY FOR USER REVIEW after making the pre-creation durable Secret-operation intent explicit. Approved identity/API contracts, failure handling, module boundaries and measurable checks have no blocking review findings. All acceptance checks remain planned; no M5 implementation or runtime proof is claimed.

## 12. Concrete design for approval

**Status:** Approved by the user with "let's proceed to the implementation". These details are the implementation baseline.

### 12.1 Simple implementation and request flow

Use FastAPI routes calling small identity, registry and audit modules. Each module uses parameterized SQL through Psycopg; there is no ORM, message broker or background job framework. A versioned SQL migration creates the tables, constraints and indexes in one transaction. A schema-version table and a PostgreSQL advisory lock serialize migrations. Refuse unsupported newer schema versions instead of modifying them. PostgreSQL is separate from the existing shop's MariaDB, like two Docker containers with different named volumes.

Proposed direct dependency baseline: Python 3.13.5, FastAPI 0.135.1, Psycopg binary 3.3.6, argon2-cffi 25.1.0, HTTPX 0.28.1, Uvicorn 0.40.0 and Pydantic 2.12.5. Keep compatible existing MCP/Starlette pins where dependency resolution permits; an incompatible resolution is a review issue, not permission to silently upgrade M3. Lock all resolved dependencies and run `pip check` in Windows and the Linux image. PostgreSQL uses the supported 17 major line with an exact current patch/digest recorded before deployment; image identity is verified rather than inventing a digest. Version sources: [FastAPI release metadata](https://pypi.org/project/fastapi/0.135.1/), [Psycopg release metadata](https://pypi.org/project/psycopg/3.3.6/), and [Argon2 API](https://argon2-cffi.readthedocs.io/en/stable/api.html).

`backend/db/database.py` owns connection/transaction boundaries; `models.py` defines safe row conversions; `migrations/001_initial.sql` owns schema. `backend/api.py` exports an API router/factory for the isolated harness and later M10 wiring. `scripts/m5/harness.py` owns only test application startup. No final `backend/main.py` or orchestrator is created here.

Use synchronous route handlers, a fresh bounded database connection per operation, and no cached authorization decisions. Database connect timeout is 3 seconds, statement timeout 5 seconds and lock timeout 2 seconds; sanitize failures to the agreed 503 envelope. A dedicated connection holds the single-process lifecycle lock described below. The harness runs one worker and one replica; multiple workers/replicas are explicitly unsupported in this module.

### 12.2 Identity and browser protection

| Detail | Concrete choice and reason |
|---|---|
| Password hashing | Argon2id with 64 MiB memory, 3 iterations, 4 lanes, 16-byte salt and 32-byte output, explicitly configured to the library's RFC low-memory profile. Passwords are 12–128 Unicode characters and at most 512 UTF-8 bytes; no trimming or silent normalization. A process-wide semaphore permits two password operations at once, bounding working memory; excess concurrent requests wait at most 2 seconds then receive safe 503. Wrong/unknown login uses a dummy hash verification and the same 401 message. |
| Email | Trim surrounding whitespace, restrict to a simple ASCII email address of at most 254 characters, lowercase the entire address and enforce unique normalized storage. No provider-specific dot/plus transformations or email-delivery claim. |
| Tokens | Generate 32 random bytes with `secrets`, encode base64url, persist SHA-256 hashes only, compare using `hmac.compare_digest`. These random tokens do not need a slow password hash. Session and invitation tokens are independently random. The session-bound CSRF value is HMAC-SHA256 keyed by the presented raw high-entropy session token with fixed purpose `urumi-csrf-v1`; encode its output as base64url. This distinct value is stable for that session and can be rederived from its cookie without storing either raw token. Persist only the SHA-256 hash of that derived CSRF value. Login and `/auth/me` return the derived value; verify changing requests with constant-time comparison of the submitted token hash against the saved CSRF hash. |
| Personal keys | `ugw_<UUID>_<random-token>`; UUID is a non-secret lookup identifier, the full string is hashed and verified. Display prefix contains only the marker and part of UUID. Current key/user rows are reread before returning a principal; revoked but cryptographically valid keys may carry trusted attribution in an internal authentication failure. |
| Login/session | Create a fresh token every successful login; revoke the currently presented valid session in the same transaction when rotating. Other devices' independent sessions remain valid. Fixed eight-hour expiry uses database UTC time. Logout revokes only the presented session and clears its cookie. No raw session token is stored in a principal. |
| Cookie | Name `urumi_session`, host-only, path `/`, HttpOnly, SameSite=Lax, eight-hour Max-Age, Secure by default. An explicit `local_http` setting permits only configured `http://localhost:<port>` or `http://127.0.0.1:<port>` origins and a loopback-bound harness listener. Production origins must be HTTPS. Later Ingress integration must choose an approved HTTPS origin or separately review a loopback-resolving development hostname. |
| Origin/CSRF | Exact configured Origin comparison; reject missing, `null`, malformed and unlisted Origin on login, redemption and every changing dashboard request. Authenticated changes also require `X-CSRF-Token` verified against the session-bound CSRF hash, distinct from the authentication-token hash. No wildcard CORS; no bearer fallback for dashboard routes. GET `/auth/me` only reads and rederives the stable CSRF value; it changes no state and requires no Origin header. Browser same-origin response protections prevent another origin reading that value. This also keeps multiple tabs working with the same session. |
| Input/output | Reject unknown body fields, including caller-supplied role/principal. JSON body limit 16 KiB applies while streaming, even without Content-Length; credential values max 4 KiB, labels/names max 100 characters, URLs max 2048, header names max 100. Use the agreed 422 envelope rather than FastAPI validation details echoing input. All authenticated and one-time replies use `Cache-Control: no-store`. Disable body/access logging in the harness. |

Invitation creation obtains an email-scoped transaction advisory lock, checks existing users and unexpired unused invitations, then inserts one hash-only invitation. Expired invitations remain historical but do not block a fresh token. Redemption locks the matched invitation row `FOR UPDATE`, verifies unused/unexpired, creates the member and marks consumed in the same transaction. Invalid token is 422, spent token 409 and expired token 422 with generic safe messages. Database uniqueness is the final concurrency boundary.

Bootstrap takes a fixed transaction advisory lock and creates the first admin only if no admin exists. Its operator helper reads email/password from an explicitly named existing Secret into memory, never command-line arguments; it deletes that bootstrap Secret only after successful creation or confirmed prior completion. This operator permission is separate from the backend's dynamic-Secret Role. Re-running cannot change a saved password.

Protected operations receive an internal immutable principal created by authentication. A private proof/handle lets the validator reread the original session/key and current owner immediately before later dispatch without giving M6 raw credentials. No exported API accepts a plain browser-supplied principal as authentication. Admin checks precede management work; resource ownership is applied in SQL before serialization. Member attempts to target another user's keys return 404; admin-only collection/management routes return 403.

### 12.3 Database schema and registry Secret operations

Tables: users, invitations, sessions, api_keys, servers, secret_operations and audit_records. Use UUID primary keys, timestamptz columns, role/outcome/status checks, foreign keys where retaining history permits, unique email/slug/token hashes and stable `(created_at,id)` or `(started_at,audit_id)` indexes. Audit attribution snapshots survive registry removal; server deletion must not cascade-delete audit history. Ordinary lists fetch `per_page + 1` after permission/filter clauses, newest first, max 50.

The Secret namespace is `urumi-upstream-secrets` by default and configurable for isolated acceptance. Secret names are predetermined `urumi-upstream-<operation-UUID>`; labels include module `m5`, installation owner ID and registry-server UUID. The installation owner ID is persisted in PostgreSQL at first migration. Every read/update/delete checks namespace, name format and exact ownership labels. Delete uses the observed Kubernetes UID precondition; never mutate/delete a foreign object even if its name collides. Credentials are stored only in that Secret, not in operation intents, exceptions or responses.

Use HTTPX against the in-cluster Kubernetes API with mounted ServiceAccount token and trusted CA, redirects disabled, 3-second phase timeouts and a 256 KiB response limit. The adapter exposes only owned-credential operations, never arbitrary namespace/name reads to M6. Its Role permits Secret get/create/update/delete in the dedicated namespace only; no list/watch, workloads, foreign namespaces or cluster administration. Namespace creation and RoleBinding are Helm/operator tasks. The backend uses no bootstrap-Secret access. A compromised backend can read dynamic credentials in its allowed namespace; the design does not claim protection against that compromise.

Every registry change and recovery pass holds a **session-level PostgreSQL advisory lock for that server UUID** on the same dedicated connection across its separate commits and Kubernetes requests. Use nonblocking acquisition, returning 409 if another edit/recovery owns the server; do not hold row transactions open during a network call. A pending unresolved operation blocks a new edit. Database loss aborts the request: no later network action or commit occurs on a newly reconnected lockless connection.

Replacement steps:

1. Validate metadata and proposed credential. Commit a durable operation row containing operation/server IDs, predetermined staged Secret name, old Secret reference, server/new-registration bookkeeping and `prepared` phase. Installation ownership is persisted separately; prepared operations always roll back and do not require a saved copy of desired metadata. New registrations also get a disabled, non-routable placeholder; existing registrations keep their previous configuration.
2. Create the immutable replacement credential Secret. No automatic retry of ambiguous creation: reconcile by exact name and ownership. A name collision with a foreign object fails closed.
3. In one database transaction, commit validated metadata and the new Secret reference, increment server version and set operation `committed`. New enabled servers become Unreachable/NOT_CHECKED, not Connected. A disable takes effect immediately on commit. Omitted credential keeps the old reference; explicit none commits a null reference without creating a Secret.
4. Retire the old owned Secret, then mark operation complete. If retirement fails, return safe 503 and retain a committed, usable new configuration plus durable cleanup intent; do not roll back to a possibly retired old Secret. This explicitly distinguishes precommit failure (old usable configuration retained) from postcommit cleanup failure (new usable configuration retained).

Recovery acquires the same server lock, loads the durable phase and inspects only known names. A `prepared` operation is **rolled back**, deleting an owned staged Secret if present and removing an inactive new placeholder; recovery never needs or reconstructs a plaintext credential. A `committed` operation only retires its old owned Secret. Crash immediately after create is covered because its name was committed first. Cleanup failure retains the intent and never touches an unrelated Secret. Each pass attempts an operation once; startup processes at most 100 pending operations, with unresolved cases surfaced as degraded readiness. An explicit operator reconciliation command can repeat passes; there is no infinite retry loop.

Removal under the same lock commits disabled status and a removal intent first. It deletes the owned credential and then registry row in a final transaction. Failure leaves a disabled record and recoverable intent. Missing Secret after an ambiguous delete is successful cleanup. Concurrent late updates cannot resurrect the record because they cannot bypass the lock/pending operation. Surface unresolved reconciliation through a sanitized 503 and readiness failure; do not invent a registry status-reason value outside the approved vocabulary or disclose a Secret name.

This refines section 6's failure wording: after a successful activation commit, cleanup failure preserves the **new** usable configuration. Rolling back at that point could restore a reference to an already deleted credential. This is a security/recovery detail included in the user design gate.

URL validation uses `urllib.parse` plus `ipaddress`: reject user info, fragments, query strings, malformed/nonstandard IP encodings, forbidden schemes and literal non-public addresses. An internal HTTP exception must match an exact configured canonical URL (scheme, normalized hostname, explicit/default port and path), with no suffix/wildcard matching. Initial built-in allowlist contains only the reviewed Woo and Inventory Service URLs. Public HTTPS names are syntactically accepted; M6 must resolve all addresses at connection time, reject non-public destinations and redirects, and apply the same explicit internal exception. M5 never claims DNS-based SSRF protection without that connector. Reserved headers include the contract list and all `mcp-` names; reject CR/LF in name/value, invalid HTTP-token names and whitespace-only values.

### 12.4 Audit lifecycle and recovery ownership

One backend process acquires a fixed PostgreSQL session advisory lock for the installation **before** serving requests or running recovery. A second process fails startup. Losing this connection makes readiness fail and dispatch validation fail closed; a supervisor restarts the process rather than trying to reacquire ownership while old work runs. Each process has a random run UUID; new audit rows store this internal owner UUID, never exposed in API output.

After exclusive startup ownership, mark only `running` records from previous run UUIDs `unknown` in one transaction with a fixed safe summary and null duration. Current-process rows are not recovered while work may be active. Registry recovery follows the same startup ownership and per-server locks. This intentionally supports one replica/worker; high availability is outside scope. M6 must stop dispatch if the ownership fence is lost and use this same lifecycle, rather than starting an independent owner.

`begin_attempt` commits running before returning its audit ID; database failure raises safe AUDIT_UNAVAILABLE. `finalize_attempt` conditionally updates only a running row owned by the current run; repeated or conflicting finalization raises a conflict, never overwrites an outcome. Known denials use one transaction for running-to-denied. Finalization failure raises AUDIT_FINALIZATION_FAILED and leaves the durable row running until a later exclusive startup can commit unknown. Callers provide only allowlisted safe error codes mapped to fixed summaries; raw exception/upstream strings and arguments/results are not accepted by the persistence API. UUID/name lengths and outcome constraints are checked. Tests use artificial attempts and never claim an upstream tool ran.

### 12.5 Kubernetes and independent checks

| Workload/resource | Proposed initial settings |
|---|---|
| PostgreSQL | One Deployment with Recreate strategy, internal ClusterIP, dedicated retained 2 GiB PVC, pre-created password Secret; requests 100m/128 MiB, limits 500m/512 MiB. `pg_isready` readiness/liveness with startup allowance; workload has no ServiceAccount token. PVC and DB credentials remain independent of the shop. |
| M5 harness | One replica/worker, Recreate strategy, port 8000 internal ClusterIP only; requests 100m/256 MiB, limits 1000m/512 MiB. Non-root, no privilege escalation, drop capabilities. `/health/live` checks process only; `/health/ready` checks schema, database, lifecycle ownership and unresolved recovery. Database loss does not fail liveness. |
| Network | PostgreSQL ingress only from labeled backend/test Pods in its namespace. Dedicated Secret API credential mounted only in backend harness. Real dashboard Ingress and final gateway connectivity wait for M9/M10. |
| Isolated acceptance | Namespace/release `urumi-m5-check`, Secret namespace `urumi-m5-upstream-secrets-check`, separate DB/PVC and generated throwaway credentials. Preserve all existing `urumi` objects. Both namespaces are explicit Helm values; no production records or credentials are imported. |

Implement and check M5A identity first, then M5B registry, M5C audit, and M5D deployment using the 12 acceptance groups above. PostgreSQL runs in the isolated Kubernetes namespace for transaction/concurrency tests, with a loopback port-forward for local test execution. Secret-stage failure tests use an owned in-memory fake to inject before/after stage failures; live tests additionally prove actual CRUD, denied list/foreign reads/workload operations, restart durability, probes and PVC identity. No SQLite substitution.

Tests explicitly include a simultaneous invitation race, bootstrap race, key revocation followed by a fresh validator read, concurrent conflicting registry operations, crashes at durable-intent/after-create/after-commit/after-delete boundaries, foreign-name collision and UID precondition protection, active versus abandoned audit recovery, failed initial/final storage and secret-free error envelopes. Evidence records exact commands and sanitized results; temporary objects are removed only after retained/restart checks. A database dump used for backup verification remains ignored private workspace data, with no hashes or credentials copied into reports.

Migrations are forward-only transactional SQL in M5. Operators back up with `pg_dump` before an upgrade and restore into a separate database to verify it; never promise Helm rollback reverses schema. Destructive schema changes require a separate reviewed migration and backup. Actual local runtime evidence and resource settings are now recorded in the M5 evidence report; live VPS verification remains outside this module.

**Concrete design independent review:** Reviewed before implementation; the user subsequently approved the concrete designs. Runtime acceptance remains a separate gate.

### 12.6 Implementation refinements found during review

- The resolved database is PostgreSQL **17.11**, pinned to observed image digest `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`. The Python image is pinned to the observed 3.13.5 digest. Dependency resolution preserved Starlette 0.52.1; the complete isolated M5 lock is `backend/requirements.lock.txt`.
- Forward migration 002 adds a non-secret canceled-name table. A timed-out Kubernetes creation can complete after an absent GET; deleting its only known name would make later safe cleanup impossible. Prepared-operation rollback retains a durable name/server-ID tombstone indefinitely. Bounded recovery rotates attempted names by last-check time, including individual failures, and rechecks ownership before deletion. An active-operation guard prevents the same process recovering its own in-flight mutation after its database connection loses the lock. This is recovery bookkeeping, not atomic database/Kubernetes commits.
- Replacement Secrets set Kubernetes `immutable: true`. The restricted update operation changes only safe owned metadata; credential changes always use staged replacement.
- Async JSON reading is followed by thread-pool execution of blocking authentication/database/Secret work. A blocked Secret request leaves the independent process liveness endpoint responsive.
- The harness owner monitor stays alive and fenced while PostgreSQL is unavailable. After a fresh database connection succeeds, it exits with code 75; Kubernetes restarts the process for exclusive startup recovery. The old process never reacquires its lost lifecycle lock.
- The isolated cluster harness uses HTTPS-origin/Secure-cookie configuration. Its HTTP Service is internal, and acceptance uses loopback port forwarding with explicit in-memory cookies. This proves backend API behavior, not browser HTTPS/TLS. Local insecure mode still refuses a non-loopback listener.

**Observed verification:** 41 tests passed against actual isolated PostgreSQL, including SQL lock/trigger failures and concurrency. Eleven live runtime groups passed, including actual Secret RBAC, database/harness replacement, backup restore and cleanup. Independent source/evidence review marked all 12 specification groups PASS. See the [report](../evidence/m5/report.md), [host output](../evidence/m5/host-tests.txt), [raw runtime result](../evidence/m5/cluster-results.json) and [derived acceptance result](../evidence/m5/acceptance-results.json). Both historical checker failures remain preserved. User acceptance and the later integration gates are separate.
