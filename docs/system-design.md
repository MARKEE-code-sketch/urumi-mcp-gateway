# System design and tradeoffs

The mandatory system has one store. [Blueprint](../blueprint.md) defines module ownership and [M9 specification](modules/m9-spec.md) defines the release contract. A Docker image becomes a running Pod; a Deployment maintains that Pod; a Service gives it a stable internal address; Ingress is the shared reverse-proxy entrance. Helm fills these resource recipes from local or production values. A render produces YAML, not a running system.

| Owner | Component | Responsibility |
|---|---|---|
| M2 | WordPress/WooCommerce and MariaDB | Checkout, products/orders; retained content and database PVCs. |
| M3 | Self-written Woo MCP | Validates tool input and translates it to signed Woo REST requests. Internal TCP8000 only. |
| M4 | Inventory MCP / hosted Microsoft Learn choice | Reproducible local inventory tools / external HTTPS MCP dependency. |
| M5 | PostgreSQL, identity, registry, Secret access, audits | Roles, hashed/revocable personal keys, team server registry, credential references and durable attribution. |
| M6 | MCP gateway/discovery/router | Catalog collision aliases, current authorization, safe connection boundaries, one dispatch and audit lifecycle. |
| M7 | Chat API and bounded provider loop | Uses the current session user and the same gateway invocation boundary. |
| M8 | Static React dashboard | Same-origin API browser client; no upstream/provider credentials. |
| M9 | Helm, build/preflight and guides | Package contract and safe operator instructions. |
| M10 | Backend main/orchestrator and final acceptance | Compose real services and prove complete two-user behavior. |

Browser requests go to HTTPS dashboard Ingress: `/` serves static frontend, `/api/v1` reaches backend and `/mcp` reaches the same backend. Paths are preserved. Backend health endpoints stay internal. Session cookies identify dashboard users; mutation requests also need the existing CSRF/Origin protections. Personal API keys authenticate external MCP clients, are hashed at rest and are individually revocable. Neither credential is forwarded to an upstream MCP server.

The server registry is shared by the installation and administered by team admins; members see its redacted shared entries. Registry ownership means installation/current SQL owner, not a separate registry per person. The gateway lists enabled installation-owned servers, creates collision-safe tool aliases, and verifies current user/server/version immediately before dispatch. Unreachable peers do not remove healthy peers. Upstream requests use bounded deadlines, response/schema sizes, checked DNS and numeric dialing; tool calls are not retried because writes may already have occurred. An audit attempt is durably started before dispatch and finalized once. If the result or finalization is uncertain, tell the user instead of claiming that a write failed or repeating it.

Chat sends only bounded safe tool descriptions and results to Groq. The model chooses a tool; backend validation and the gateway decide whether it may execute. Each activity has the same user/server attribution as an external call. Today's orders use one captured Asia/Kolkata day window and consistent pagination; partial results are explicitly marked. M7 fake-provider tests passed; its real-provider probe remains pending confirmation. Prompt text and tool descriptions are untrusted data.

Woo MCP alone holds store consumer credentials. Locally it signs the public HTTP origin while reaching WordPress's internal Service. Production uses real HTTPS to the public shop hostname resolved to Traefik's Service IP; TLS Host/SNI/signature all agree. Traefik forwards to WordPress HTTP80, and only its exact Pod selector may make that production hop. Verify trusted-proxy handling in the retained WordPress configuration before deployment; image defaults cannot prove a persistent file's state. No Basic-auth switch, forged connector proxy headers or TLS bypass is used.

The backend has one replica, one worker and Recreate updates because the current database owner model is exclusive. Startup must migrate under transactional locking, acquire ownership, construct identity/registry/audits, recover operations, reconcile built-in servers, start discovery and only then serve HTTP. Readiness depends on database/current ownership and completed startup, not every upstream's availability. Ownership loss fences dispatch. M10 implements this composition with explicit child MCP lifespan and API-only body limits. Schema 3 adds a durable one-time Woo initialization marker that survives admin deletion; startup preserves existing edits. Controlled checks and real PostgreSQL migration checks are separate from pending live deployment evidence. The release image excludes check harnesses.

Three retained PVCs store MariaDB data, WordPress content and PostgreSQL data. They are not backups. The dedicated dynamic-Secret namespace is also retained; references/ownership in PostgreSQL must remain consistent with those Secrets during recovery. Namespace-scoped backend RBAC allows only get/create/update/delete Secrets there, with no list/watch or cluster-wide role. [Operations](operations.md) explains coordinated backup, restore and schema-aware rollback.

| Environment difference | Local example | Production example / provisioning source |
|---|---|---|
| Runtime | Existing k3d on Docker Desktop | Operator-provisioned single k3s VPS; actual deployment unverified. |
| Origins | HTTP shop, trusted HTTPS dashboard `.urumi.test` | Real HTTPS DNS names; replace `.example.com`. |
| Certificates | Operator local trusted certificate | Operator public certificate Secrets; cert-manager optional. |
| Images | Reviewed local module tags; real backend source now supplied, live runtime verification pending | Private repositories and immutable digests/provenance; operator supplies. |
| Woo transport | Internal WordPress HTTP80 | Public hostname over TLS to verified Traefik ServiceIP/target8443. |
| API egress | No shared machine CIDR | Operator-verified API endpoint host CIDRs/port; preflight rejects missing inputs. |
| Storage | local-path | Verified actual StorageClass/capacity; local-path example is not replicated. |
| Secrets | Already provisioned private inputs | Operator static/provider/TLS/pull Secrets and dedicated dynamic namespace. |
| Resources/owners | One backend owner, bounded module starting envelopes | Same starting envelopes; no throughput/HA claim. |

No environment requires editing source/templates. Both profiles render seven workloads. Deploy preflight rejects placeholders, missing final entry points/digests/provenance, missing verified infrastructure and Secret metadata. Successful metadata checks do not prove network enforcement, credential validity, backup recoverability or application behavior. Those remain M10 evidence.
