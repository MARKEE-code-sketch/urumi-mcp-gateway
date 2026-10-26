# M4 — Inventory and external MCP compatibility

**Status:** Specification scope and implementation requested by the user on 16 October. Concrete design in section 11 independently reviewed READY FOR USER REVIEW; awaiting that design gate before coding.
**Date:** 16 October 2026.  
**Sources:** Assignment DOCX; [blueprint M4](../../blueprint.md#m4-inventory-and-external-server-compatibility); [decisions](../decisions.md); [M0 tool contract](../../contracts/mcp-tools.md) and [exact schemas](../../contracts/mcp-tools.schema.json).

## 1. WHAT, WHY, HOW

**WHAT:** Build one small sample Inventory MCP server and independently check the real hosted Microsoft Learn MCP server.

**WHY:** The assignment needs at least three upstream tool servers. M3 supplies WooCommerce; Inventory and Microsoft Learn supply the other two. Inventory makes our warehouse demonstration predictable; Microsoft Learn checks real external connectivity.

**HOW:** Our Inventory server reads a checked-in JSON fixture and answers `lookup_sku`. A separate test client discovers and calls Microsoft Learn over Streamable HTTP. M10 later registers both with the real gateway.

**What you will see:** A known SKU returns sample warehouse quantities; an unknown SKU returns a successful “not found” result. Separately, a real Microsoft Learn call returns documentation from its actual remote service.

## 2. Terms and request paths

| Term | Simple meaning |
|---|---|
| Upstream | A tool server that the gateway calls. |
| Fixture | Fixed sample data or a controlled test service. It is not live business data. |
| Schema | The checklist describing accepted arguments and returned fields. |
| Streamable HTTP | MCP messages carried over a web connection; SDKs manage the protocol. |
| ClusterIP Service | An internal address for a Kubernetes workload, similar to a service name on a private Docker network. |
| NetworkPolicy | Rules controlling which Pods can connect; the cluster must actually enforce them. |

Final paths, connected only in M10:

~~~text
Chat / external MCP client -> gateway -> Inventory -> sample JSON
                                    -> Microsoft Learn over HTTPS
~~~

During M4, an isolated MCP test client temporarily replaces the gateway. It is a testing stand-in, not an implementation of M6 authentication or routing. Microsoft Learn is a hosted dependency; we deploy no Microsoft Learn Pod.

## 3. Scope and boundaries

| Responsibility | Owner / boundary |
|---|---|
| Sample Inventory server, data, container and Helm resources | M4; independently testable without shop, platform database, AI model or gateway. |
| Actual hosted discovery and one useful read-only tool call | M4; record genuine schemas, protocol and returned result. |
| Controlled bearer/custom-header and duplicate-name test servers | M4 fixtures for later M6 checks; not extra production upstreams. |
| Team users, API keys, stored server records and audits | M5; M4 does not implement them. |
| Registry-driven discovery, collision aliases, dispatch, timeouts and upstream credential injection | M6; M4 supplies test fixtures, not gateway logic. |
| Three-server gateway registration and cross-server user prompt | M10; no early connection to the real M2 shop or gateway. |

Excluded: stock synchronization, inventory writes, reservations, shipping purchases, a Shipping MCP service, provider-specific gateway branches, paid services and hosting Microsoft Learn.

The [M2 report](../evidence/m2/report.md) and [M3 report](../evidence/m3/report.md) record completed independent checks. On 16 October the user accepted progression into M4/M5 specifications; this does not imply full-system acceptance. This spec does not change their source or saved shop data.

## 4. Inventory contract

The approved M0 JSON schema remains authoritative. Do not alter it to simplify implementation.

| Item | Required behavior |
|---|---|
| Tool | Exactly `lookup_sku`; descriptions explicitly say **SAMPLE**, not current WooCommerce stock. |
| Input | Object containing only required `sku`: string, 1–100 characters, not whitespace-only. Reject extra arguments and non-string values. Trim surrounding whitespace; match the normalized SKU exactly, retaining case. |
| Success | Object containing only `sku`, boolean `found`, and `warehouses`. Each warehouse contains only nonblank `name` (maximum 100 characters) and integer `quantity` >= 0. |
| Known SKU | Return normalized SKU, `found=true` and fixture warehouses. `DEMO-001` includes Bengaluru with quantity 12, consistent with M0's example. |
| Unknown SKU | Return normalized SKU, `found=false`, `warehouses=[]`; this is a successful lookup. |
| Zero quantity | A known warehouse with quantity 0 remains a found sample record; do not turn it into an unknown SKU. |
| Effects | Read-only and idempotent; preserve the approved M0 annotations. No API/database writes or external stock lookup. |

Successful MCP results use `isError=false`, `structuredContent` matching the output schema and a text block containing the same object serialized as JSON. Invalid arguments produce a safe `INVALID_ARGUMENT` execution error (`isError=true`), without success-shaped structured content. Unknown tools and malformed protocol messages use the SDK's MCP/JSON-RPC errors.

Reject a malformed fixture during startup and keep the workload unready; do not manufacture warehouse data. Fixture validation checks duplicate SKU records, invalid field types and negative quantities; booleans and floating-point values are not accepted as integer quantities. A missing/malformed file must not cause raw exception paths or file contents to leak to callers.

Tool inputs cannot override a destination URL, credentials, file paths or caller identity. Do not add output fields outside the approved schema merely to label sample data; use the tool description and documentation.

## 5. Hosted Microsoft Learn compatibility

The currently documented endpoint is `https://learn.microsoft.com/api/mcp`, using Streamable HTTP without authentication. This was checked against [Microsoft's official overview](https://learn.microsoft.com/en-us/training/support/mcp) on 16 October 2026; endpoint behavior still requires an actual MCP run. A browser GET or HTTP 405 is not an MCP compatibility test.

[M0's recorded probe](../evidence/m0/network-probe.json) initialized protocol `2025-06-18` and listed three tools; it did **not** call a tool. M4 must do a fresh SDK-based initialization, discover all tool-list pages, save the actual schemas and perform at least one read-only call chosen from those discovered schemas. Do not hardcode an assumed current tool set or treat earlier discovery as a current pass.

Use a harmless documentation query such as Kubernetes readiness versus liveness. Save the requested arguments, result content, useful source URL(s), elapsed time, UTC timestamp and negotiated/package versions. Human review must confirm the response contains actual relevant documentation, not merely a successful HTTP status or an empty answer. A fixture cannot substitute for this acceptance check.

Treat remote tool descriptions and returned text as untrusted data. A compatibility probe must not execute instructions, scripts or commands contained in them. Model-facing handling of untrusted tool content remains M6/M7 work.

Use verified HTTPS with finite connection/read/overall deadlines and explicit result-size/work limits. Exact values, supported session lifecycle, redirect handling and dependency pins belong to detailed design. Report timeout, transport/protocol errors or oversized responses clearly; never claim a silently truncated result is complete. Capture DNS/HTTPS/MCP evidence from a temporary in-cluster client as well as local SDK testing to establish the environment the gateway will later use.

If internet access, rate limits or the hosted service prevent a real call, mark the hosted check BLOCKED/FAIL with observed evidence. Inventory may still pass independently; M4 is not fully accepted until its required hosted checks pass. Do not switch providers silently.

## 6. Credentials and controlled fixtures

Microsoft Learn proves the **no-authentication hosted path** only. Controlled Streamable HTTP fixtures must support separate bearer-token and named API-key-header modes and reject missing/wrong credentials while accepting the configured test credential. They must not receive a person's gateway key or cookie.

Use artificial sentinel credentials, bounded errors and redacted logs/evidence; never record real keys. The actual gateway's secure storage, reserved header validation, credential injection, sanitization and member-token isolation are M5/M6 responsibilities. Supplying fixtures alone does not prove those gateway behaviors.

Provide controlled duplicate `service_info` names on separate test servers for M6 collision tests. Inventory's production discovery still exposes only `lookup_sku`; do not assume Microsoft Learn has `service_info`.

A real authenticated hosted-server run is **separate, unverified evidence**, not proved by either Microsoft Learn or controlled fixtures. It does not justify adding a paid provider or acquiring a credential without user approval.

## 7. Kubernetes requirements

Inventory runs inside Kubernetes with an internal ClusterIP Service and no Ingress, NodePort or LoadBalancer. Final traffic permits only the gateway caller; unrelated Pods must be denied. A temporary isolated M4 client may stand in for the gateway during tests, with explicit namespace/selectors and cleanup. No direct browser/client route remains after testing.

The Inventory workload has readiness/liveness probes, CPU/memory requests and limits, and no need for a Kubernetes API token, platform database access or shop credential. Its sample data travels with the image; no writable persistent disk is required. Liveness checks the local process, while readiness includes usable validated sample data. Hosted Learn outages must not make healthy Inventory unavailable.

Use the existing Helm chart with local/production-shaped values; do not create a second deployment system. Detailed design must propose exact image/package pins, names, ports, probe paths, security settings, network selectors/egress, deadlines and resource sizes for review before implementation. Reserve disposable test resources explicitly and protect existing M1/M2/M3 resources and PVCs.

## 8. Planned file ownership

| M4-owned path | Purpose |
|---|---|
| `services/sample_mcps/inventory.py` | Tool implementation and MCP/probe entry point. |
| `services/sample_mcps/data/` | Validated, clearly labelled sample warehouse fixture. |
| `services/sample_mcps/Dockerfile` and dependency files | Reproducible Inventory container. |
| `tests/sample_mcps/` | Unit, real MCP transport and controlled compatibility fixtures. |
| `scripts/m4/` | Independently runnable cluster and hosted checks with scoped cleanup. |
| `deploy/charts/urumi/templates/sample-mcps/` | Inventory Deployment, internal Service and traffic policy. |
| `docs/external-mcp.md` | Observed hosted setup, limitations and reproduction instructions. |
| `docs/evidence/m4/` | Sanitized commands, schemas, transcripts, cluster checks and final report. |

Shared chart values/helpers/dependencies and cross-module contracts require coordinated main-agent review. M4 does not silently edit M0 schemas, M2 storage or M3 behavior. Exact filenames may be refined during detailed design without expanding scope.

## 9. Measurable acceptance

The following acceptance criteria were planned before implementation; current verified outcomes and evidence are in section 12. Record exact commands, exit codes, versions and sanitized artifacts. Unit tests cannot prove live MCP, cluster enforcement or hosted compatibility.

| ID | Required observation | Evidence |
|---|---|---|
| M4-01 | Fixture validates; known, unknown, zero-stock and normalized SKU results match the M0 schema. Bad/extra inputs fail safely; malformed fixtures fail startup readiness. | Unit output and validation cases. |
| M4-02 | Real Streamable HTTP SDK client initializes, discovers exactly `lookup_sku` with approved schemas/annotations, and calls known/unknown/invalid cases. Text and structured successes agree. | Protocol/version transcript, discovered schemas, call results. |
| M4-03 | Same chart lints/renders for local and production-shaped values. Isolated cluster workload is Ready with probes/resources and no public exposure. | Helm output, image identity, resource/probe observations. |
| M4-04 | Permitted temporary caller connects/calls; unrelated Pod is denied within a deadline; permitted call succeeds afterward. A controlled failing liveness probe triggers observed kubelet restart, followed by restored probe/service recovery. | Allowed-denied-allowed and probe/restart transcripts. |
| M4-05 | Fresh local SDK and in-cluster client both initialize/discover the actual hosted endpoint; at least one real useful hosted call succeeds from the cluster. Save negotiated protocol, real schemas and documentation result. | Separate local/cluster hosted transcripts and reviewed source links. |
| M4-06 | Controlled bearer/custom-header fixtures reject missing/wrong and accept correct artificial credentials. Duplicate-name fixtures expose the intended identical names. No sentinel secret leaks in saved output/logs. | Fixture transport/authentication/redaction results. |
| M4-07 | Controlled unreachable/slow/invalid endpoints yield bounded observable failures; healthy Inventory continues to answer. No fixture result is labelled a real hosted pass. | Failure results with elapsed times and subsequent healthy call. |
| M4-08 | Temporary clients, test servers, permissions and resources are removed; existing shop data/resources are untouched. Independent review reports PASS/FAIL/BLOCKED and remaining gaps before user acceptance. | Cleanup/resource inventory and final report. |

M4-07 checks independent clients/services only; gateway aggregation and failure isolation still require M6/M10 evidence. Broad metrics such as retrieval precision are unnecessary for deterministic lookup/protocol checks.

## 10. Review and handoff

1. Review this specification; resolve scope questions and obtain user approval.
2. Add detailed design **inside this same file**; independently review and obtain the user's design approval before application implementation.
3. Implement M4-owned files, independently review, then run unit, real MCP, Kubernetes and genuine hosted checks.
4. Explain one Inventory request and one hosted call in plain language. Present results/gaps for module acceptance before M10 wiring.

No additional parallel-plan specification is needed. Open design items are concrete pins/resources/network rules, client lifecycle and bounded time/payload settings; the selected Inventory/Microsoft Learn scope is already recorded. Cross-server AI answers, actual gateway registration/authentication, three-source routing and the final two-user demonstration remain M6/M7/M10 checks.

**Independent review:** READY FOR USER REVIEW after clarifying the M2/M3 progression status and requiring actual failing-probe evidence for liveness. Scope, approved contract, hosted-versus-fixture evidence and module boundaries have no blocking review findings. At that specification-review gate, no M4 acceptance check had run; current outcomes are in section 12.

## 11. Concrete design for implementation review

**Design status:** Independently reviewed and approved by the user on 16 October 2026, followed by scoped implementation. The user requested implementation of both modules using subagents on 16 October. This design introduces no paid dependency, new production upstream or early integration.

### 11.1 The small implementation

`inventory.py` owns fixture loading, strict argument checks, the single MCP tool and HTTP health endpoints. It reads the unchanged `lookup_sku` definition from `contracts/mcp-tools.schema.json`; it does not duplicate or edit that contract. A list of sample records in `data/inventory.json` contains `DEMO-001` / Bengaluru / 12 and `ZERO-001` / Bengaluru / 0. Startup rejects missing files, unknown fields, duplicate normalized SKUs, empty names, invalid quantities and oversized fixtures. Records contain only `sku` and `warehouses`; successful responses are copied out so a caller cannot mutate future answers.

Use the same low-level Python MCP SDK pattern already verified in M3: `StreamableHTTPSessionManager(json_response=True, stateless=True)`, exact `/mcp`, and no long-lived per-caller state. The SDK negotiates the actual protocol. Preserve every M0 annotation, including `openWorldHint=true`. The call wrapper handles unknown names as MCP invalid-params errors and validates arguments itself before returning safe `INVALID_ARGUMENT` execution errors. `/livez` checks the process; `/readyz` succeeds only after fixture validation and MCP manager startup. Invalid startup configuration produces a fixed safe log message and exits; it cannot become Ready.

The HTTP boundary rejects browser Origin headers and unapproved Host names, allows at most 64 KiB of request body, and imposes a 10-second whole-request receive/dispatch deadline. Host names come only from operator settings, never from tool arguments. Default local hosts are `localhost` and `127.0.0.1`; Helm supplies the actual Service DNS names. This duplicates the small boundary locally rather than coupling Inventory to M3 application code.

### 11.2 Reproducible runtime and container

| Item | Exact design |
|---|---|
| Runtime | Existing Python 3.13.5 base: `python@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419`; build accepts the same immutable base argument used by M3. |
| Direct packages | `mcp==1.26.0`, `httpx==0.28.1`, `jsonschema==4.26.0`, `starlette==0.52.1`, `uvicorn==0.40.0`. |
| Dependency lock | Exact M3 transitive baseline in an M4-owned lock, omitting its unrelated OAuth dependency; image installation plus `pip check` and actual SDK tests verify compatibility. No change to the shared `.venv`. |
| Image | `urumi/inventory-mcp:m4` for isolated local checking; record built image identity. Production-shaped values accept an immutable published digest without publishing this assignment. |
| Process | `python -m services.sample_mcps.inventory`, port 8000; nonroot UID/GID 10001, read-only root, drop ALL capabilities, no privilege escalation, RuntimeDefault seccomp, no API-token mount. |
| Data bounds | Fixture at most 64 KiB, 100 SKU records, 20 warehouses per SKU; reject excess rather than truncate. No PVC, shop credentials or network client in the Inventory process. |

### 11.3 Helm and temporary resource boundaries

Use `templates/sample-mcps/resources.yaml` in the existing chart, gated by `inventoryMcp.enabled` (false by default). Resource name is `<release>-inventory-mcp`, with `app.kubernetes.io/name=urumi`, instance `<release>`, component `inventory-mcp`. Deployment has one replica and a ClusterIP Service, both port 8000. There is no Ingress, NodePort or LoadBalancer.

Requests are CPU 50m / memory 64Mi; limits CPU 250m / memory 128Mi. Startup probe `/livez` runs every 2s with timeout 2s, threshold 30. Liveness `/livez` and readiness `/readyz` run every 10s with timeout 2s, threshold 3. These are initial small-server budgets validated by observed cluster readiness, not throughput promises.

NetworkPolicy selects only this release's Inventory Pod: permit TCP8000 ingress only from same-namespace Pods with name `urumi`, this release's instance, and component `gateway`; deny all egress (Inventory needs no DNS or outbound connection). The test caller temporarily carries that exact gateway label in the dedicated test namespace. Unrelated Pods do not. Final real gateway wiring remains M10.

Reserve namespace/release `urumi-m4-check`, marked `urumi-check-owner=m4`, and refuse an existing namespace rather than deleting unknown resources. The check script snapshots existing `urumi` Deployment/StatefulSet/Service/PVC identities before and after. It installs with foundation, store and Woo MCP disabled. All temporary Jobs/fixture Pods live only in this namespace and the owned namespace is removed in `finally`; the production `urumi` release and its disks are never upgraded by M4.

Actual liveness evidence comes from patching only this temporary Inventory Deployment's liveness path to a nonexistent path, recording the new Pod UID after that patch and observing its positive container restart count with kubelet unhealthy/killing events before any restoring rollout, restoring `/livez`, then observing recovery and a successful MCP call. A rollout alone is insufficient.

### 11.4 SDK probe bounds and real hosted evidence

`scripts/m4/probe.py` is an independent client, not gateway code. It uses verified TLS, no environment proxy inheritance, no redirects, HTTP phase limits of connect/pool 5s and read/write 15s, and a 45-second whole-session deadline including initialization, discovery, call and cleanup. An HTTPX streaming wrapper rejects a response exceeding 2 MiB or total received bytes exceeding 8 MiB; discovery permits at most 20 pages / 200 tools and rejects repeated cursors. Serialized call results are at most 2 MiB. Limits produce explicit failures, never silently truncated PASS results.

The client supports SDK-managed stateless or stateful upstream sessions, records the negotiated protocol and whether a session identifier was supplied without publishing that identifier, and closes streams/client on every outcome. It attempts normal SDK session termination only for its own created session within the overall deadline; it does not delete somebody else's session. Tools/call content remains data and is never evaluated or executed.

Microsoft Learn is the only hosted URL in the acceptance runner. Fresh local and temporary in-cluster probes independently list all actual tools. Choose an actual discovered read-only documentation-search tool whose schema supports a harmless readiness/liveness query; verify arguments against its discovered schema before sending. If current schemas do not support that query, fail with the schema evidence for review rather than inventing a tool. Save timestamp, package/protocol versions, real complete discovered schemas, selected name/arguments, elapsed time, result and source links. Review links/text for meaningful Kubernetes documentation before M4-05 can pass. Retain separate local/cluster artifacts. External outages remain BLOCKED evidence, not a fixture substitute.

### 11.5 Controlled compatibility and failures

`tests/sample_mcps/fixtures.py` exposes two separate Streamable HTTP servers advertising the same `service_info` name. One requires an artificial bearer sentinel, the other an artificial `X-Test-Api-Key` sentinel. Constant-time comparison rejects missing/wrong values with HTTP401; neither fixture logs received headers. The sentinel is test data only. Save assertions and status categories, never configured sentinel strings. Run real TCP SDK missing/wrong/valid cases; these are fixture checks, not authenticated-hosted claims. Inventory still exposes only `lookup_sku`.

The same test harness supplies controlled slow, unavailable and malformed MCP endpoints. Probe timeout/transport/protocol errors must complete inside finite deadlines, then a fresh healthy Inventory call must pass. Negative tests cover oversized body/result and repeated tool-list cursors so the stated client bounds are executable checks. No fixture implements a gateway, registry, model call or production authentication.

### 11.6 Exact file responsibilities and check order

| Files | Responsibility / proof |
|---|---|
| `services/sample_mcps/inventory.py`, `data/inventory.json`, package marker | Minimal application, contract-driven schemas, safe fixed fixture. |
| `services/sample_mcps/Dockerfile`, `requirements.in`, `requirements.lock.txt` | Exact dependency/image inputs and nonroot application/test-client image. |
| `tests/sample_mcps/test_inventory.py`, `test_protocol.py`, `fixtures.py`, `test_compatibility.py` | Fixture/argument cases, real TCP discovery/calls, host/body errors, controlled auth/collision/failure/limit checks. |
| `tests/sample_mcps/cluster_client.py`, `values-check.yaml` | Real in-cluster permitted/denied MCP calls and isolated Helm settings. |
| `scripts/m4/probe.py`, `check-m4.ps1` | Bounded hosted probe plus exact cluster actions, logs, snapshots and scoped cleanup. |
| `deploy/charts/urumi/templates/sample-mcps/resources.yaml` | Deployment, Service and enforced gateway-only ingress / deny-egress policy. |
| `docs/external-mcp.md`, `docs/evidence/m4/` | Reproduction, actual results/schemas, source review and limitations. |

Order: unit/real TCP controlled checks -> build and Linux package check -> chart lint/render local and production -> isolated Ready/internal-only check -> allowed-denied-allowed -> actual bad-liveness restart/recovery -> local and cluster real Learn probes -> scoped cleanup and unchanged-resource snapshot -> independent source/evidence review. These checks implement M4-01 through M4-08; nothing implies the M6/M10 gateway path already works.

**Independent concrete-design review:** READY FOR USER REVIEW; no blocking technical findings. Preserve exact M0 annotations, real hosted-versus-fixture evidence, same-Pod kubelet restart proof and scoped cleanup. At that design-review gate, no implementation or acceptance check had run. User approval and implementation followed.


## 12. Implementation and verification outcome

Implemented the concrete M4 design and completed all eight acceptance checks on 16 October 2026. Host10 and Linux10 test methods passed; a final host-only four-method compatibility run added real closed-port failure evidence. Actual local and in-cluster Microsoft Learn discovery/calls passed with meaningful reviewed documentation. The isolated namespace was removed and existing store resource/PVC identities were unchanged. Independent source/evidence review returned PASS; user module acceptance remains pending.

See [report](../evidence/m4/report.md), [acceptance results](../evidence/m4/acceptance-results.json), [independent review](../evidence/m4/acceptance-review.md) and [reproduction runbook](../external-mcp.md). Raw results and the initial corrected OCI-identity comparison failure remain preserved. No real gateway/shop integration, paid dependency or authenticated hosted-provider claim is included.
