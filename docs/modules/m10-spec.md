# M10 specification - final integration, acceptance and handoff

**Status:** Implemented; independent acceptance review passed18/18 on21 October2026. The user approved the separate test shop, local HTTPS and free-plan Groq use. Results and limitations are recorded in the [acceptance ledger](../evidence/m10/acceptance-results.json); final user acceptance remains pending.  
**Prepared:** 19 October 2026.  
**Sources:** Assignment DOCX: mandatory requirements, definition of done, demo video and deliverables; [blueprint](../../blueprint.md#m10-final-integration-and-acceptance); [working rules](../../AGENTS.md); [decisions](../decisions.md); [operating guide](../operations.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Connect the modules we have built into one working application, then demonstrate the complete assignment with two people. M10 is the last mandatory module in the approved M0-M10 blueprint. There is no additional M11 or M12 to invent.

**WHY:** Individual checks proved separate parts using controlled substitutes. They have not yet proved that a real dashboard request reaches the real shop, returns through the gateway and creates the correct audit record.

**HOW:** Add a small backend entry point and an orchestrator, deploy the complete system using our existing Helm chart, and run real browser, MCP, database, network and recovery checks. The orchestrator connects existing code; it does not rewrite accounts, routing or chat.

Think of Docker Compose connecting containers: Helm supplies the Kubernetes installation recipe, Services provide stable internal addresses, and Ingress sends public requests to the correct Service. Our Python orchestrator has a different job: it connects the backend's Python objects inside one process.

The final result is one store, one dashboard and one gateway MCP URL. An admin configures upstream servers once. A member uses the gateway with their own key and never receives saved upstream credentials.

## 2. Remaining work and entry gates

Only M10 remains as a new mandatory module. Earlier verification gaps remain attached to their original modules; creating another module would hide them.

| Item | Currently recorded | Needed before final acceptance |
|---|---|---|
| M8 dashboard | Implemented; independent 12/12 PASS using controlled APIs and an isolated static deployment | User module acceptance and real backend/browser checks |
| M9 package | Implemented; independent 12/12 static package PASS | User module acceptance and real full-release deployment |
| M7 provider check C7-11 | Subsequently verified in M10 after current free-plan confirmation | [Real probe](../evidence/m10/provider-probe.json) plus separately integrated browser chat evidence |
| M0 deferred client checks | Historical progression allowed with exceptions | Real external-client protocol and natural-language evidence in M10 |
| M2/M3 real shop-to-MCP wiring | Deliberately deferred | All five Woo tools against the real shop through the gateway |
| M5/M6/M7 real composition | Deliberately deferred | PostgreSQL, Secret API, identity, registry, audit, discovery, router and chat work together |
| Production profile | Same chart statically checked | Final source/image/preflight checks and accurate VPS instructions; a live VPS is optional |

Read the earlier module reports before implementation; do not infer user acceptance from a test PASS. Specification/design work can proceed while these gates are open. Integration implementation starts only after prior acceptance/exception decisions and M10 design approval are explicitly recorded. A blocked provider check can permit reviewed non-provider work, but cannot become a final PASS.

Links: [M7 report](../evidence/m7/report.md), [M8 review](../evidence/m8/acceptance-review.md), [M9 review](../evidence/m9/acceptance-review.md), [workflow history](../workflow-log.md).

## 3. Scope and boundaries

Included:

- Real backend composition, startup/shutdown and readiness; one replica and one worker as already designed.
- Real persisted accounts, invitation redemption, login, individually revocable hashed keys, registry and attributed audit records.
- Same-origin React/API/chat and the public Streamable HTTP gateway endpoint.
- Custom Woo MCP connected to the persistent WooCommerce shop; local sample Inventory and actual hosted Microsoft Learn connected through the gateway.
- All mandatory two-user demo steps, persistence and network enforcement checks, reproducible installation and final evidence/handoff preparation.
- Small integration fixes to existing modules when a real contract mismatch is demonstrated, with focused regressions and a record of affected criteria.

Excluded unless separately approved: multi-store provisioning, gateway OAuth login, new per-tool permission policies, multi-replica scaling, paid provider fallback, VPS purchase/deployment, cert-manager, hosted-server provisioning, public GitHub publication and submitting the form. Existing WooCommerce OAuth 1.0a signing stays as approved; it is separate from optional gateway OAuth.

Recording/publishing a demo or uploading a private repository is a later explicit user action after core review. M10 prepares a script/checklist and safe artifacts first.

## 4. Request and credential paths

```text
Browser -> HTTPS Ingress -> React static files
Browser -> same-origin /api/v1 -> account/server/key/audit APIs
Browser -> same-origin /api/v1/chat -> current user's chat agent
                                      -> gateway router -> upstream MCP
External client -> HTTPS /mcp + user's gateway key
                -> gateway authentication -> same router -> upstream MCP

Woo MCP -> WooCommerce REST -> MariaDB + WordPress content disk
Inventory MCP -> checked-in sample inventory (not synchronized shop stock)
Gateway -> actual hosted Microsoft Learn MCP
Backend -> PostgreSQL; scoped Kubernetes Secret API; Groq provider
```

Chat calls the gateway's authenticated application boundary using the signed-in user's validated identity. It does not need a browser-held API key or a network round-trip to its own public URL. Both chat and external MCP calls must use the same routing, authorization and audit behavior. Neither may bypass that path to call an upstream directly.

Browser sessions use HttpOnly cookies and CSRF/Origin checks. External clients use a personal gateway API key, stored hashed by the backend. Upstream credentials and the provider key remain server-side in Secrets. These are distinct credentials with distinct purposes; a client key must never be forwarded upstream.

Member tool access retains the approved shared upstream authority. A member can perform operations allowed by that upstream credential, including writes where exposed. Role separation protects administration; it does not invent an unimplemented read-only member policy. Member-to-member key, audit and account boundaries still apply.

## 5. Functional requirements

### 5.1 Backend composition and ownership

`backend/main.py` starts the application; `backend/orchestrator.py` constructs existing dependencies and owns their lifetime. Compose the existing FastAPI account API, gateway ASGI application and chat adapter without duplicate routes, conflicting middleware, broken `/mcp` paths or omitted child lifespan startup.

Required startup order: validate configuration -> migration lock -> exclusive database owner -> construct services -> recover unfinished audit/credential operations -> reconcile built-ins -> start discovery -> serve ready traffic. Reuse existing migration/owner/recovery contracts. Never run competing bootstrap/migration owners or silently reset a password.

Readiness requires current database ownership, supported schema, completed mandatory local recovery and initialized services. Liveness means the process can respond. A remote upstream or provider outage must not make otherwise healthy gateway workloads restart continuously. Owner loss fences new dispatch; shutdown stops new work, bounds draining, closes upstream clients/tasks and releases ownership. Preserve honest outcomes for interrupted writes; never automatically replay them.

### 5.2 Initial accounts and upstream registration

Bootstrap an initial admin through the existing private operator workflow, then invite a member through the real dashboard. Do not ship default passwords, create a public bootstrap endpoint or turn failed bootstrap into a password reset.

WooCommerce is already registered on first login. Reconciliation uses a stable identity, is safe across restart, and preserves admin edits, disabled state and deliberate removal. The concrete design must specify how initial installation is distinguished from later missing/deleted records; absence alone must not cause endless recreation. Inventory and Microsoft Learn must be registered and enabled for final checks; choose the minimal documented bootstrap/admin procedure in design.

Upstream URL/static-credential management must use real registry validation, scoped immutable Secret storage, recovery and redacted responses. Member requests to admin APIs must fail server-side, including direct requests bypassing navigation.

### 5.3 Real tool and chat behavior

- Real calls through the gateway exercise all five Woo tools: list products, create product, list orders, get order and update order status. Use disposable records; update only a labelled test order and record before/after state.
- Fresh tool discovery aggregates all three enabled servers and keeps the documented collision scheme. Preserve existing independent collision/slow-server tests without adding a fourth production upstream just for a fixture.
- Real Microsoft Learn discovery and at least one successful discovered call must pass through the gateway. Direct historical M4 connectivity is insufficient.
- Chat creates the exact named/priced product, reports today's actual shop orders using Asia/Kolkata boundaries, and displays actual tool attempts. Audit timestamps remain UTC.
- A real external AI client connects as B using only gateway URL/key and answers the orders and cross-server prompts. MCP Inspector proves protocol operations but manual calls alone cannot prove natural-language orchestration. Retain the recorded choice of Codex for the natural-language demo and MCP Inspector for protocol connection/call evidence. Their live compatibility is deferred from M0; design specifies exact setup and trust checks. A replacement needs your review; do not install or charge for a client silently.
- The cross-server prompt is: “Find SKU DEMO-001 in our shop, tell me its price, and check its warehouse availability.” Prepare a real disposable Woo product with that SKU after checking for conflicts. Label Inventory as sample warehouse data. Both upstream calls and their attributed audit records must be observed.
- Keep existing chat bounds, cancellation, partial-result and uncertain-write semantics. No test harness, fake model or fake shop may serve the final acceptance flow.

### 5.4 Control, failure isolation and audit

Check key revocation on the next request through the already-open client connection. Revalidate each call, record an identifiable rejection, show no upstream execution and show another active key still works.

Disabling an upstream removes its tools from fresh chat/client lists and rejects its former tool name. Record client refresh/reconnect needs honestly. An unreachable server has a clear error/status while healthy servers continue working. Restore the original enabled state and replica count after controlled failure tests.

For every demo attempt, correlate user, request/audit identifiers, upstream/tool, timestamp, duration and outcome. Show denied/error/timeout/unknown outcomes without relabelling them successful. Unknown unauthenticated callers must not be assigned an invented user. Saved evidence must not contain raw keys, cookies, invitation tokens, provider prompts containing private data or raw Secret objects.

## 6. Deployment, data safety and reproducibility

Use the existing chart and full local profile; final production differences remain Helm values. Seven workloads run in Kubernetes: WordPress, MariaDB, Woo MCP, Inventory MCP, PostgreSQL, backend and dashboard. Microsoft Learn and Groq are external services, not locally hosted workloads.

All workloads retain probes, resource requests/limits and reviewed security settings. Store database, WordPress content and platform database use persistent claims. Woo MCP and databases remain internal; only the reviewed storefront/dashboard/gateway routes are public.

Before modifying the retained shop, inventory explicit context/namespace/release, Pod/PVC identities, image digests and data IDs. Take a verified private recovery point, compare rendered changes and preserve disks/credentials. Prefer a separate owned target for initial composition checks. Never delete the current cluster, uninstall the existing shop or remove PVCs as a retry mechanism. The concrete design must choose retained-release upgrade versus a separate target and explain data/image/ownership consequences before applying anything.

The stable dashboard hostname needs trusted HTTPS under the existing secure-cookie contract. Do not weaken cookies, disable certificate verification or silently change the machine trust store. Design must propose the certificate/hostname/Ingress plan and identify any user-run trust or hosts-file action. Local shop REST signing and production TLS/proxy settings retain their approved transports.

Validate actual NetworkPolicy enforcement: gateway can call Woo MCP; ordinary non-gateway test Pod cannot; unrelated services remain available. Check least-privilege Kubernetes API access and deny unneeded Secret namespaces. Structural YAML checks alone do not prove enforcement. Any diagnosis Pod is explicitly owned, has no unnecessary token/privileges, and is cleaned up.

Freeze images from reviewed source, identify actual running configuration/image digests and verify rendered config. No fixtures or check-image command may replace `python -m backend.main`. Build fails if runtime entry points are missing. On Windows use observed tag-based k3d import and verify deployed identity; a CLI exit code alone is insufficient.

Rehearse a clean installation from the packaged source with separately supplied private inputs. Do not depend on old `.tools` environments or historical fixture images for final runtime. Document unavoidable operator inputs and exact tool/dependency versions. Exercise backup restore into a separate isolated target; report data checks without copying dumps or credentials into evidence. Same-chart production lint/render/preflight and accurate deployment/upgrade/rollback instructions are required; a real VPS remains optional. Also exercise the approved production Woo HTTPS/OAuth path against a controlled local production-shaped target: real TLS verification, canonical host/SNI, Traefik mapping and installed WordPress proxy handling, with an observed read and disposable write. This proves that transport configuration without claiming a VPS deployment; if prerequisites are unavailable, mark the check blocked rather than production-ready.

## 7. Files, responsibilities and inputs/outputs

Paths below are proposed responsibilities; concrete design finalizes small helper names before implementation.

| Owner / files | Inputs -> outputs and responsibility |
|---|---|
| `backend/main.py` | Validated runtime configuration -> one web/MCP application and process entry point |
| `backend/orchestrator.py` | Real DB, Secret API, service factories -> ordered startup, ready dependencies, bounded teardown |
| Existing `backend/api.py`, identity, registry, audit, gateway and chat modules | Reused contracts; only demonstrated integration corrections with regressions |
| `tests/e2e/` | Integration, browser, real MCP and security scenarios -> assertions and safe correlation evidence |
| `scripts/m10/` | Explicit target/private inputs -> preflight, safe setup/check/recovery helpers and sanitized reports |
| `scripts/demo.ps1` | Reviewed target and prepared test data -> step-by-step demo assistance; no automatic recording/upload |
| `docs/demo-checklist.md` | Acceptance IDs -> beginner-friendly live walkthrough and video outline |
| Existing chart/build/preflight files | Final runtime images and operator values -> same-chart local install and production validation |
| `docs/evidence/m10/` | Observed commands/results -> acceptance report, redacted screenshots, timings, image/resource/data identities |
| README/operations/design/threat/optional notes and workflow log | Observed implementation -> corrected instructions, limits and traceable history |

No new framework, database, authentication scheme or deployment controller is proposed. Reuse Python/FastAPI, the MCP SDK, PostgreSQL, React/TypeScript, Docker, Helm and k3d. Exact versions remain pinned by existing module locks unless a demonstrated compatibility issue requires a reviewed change.

## 8. Acceptance checks and required evidence

These are planned checks, not results. A result is PASS, FAIL, BLOCKED or NOT RUN, with command, target, time, evidence path and limitation. No prefilled passing report.

| ID | Check and measurable pass condition | Evidence |
|---|---|---|
| C10-01 | Real composition starts and shuts down; concurrent owner refused; readiness fences owner/recovery failure; unreachable upstream does not block overall readiness | Lifecycle/negative tests, sanitized process/probe observations |
| C10-02 | First login shows built-in Woo; restart adds no duplicate and does not overwrite admin changes or recreate deliberately removed data | Registry IDs/state before/after; safe UI capture |
| C10-03 | Full local Helm release healthy, correct actual images, three Bound claims, probes/resources; stable URLs work | Resource inventory, runtime identities, HTTPS/browser observations |
| C10-04 / D1 | Browser storefront cart + COD checkout; same order visible in Woo admin | Order ID, safe storefront/admin captures |
| C10-05 / D2-D3 | A's real chat creates exact name/price; product publicly visible; manual order then today's answer includes that order | Product/order IDs, real tool activity, A's matching audit IDs and timezone bounds |
| C10-06 / D4 | B connects with only gateway URL/key; lists all three upstreams and answers today's orders using actual tools | Redacted client setup, live client answer/tool metadata and B's audits |
| C10-07 / D5 | One natural-language prompt uses Woo + Inventory data; actual Microsoft Learn call also succeeds through gateway | Two-server answer and correlated audits; Learn tool/result metadata |
| C10-08 / D6 | Revoke B's selected key; next request in existing connection denied with no upstream execution; second active key unaffected | Denial and control call audit/counters; no raw key |
| C10-09 / D7 | Disable selected upstream; absent from both refreshed catalogs; stale tool rejected; healthy upstream works; restore | Catalog/status transitions, audits and final state |
| C10-10 / D8 | Delete owned upstream Pod and observe failure isolation/Unreachable/recovery; if replacement too fast, controlled scale-to-zero and restore | Timed status/calls/events with actual outage method; restored replica count |
| C10-11 / D9 | Every identifiable demo tool attempt has correct user/server/tool/time/duration/outcome; member only sees allowed audit/key data | Safe request-to-audit correlation matrix, direct role/ownership negatives |
| C10-12 / D10 | Separate store/database and backend/PostgreSQL restarts preserve test order/product/content and accounts/keys/revocation/registry/audits | Before/after data IDs/checksums; PVC identities; recovered readiness |
| C10-13 | Actual gateway-only Woo access; non-gateway denied; scoped Secret API RBAC and no public upstream route | Allowed/denied connection and RBAC observations, resource inspection |
| C10-14 | Real gateway calls pass for all five Woo tools, including a controlled order-status update | Test order before/after, tool results and attributed audits |
| C10-15 | Real browser invitation/login, own key issuance, admin registry mutations and audit/chat use real APIs; CSRF/role/ownership negatives enforced | Browser checks and safe same-origin request metadata |
| C10-16 | Real provider loop observed after free-account confirmation; no fake provider, silent paid fallback or direct-upstream chat call | M7 C7-11 closure reference plus real integrated tool activity; rate-limit/failure limits reported |
| C10-17 | Source-only clean local installation runs with explicit private inputs; isolated backup restore checks agree; production profile validates using same chart and approved Woo HTTPS/OAuth transport passes a real read/write | Reproduction/restore reports, exact commands, local/prod diff, no false VPS claim |
| C10-18 | Mandatory source/docs/chart/evidence present, secret scan reviewed, optional work correctly labelled; demo plan covers DOCX topics | Private handoff checklist, independent acceptance review and remaining gaps |

Timing checks retain approved M6 deadlines and bounds; record observed list/call/outage durations and compare with the accepted contract. Do not promote historical blueprint proposals to newly approved limits or relax a failed limit silently. Controlled slow/duplicate-name tests remain supporting module evidence; actual upstream outage evidence is required here.

## 9. Delivery sequence and review gates

1. **Specification review:** You review this file. Resolve scope/questions below. No application edits or live mutation in this phase.
2. **Concrete design:** Extend this same file with application mounting/lifespan, factories, startup/recovery, built-in reconciliation, configuration, certificate/target/data-safety and test/client plans. Independent review, then your approval.
3. **Composition implementation:** Add the minimal entry point/orchestrator and focused lifecycle/contract tests. Review before deploying the combined system.
4. **Deployment verification:** Private input preflight, data protection, build/import, reviewed chart install/upgrade, runtime health/TLS/network/persistence checks. Collect actual observations.
5. **User-flow verification:** Real provider plus browser/external client flows, controls, faults and correlated audits. Restore every controlled fault and remove only owned temporary resources.
6. **Final acceptance and handoff preparation:** Independent audit against C10-01..18 and DOCX; present exact commands/results/gaps and updated guides. You review the working core before any recording/publication/submission or optional work.

Subagents may implement distinct responsibilities and independently review artifacts. Root owns shared chart/log changes and live operations so two agents do not compete for the release/database owner. A reviewer cannot approve on your behalf.

Exact runnable commands belong to concrete design and implementation runbooks once real entry points and target choices exist. Existing operating-guide commands remain planned until exercised; this specification does not claim they run successfully today.

## 10. Decisions for your review

- **Prior gates:** Accept the M8/M9 module reports for progression, and explicitly retain/close earlier exceptions. This spec does not count your request for a spec as that acceptance.
- **Provider:** Confirm the account used for the Groq probe is currently on the intended free plan before calls. No keys should be pasted into review/chat. If unavailable, report BLOCKED and discuss alternatives rather than spending or swapping silently.
- **External AI client:** Codex plus MCP Inspector are already selected. Confirm availability and explain installation, TLS trust and any provider dependency during design. Propose a replacement only if needed; Inspector alone is insufficient for the two natural-language prompts.
- **Deployment target and HTTPS:** Review the proposed retained-release upgrade or separate installation and trusted local HTTPS procedure in the design. Trust-store/hosts-file changes and data-impacting transitions require explicit informed approval.
- **Final handoff:** Keep repository private. Actual repository creation/upload, demo recording/upload and form submission require your later explicit instruction. No VPS or bonus work is needed to complete the mandatory core.

These are known decisions, not reasons to delay writing/reviewing this specification. More detailed implementation choices come in the design phase. Material new security, cost or data decisions return to you.

## 11. Definition of done and limits

M10 is ready for final user acceptance only when all eighteen criteria have observed passing evidence, earlier required gaps are closed, real D1-D10 flows are demonstrated, documentation matches the actual installed system, controlled faults are restored, retained data is protected and an independent reviewer finds no unresolved mandatory defect.

Any missing client, quota, certificate, external service or recovery proof is labelled explicitly. Unit tests, static renders and fixture screenshots cannot substitute for real end-to-end evidence. A local PASS does not imply a live VPS deployment, a submitted assignment or complete protection from malicious upstream/model behavior.

**Independent specification review verdict:** READY FOR USER REVIEW. The reviewer checked the DOCX, blueprint, module reports, operating contract and this draft; no blocking specification gap was found. The recorded Codex plus Inspector choice is retained. The subsequent user instruction "design and implement" approves progression and authorizes routine in-scope implementation after independent concrete-design review; specific live-operation decisions remain separate.

## 12. Concrete runtime composition design

### 12.1 WHAT, WHY, HOW and ownership

**WHAT:** `backend/main.py` runs one Uvicorn worker. `backend/orchestrator.py` connects our existing account, gateway and chat objects. **WHY:** the earlier modules intentionally stopped at factories and isolated check applications. **HOW:** construct the real dependencies once, recover their persisted state, then let browser APIs and MCP share those same objects. No check harness or substitute adapter enters the release application.

| File | Responsibility and verification |
|---|---|
| `backend/main.py` | Read exact release environment, construct the root ASGI application, start Uvicorn on port 8000 with access logging disabled; reject unsupported workers/model/configuration before startup |
| `backend/orchestrator.py` | Configuration validation, real dependency construction, lifespan, readiness, owner monitor and shutdown; lifecycle tests inject explicitly supplied test factories rather than production fallbacks |
| `backend/db/migrations/003_builtin_initialization.sql` | Durable one-time Woo registration marker, separate from the deletable server row; transaction/restart/deletion regression checks |
| Existing `backend/db/database.py` and `backend/api.py` | Accept schema version 3 and preserve ordered migrations/readiness compatibility; migration and older component regression checks |
| `tests/e2e/test_runtime.py` and focused PostgreSQL checks | Exact routes, lifespan ownership, config rejection, readiness fencing, startup failure cleanup, owner loss and one-time registration; explicitly distinguish simulated dependencies from real database evidence |

### 12.2 Configuration and startup sequence

Reuse chart inputs `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, `PGPASSWORD`, `URUMI_ORIGIN`, `URUMI_ALLOWED_HOSTS`, `URUMI_INTERNAL_URLS`, `URUMI_SECRET_NAMESPACE`, `URUMI_LISTEN_HOST`, `URUMI_WORKERS`, `GROQ_MODEL` and `GROQ_API_KEY`. Add explicit non-secret `URUMI_WOO_URL` to the backend ConfigMap, pointing at the same release's internal Woo MCP URL; do not infer the built-in from URL-list order. Require that URL to be in the exact internal URL allowlist. Preserve TLS checks for hosted upstreams. Reject worker counts other than one and model names other than the existing approved Groq client model. An absent provider key may leave chat unavailable without preventing account/gateway startup; no network provider call occurs during startup, and the final demo still requires a real configured provider.

Startup is owned by the root application's lifespan, in this order:

1. Validate configuration, then construct the database connection information without logging secrets.
2. Run existing advisory-lock migrations, then acquire the existing exclusive database owner lock. Refuse a second owner. No runtime bootstrap password or public bootstrap route is added.
3. Read the persisted installation UUID and construct `Identity`, `Members`, `ApiKeys`, `SecretStore`, `Registry` and `Audit`. Secret ownership labels use the installation UUID, not a new process UUID.
4. Recover unfinished audits as `unknown` and run registry credential recovery. If any durable credential operations remain unresolved, fail startup before serving ready traffic. Do not retry or replay uncertain tool writes. Canceled credential-name tombstones retain their existing cleanup semantics and do not alone block startup after a completed recovery pass.
5. Reconcile the Woo built-in once using the transaction described below. Inventory and Microsoft Learn are added explicitly through the real admin UI/API; no extra automatic seeding or hidden administration identity is introduced.
6. Construct `UpstreamClient`, `Discovery`, `Router`, `GroqClient` and `ChatAgent`. Both external MCP and chat receive the same Router. Construct the existing account API and mount chat on its inner FastAPI object.
7. Explicitly enter the existing gateway child's lifespan, which owns the MCP session manager and starts discovery. Start the database owner monitor. Only then mark the root initialized and accept normal traffic.

A remote upstream/provider failure is not a startup readiness dependency. Discovery can report an upstream `Unreachable` while the rest of the application remains ready. Local database ownership/schema/recovery are readiness dependencies.

### 12.3 Exact ASGI dispatch and lifespan

ASGI is Python's web request interface; it also carries process startup and shutdown messages. Mounting a child web app does not automatically run every child's startup logic, so this composition enters that lifecycle explicitly.

Use a small root Starlette application with routes in this order: `/health/live`, `/health/ready`, exact `/mcp`, exact `/api/v1/servers/{server_id}/tools`, then `Mount('/', account_api)` as the fallback. The two gateway routes call the existing whole `Guard` ASGI app without stripping a prefix or changing `scope['path']`; this preserves its exact `/mcp` authentication check and MCP endpoint. No `/mcp/mcp`, redirect or permissive catch-all MCP mount is added. GET/DELETE reach the same guard so its existing authentication/POST-only behavior remains authoritative. Tool previews continue using the gateway's cookie-authenticated preview handler.

`create_api(...)` returns `BodyLimit(FastAPI)`, so `mount_chat(account_api.app, ...)` attaches `/api/v1/chat` before mounting that wrapper. Browser requests retain the existing body limit, cookie/CSRF/Origin checks and error shapes; MCP retains its separate protocol body limit. A browser cookie cannot become an external MCP API key, and no gateway key is forwarded upstream. Parent health routes win over the inner API's historical health routes. Root readiness verifies initialization, current DB owner, supported schema, no pending credential operations and a live discovery task; failures return a fixed 503 response without dependency details. Liveness is a fixed responsive-process check.

The root lifespan enters `gateway.app.router.lifespan_context(gateway.app)` exactly once. That child already owns discovery start/close, MCP manager lifetime and router close; the orchestrator must not start or close them a second time. Route/lifespan tests assert this and exercise real protocol initialization through the mounted guard. Startup exception cleanup releases any resources already acquired, including the exclusive owner connection.

### 12.4 Durable Woo initialization and deliberate deletion

Migration 3 adds a small table `builtin_initializations(name text PRIMARY KEY, server_id uuid NOT NULL)` with no foreign key to `servers`. It records that an installation has completed the initial Woo setup even when the administrator later deletes the actual server. The marker contains no credential or mutable server configuration.

After recovery, with exclusive owner checked, one database transaction reads marker `woocommerce`. If present, reconciliation does nothing. If absent, it first looks for an existing server with immutable slug `woocommerce`: adopt that row's ID into the marker without changing name, URL, enabled state or credentials. Otherwise insert a new server with a generated ID, name `WooCommerce`, slug `woocommerce`, configured internal URL, enabled `true`, status `Unreachable`, reason `NOT_CHECKED` and auth type `none`; insert the marker in the same transaction. Validate the configured URL with the existing registry allowlist rules before insertion. This built-in needs no static upstream credential because Woo MCP already uses its own server-side shop credentials and cluster access is restricted to the gateway.

The transaction prevents a crash between server creation and marking setup complete. The marker's independent lifetime prevents startup from undoing a deliberate deletion. Subsequent admin edits and disable actions remain untouched. No per-request reconciliation or administrative impersonation is required. Restoring both platform database and credential namespace preserves this state. Explicitly recreating a removed server remains an admin action. Tests cover a new installation, adoption of pre-existing rows, repeated startup, changed fields, disabled state, deletion, rollback on interrupted transaction and migration from schema 2.

### 12.5 Ownership loss and bounded shutdown

The owner monitor follows the existing M5 rule: check ownership at a short fixed interval; ownership loss immediately makes readiness fail and existing service revalidation fences new dispatch. Do not reacquire in the same live process. Wait until the database is reachable, then request a process restart so recovery occurs under a fresh exclusive owner. The executable owns that restart behavior; tests inject a harmless restart callback. During a database outage liveness remains healthy, avoiding restart storms.

Uvicorn stops accepting new requests and gives existing requests a bounded graceful-shutdown interval that accommodates the approved 120-second chat deadline. Root marks itself unready at teardown. Before exiting the gateway child lifespan, give existing audit-finalizer tasks a bounded two-second settling window; do not replay remote writes. Exit the gateway child lifespan (discovery/tasks/router), cancel and await the owner monitor, then drain the actual tracked adapter futures, lock-worker futures, pending audit finalizers and chat blocking tasks for at most fifteen seconds. Executor shutdown with `wait=False` alone is not evidence that SQL has stopped. The implementation review also identified ordinary account API thread work: the API factory accepts an optional tracked blocking adapter, preserving its historical default for isolated callers. Production injects tracked API workers; startup, readiness and ownership monitoring use tracked lifecycle workers. Cancellation must not hide those workers from draining. Regression checks cover both a synchronous account handler and an asynchronous login handler that delegates to a thread. Release the database owner only after those tracked workers are finished, then close provider/SecretStore resources. If work cannot drain, terminate the process with a fixed nonzero exit through an injectable process-exit callback, without deliberately releasing ownership first; process termination closes its database connections and startup recovery records interrupted attempts as unknown. Tests must prove the undrained branch never calls ordinary `db.close()` or starts another owner. Use independent cleanup guards for partial startup and completed shutdown, so one harmless close failure cannot skip the remaining cleanup. Process termination can still interrupt a dispatched write; existing durable audit recovery records that uncertainty on next startup.

This design implements composition and its independent verification only. Live release selection, retained-data changes, machine certificate trust, hosts-file modification, external client setup and real provider calls remain subject to the separate concrete deployment decisions and existing explicit gates.


### 12.6 Verification, packaging and deployment gates

The routine composition design above received independent review with no blocking defect. The user's explicit design-and-implement request and 20 October resumption authorize implementing this existing architecture after that review. This records authorization, not passing runtime evidence or a reviewer approving on the user's behalf. New material deployment/security/cost choices below remain proposals.

Use existing pinned dependencies and a fresh ignored `.tools/m10/venv` for clean verification. Controlled route/lifecycle/configuration tests exercise exact MCP dispatch, child startup exactly once, API-only body limits, owner/recovery failures, one-time registration and bounded shutdown. A returning injected process-exit callback must still never release ownership after failed draining. Real PostgreSQL checks use a separate owned disposable database, never truncate historical M5 or retained shop data. Unit/contract checks are not the real deployment acceptance.

Keep Docker stages separate: `runtime` installs the pinned lock and copies backend/contracts; `checks` adds historical check scripts and its harness command; final `release` inherits runtime only and starts `backend.main`. Existing explicit `--target checks` callers stay compatible. Adjust package tests to exercise missing-entrypoint negatives in an empty temporary root. The package runner must invoke the build rejection in a staged temporary checkout, never accidentally build the current runtime. Compare historical M6 hashes as historical differences, not current image parity; preserve old evidence unchanged. Current image/source/runtime identity requires new observations.

A small M10 checker runs controlled tests and records real outputs. Its live inventory mode is read-only, requires explicit context/kubeconfig/namespace/release and records safe metadata only. Unimplemented live scenarios must not be advertised as working. `scripts/demo.ps1` prints the reviewed checklist; it does not mutate, record or upload automatically. Tests and deployment reports retain all eighteen acceptance statuses, distinguishing controlled checks from actual D1-D10 proof.

The user subsequently approved the separate `urumi-m10` release/application namespace, `urumi-m10-secrets` credential namespace, fresh PVCs, `shop-m10.urumi.test` and `dashboard-m10.urumi.test`. This target is installed. No retained `urumi` resources are upgraded or reused implicitly. Supply private operator inputs under ignored `.tools/operator/m10/`; observe actual API endpoint/Traefik/storage instead of guessing. Image preflight verifies built/imported identities before install; later actual Pod image identities provide separate runtime proof.

Use a supplied trusted certificate covering the hostname; if no such certificate exists, prepare and review the exact local CA/hostname/trust procedure before changes. Provider calls await current free-plan confirmation. Codex/Inspector compatibility and trust setup are checked during that concrete client phase. Initial admin bootstrap uses the existing private operator helper while the runtime owner is stopped, releases that owner before starting backend, and never resets a password automatically. Restore remains an isolated target with separately reviewed private inputs. No live action or passing result follows merely from writing this design.


## 13. Implementation progress - 20 October 2026

The real backend entry point/orchestrator, schema-3 Woo initialization, tracked worker shutdown, API/chat integration fixes and release/check tooling are implemented and independently source-reviewed. Fresh controlled regression results: **161 PASS, 6 SKIP**; the six opt-in database checks separately **6 PASS** against a new disposable PostgreSQL container. Package/store/guard checks passed, the backend release image built, and its no-network import/no-harness smoke passed. These results support source implementation, not complete M10 acceptance.

[Implementation report](../evidence/m10/report.md) is the historical controlled-build checkpoint. The [live report](../evidence/m10/live-report.md), [runbook](../evidence/m10/runbook.md), [independent source review](../evidence/m10/implementation-review.md) and [acceptance ledger](../evidence/m10/acceptance-results.json) now distinguish the subsequent real deployment checks and remaining gaps. The test target, local HTTPS and provider were approved and exercised. The original shop remains separate; final acceptance requires observed evidence for every criterion and user review.
