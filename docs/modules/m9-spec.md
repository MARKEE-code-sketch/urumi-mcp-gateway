# M9 specification - release package and operating guide

**Status:** Specification and concrete design approved by the user's implementation request. M9 packaging is implemented; independent acceptance review passed all 12 static package criteria. User module acceptance is pending. No combined deployment is authorized in M9.  
**Date:** 18 October 2026.  
**Sources:** Assignment DOCX sections Kubernetes and Helm, Deliverables, Demo video, and Upgrades and rollback; [blueprint M9](../../blueprint.md#m9-release-package-and-operating-guide); [M10 boundary](../../blueprint.md#m10-final-integration-and-acceptance); [project decisions](../decisions.md); [working rules](../../AGENTS.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Prepare one Helm release package and clear instructions for installing, operating and explaining the mandatory single-store system.

**WHY:** A reviewer must be able to reproduce our setup. A collection of separately tested containers is not yet a documented installation. The assignment also requires a production-like VPS path using the same charts.

**HOW:** Collect the reviewed modules' container definitions, ports, health checks, configuration, persistent disks and Secret references into the existing chart. Give it separate local and production values. Check both rendered configurations and write step-by-step operating guides. M10 later connects the real backend modules, builds their combined image, installs the complete system and proves the user journeys.

Think of Helm as a reusable installation recipe. A **values file** supplies environment settings, similar to configuring the same Docker Compose project for different machines. A **render** converts that recipe into Kubernetes resource definitions; it does not start containers.

| Term | Plain meaning and Docker connection |
|---|---|
| Pod / Deployment | A running container group and the controller that maintains its desired copies. |
| Service | A stable internal address in front of Pods, similar to a Compose service name. |
| Ingress | Rules for the cluster's web entrance, similar to a reverse proxy's host/path routing. |
| PVC | A request for persistent storage, serving the purpose of a named Docker volume. |
| Secret / ConfigMap | Private runtime credentials / ordinary runtime settings. A Secret's base64 representation is not encryption. |
| Probe / resource requests and limits | Health checks / CPU and memory reservations and caps. |
| Namespace / RBAC / NetworkPolicy | A resource grouping / Kubernetes API permissions / permitted network traffic. |
| VPS / k3s | A rented machine / the Kubernetes distribution used directly there and through local k3d. |

M9 delivers packaging readiness. It must not describe a successful render as a working application or a live VPS deployment.

## 2. Scope, prerequisites and current evidence

| Included in M9 | Owned elsewhere or excluded |
|---|---|
| Shared chart, common values and environment-specific settings | Real service wiring and `backend/main.py` / `orchestrator.py`: M10. |
| Backend deployment template and packaging contract | Replacing tested backend business logic or creating another gateway implementation. |
| Repeatable image build/import/pull instructions | Building and accepting the combined backend before its M10 entry point exists. |
| Local and k3s setup, operation, security and architecture notes | Buying hosting/domains, creating cloud accounts or deploying to a VPS. |
| Static chart checks and isolated build/configuration checks | Applying the combined release, restarting the retained shop or exercising real checkout/chat: M10. |
| Private handoff checklist with accurate evidence status | Publishing a repository, sending invitations to reviewers, uploading a video or submitting the form. |

M9 implementation depends on reviewed M1-M8 component artifacts and their user progression gates. Drafting this specification does not assert those gates are complete. Existing M6 evidence records passing isolated checks; M7's implementation has passing host/Linux tests but its real-provider check is still blocked. M8 is being specified separately. M9 documentation must preserve these distinctions and must not label all modules accepted.

The existing chart already contains module-specific store, WooCommerce MCP, Inventory, PostgreSQL, Secret-access and disposable check templates. Its local/production files are partial. `backend/Dockerfile` currently starts the **M5 check harness**, not the final backend. M9 must identify that fact and ensure a release configuration cannot quietly start a test substitute.

## 3. Requirements and traceability

The first column separates product requirements from already agreed project work and recommendations. A recommendation is not permission to add a feature.

| Source / status | M9 responsibility | Proof owned by M9 / later proof |
|---|---|---|
| Required: local Kubernetes and same Helm charts for production-like VPS | One chart supports both configurations without editing templates or source for the environment. | Both renders and a values-difference inventory / actual full deployment M10; live VPS optional. |
| Required: all application components in Kubernetes | Describe and render store, MariaDB, Woo MCP, Inventory, PostgreSQL, backend and dashboard resources. | Workload/resource inventory / Ready runtime inventory M10. |
| Confirmed choice: Microsoft Learn is the third upstream | Document its external hosted URL and outbound dependency; do not invent a third locally hosted MCP workload. | Configuration and trust-boundary inspection / real registration/calls M10. |
| Required: persistence, stable Ingress URLs, Secrets, probes and resource limits | Carry each component's agreed storage, routing, credential and health contracts into release settings. | Rendered-resource assertions / restart, reachability and retention M10. |
| Required: Woo MCP internal and gateway-only; server-side credentials | Preserve internal services and gateway-only policy selectors; keep credentials out of images, frontend and values. | Static exposure/policy/reference checks / allowed-and-denied live traffic M10. |
| Required: README and design/threat notes | Explain setup and the actual tool/authentication/data paths in beginner-friendly language. | Documentation and command review / fresh complete installation M10. |
| Required: production story and video explanation | Document DNS, ingress, storage, secrets, image distribution and limitations. | Runbook review / video and final handoff M10. |
| Agreed blueprint: backup, migration, upgrade and rollback guidance | Supply safe ordered procedures consistent with existing module recovery contracts. | Procedure validation and clearly marked pending execution / combined-system rehearsal M10. |
| Optional: actual VPS, cert-manager, multi-store, scaling | List only if actually implemented and independently evidenced. | No optional work starts through this specification. |

## 4. Package and file ownership

Existing owners retain business logic and module-specific templates. M9 changes shared packaging only where necessary; API or security-contract changes return to the owning module and user review.

| Owner / files | Responsibility |
|---|---|
| M9: `deploy/charts/urumi/{Chart.yaml,values.yaml,values-local.yaml,values-prod.yaml,values.schema.json}` | Release metadata, settings, validation and environment examples. |
| M9: `deploy/charts/urumi/templates/backend/` and shared networking resources | Final backend deployment contract, internal Service, public route references and reviewed policy coordination. Exact filenames come in design. |
| M9: `backend/Dockerfile`, `scripts/build-images.ps1` | Reproducible backend packaging and named image-build workflow. Preserve independently used harness paths explicitly; final runtime command belongs to M10's entry-point contract. |
| M2-M5 and M8 component owners | Store, MCP, database/access and dashboard definitions. M9 reviews their compatibility and makes only approved coordination changes. |
| M9: `README.md`, `docs/system-design.md`, `docs/threat-model.md`, `docs/operations.md`, `docs/optional-items.md` | Local/production setup, explanation, operating procedures and honest scope index. |
| M9: `tests/release/`, `scripts/m9/`, `docs/evidence/m9/` | Focused chart/configuration checks and sanitized results. Exact test/runner files come in design. |
| M10: `backend/{main,orchestrator}.py`, `tests/e2e/`, final demo artifacts | Combined application, runtime acceptance and final evidence completion. |

Inputs are reviewed component contracts and artifacts. Outputs are a checked chart, validated settings, image-build definitions, operating documents and a report separating present proof from pending M10 work.

## 5. Functional and technical requirements

### 5.1 One chart, two environments

- Keep `deploy/charts/urumi` as the shared chart; do not add Kustomize or a separate production implementation.
- Supply clearly identified complete-core local and production configurations. Disposable foundation/M5/M6 check workloads are disabled in both release profiles. Microsoft Learn remains a registry configuration target, not a deployed Pod.
- Base defaults must be safe and explicit. The later design decides which components default to enabled; the release profile must enumerate the intended mandatory workload set rather than inherit accidental test settings.
- Environment changes must use values: hostnames, URL/origin settings, ingress class, storage classes/sizes, image references/pull policy, Secret names, resource settings and network selectors as needed. Configured namespaces and release names must consistently reach Service DNS, RBAC and policy references; any intentional fixed-name restriction must fail clearly and be documented.
- Validate required types, ranges, incompatible modes and safety-sensitive values with `values.schema.json` and focused template checks. Negative checks must reject unsupported multi-replica backend operation and release profiles that enable check harnesses. Do not introduce broad schema machinery beyond used settings.
- Production examples must identify every operator-supplied field. Keep placeholders unmistakable and provide preflight validation that refuses deployment with unresolved required placeholders or missing Secret references. A renderable example is not deployment-ready by itself.
- Document images by immutable release reference and record build inputs. Exact tags/digests, image-pull Secrets and registry choice are design/operator decisions; do not publish images or assume access to a paid registry.

### 5.2 Workloads, startup and network boundaries

- Include required probes and CPU/memory requests/limits for every application/database workload, preserving component semantics. Backend liveness checks the process; readiness checks its agreed dependencies and exclusive lifecycle ownership. A temporarily dead upstream must not mark the whole gateway dead.
- Keep one backend replica and one worker, consistent with M5 ownership/recovery. Use a startup/update strategy that does not create competing owners. Do not add horizontal scaling in packaging.
- Preserve persistent MariaDB, WordPress content and platform PostgreSQL claims and existing data. Document uninstall/upgrade retention behavior explicitly, including storage-class reclaim effects; never assume Helm rollback restores deleted data.
- Public entrances are the storefront and dashboard, with the dashboard's backend API and single gateway MCP endpoint routed as designed. Keep database, Woo MCP and Inventory Services internal. Define browser origin/cookie/CSRF and forwarded-header trust configuration consistently; no wildcard credentialed browser access.
- Preserve gateway-only Woo MCP ingress, required database paths, DNS, and narrowly scoped Kubernetes Secret permissions. Document necessary gateway outbound access to Microsoft Learn, Groq and compatible registered external servers. A manifest is only static policy intent; effective enforcement remains a live M10 check.
- Reconcile the existing Woo MCP caller selector `component=gateway` with PostgreSQL's `component=backend` for the one combined backend. Design must select consistent labels/policies and provide a rendered allowed/denied path inventory; do not simply assume these existing selectors match.
- A normal dashboard Pod must not receive the backend Kubernetes ServiceAccount token or upstream/provider credentials. Do not place Secrets into generated JavaScript, public configuration, container layers or chart defaults.
- Specify runtime Secret names/keys and ownership, with Secret values supplied privately by the operator. The backend may manage owned dynamic upstream credentials only within the dedicated Secret namespace; it must not gain cluster-admin or deployment permissions.

### 5.3 Bootstrapping and image workflow

The guides must show an ordered path: prerequisites and explicit cluster context -> image build/import or private pull -> namespace/Secret preparation -> database readiness and migrations -> one-time admin/bootstrap -> application startup -> built-in upstream reconciliation and readiness checks. Exact executable wiring and lifecycle implementation remain M10.

- Reuse M5's forward-only SQL migration, exclusive ownership and first-admin bootstrap behavior. Rerunning setup must not reset passwords, revive revoked keys or overwrite administrator edits. Describe which steps are currently runnable and which need M10; no pretend working all-in-one install command.
- Explain how WooCommerce REST credentials and provider credentials are obtained privately. Keep generated files, database dumps, `.env`, raw keys and machine-specific kubeconfig files ignored. Do not print them in shell history, logs or shared evidence.
- Build instructions must name repository-root working directory, active shell, prerequisite versions, image names and failure behavior. Windows instructions use PowerShell; VPS instructions explicitly use the Linux shell. Do not mix shell syntax.
- The build workflow must stop on failure and avoid changing cluster state. M9 may build reviewed standalone artifacts and check dependencies. The combined backend build must fail clearly or be marked unavailable until M10 supplies its real entry point; the existing harness must never satisfy that requirement.

### 5.4 Local-to-VPS operation

Local instructions explain Docker Desktop, k3d, Traefik, stable `.test` hosts and the existing local-path storage approach. Production instructions explain k3s prerequisites, actual DNS records, ingress/controller configuration, firewall/public ports, storage availability, private image pulls, backups and trusted certificates.

The current production values contain example hosts and Woo HTTPS transport assumptions. Design must resolve canonical public shop origin versus the internal REST transport, permitted Host names, certificate trust, ports and NetworkPolicies consistently with M3's approved OAuth 1.0a signed requests. Do not switch authentication or disable TLS verification to make the example work. Browser TLS certificate provisioning is required for a usable secure HTTPS configuration; automating it with cert-manager remains optional. Explain any approved internal HTTP transport's lack of encryption.

Resource values are documented starting points grounded in module evidence, not a high-availability or load-test claim. Storage on one VPS is not replicated/off-machine backup. No hosting purchase, machine changes, live VPS access or provider calls are part of M9 checks.

### 5.5 Operating and handoff documents

`README.md` must provide a short architecture overview, prerequisites, local setup, production-like setup, troubleshooting entry points and instructions for checkout, dashboard chat and external MCP connection. External clients receive only the gateway URL and their own personal key, never upstream URLs/credentials as configuration requirements. State current compatibility evidence accurately; Codex and Inspector final checks remain M10.

`docs/operations.md` must cover:

- Secret provisioning/rotation responsibilities, bootstrap recovery and explicit context/namespace safeguards.
- PostgreSQL and MariaDB backups plus WordPress-content backup, ownership/permissions, private/off-machine storage and a consistent recovery point; backup files contain sensitive data.
- Restore into an isolated target first, including corresponding Secret/configuration recovery and database-to-credential-reference consistency. Never restore over the retained installation as a packaging test.
- Image/chart version inventory, pre-upgrade backups, migration compatibility and ordered rollout checks for store/MCP/backend/dashboard.
- Helm history/rollback with an explicit reviewed revision; database schemas and disk contents are not rolled back by Helm. Incompatible database changes require a reviewed restore/migration procedure, not blind rollback.
- Troubleshooting probes, events, storage, DNS, policy, registry/provider availability and safe logs without dumping Secrets.

`docs/system-design.md` must explain component ownership and complete browser/client -> gateway -> upstream -> shop flows, collision naming, isolation/timeouts, audit lifecycle, chat identity and production changes. `docs/threat-model.md` must cover shared upstream authority, no forwarding of personal keys, malicious tool descriptions/results, SSRF/DNS checks and limitations, member boundaries, RBAC, network access and container privilege exceptions. Describe implemented controls and remaining risks separately from optional hardening.

`docs/optional-items.md` lists only actually completed extras with evidence; “None” is valid. The handoff checklist includes sources, chart/values, setup/notes, sanitized evidence, chronological workflow log, relevant `.agents` configuration, demo video and private repository access. M10 supplies the final demo and verifies reviewer access. Preparing a checklist authorizes no publishing or submission.

## 6. Independent acceptance criteria

All results require saved commands, exit codes and inspectable artifacts. These are future checks, not measured outcomes. M9 must stop short of applying the combined release.

| ID | Check | Measurable pass condition / evidence |
|---|---|---|
| M9-01 | Prerequisite/ownership inventory | Every mandatory component maps to image/build definition, ports, health endpoints, settings/Secrets and owning module; unresolved M7/M8/M10 gates remain visible. Save inventory and gap list. |
| M9-02 | Shared chart | `helm lint` and `helm template` succeed for local and production examples with explicit release/namespace and the same chart revision. Save both renders and command output; no template edits between environments. |
| M9-03 | Value validation | Focused negative tests reject wrong types/missing required deployment inputs, unsupported backend replicas, unresolved deploy placeholders and enabled harnesses in release profiles. Each rejection has an expected reason; valid examples pass their appropriate render/preflight mode. |
| M9-04 | Resource completeness | Parse both full-core renders: all intended workloads present, all check workloads absent, every container has required resources and each workload has probes; all Service/Ingress/config references resolve structurally. Report an explicit inventory, not a text-search-only PASS. |
| M9-05 | Persistence | Both renders retain the three required storage purposes, preserve reviewed mount paths and identify claim ownership/retention; runbook covers backup/restore/reclaim consequences. No live disk deletion or restart. |
| M9-06 | Exposure and policies | Both renders expose only reviewed storefront/dashboard/API/MCP routes; Woo MCP and databases lack external Services/Ingress. Policy selectors match intended gateway/workload labels, include required DNS/egress paths, and RBAC stays namespace-scoped. Save static assertions; do not claim live enforcement. |
| M9-07 | Credentials and browser boundary | All credential-bearing settings reference operator-managed Secrets; frontend/public config has none. Scan tracked/reviewable source and proposed handoff contents for actual privately known test sentinels and prohibited generated/private files without printing values. Save sanitized counts and exclusions. |
| M9-08 | Image/build contract | Reviewed standalone images build or have reproducible existing evidence with matching source/version; dependency checks pass where applicable. Build script rejects missing final backend entry point rather than using a harness. Record combined build as pending M10 until real wiring exists. |
| M9-09 | Same-chart production readiness | A field-by-field environment difference table explains DNS, ingress/TLS, storage, Secrets, images, origins and resource settings. Every placeholder has a provisioning source and preflight rule; production REST transport/trust decision is reviewed and internally consistent. No claim of live VPS proof. |
| M9-10 | Documentation completeness | Required README, design, threat, operations and optional-index files exist, links resolve, command working directories/shells are stated, required walkthroughs and all backup/migration/rollback caveats are present. Review against section 5 and assignment deliverables. |
| M9-11 | Reproducibility boundary | An isolated staging directory can prepare/render the package from documented non-secret inputs without relying on private `.tools`, `.venv`, `.env` or kubeconfig contents. Capture exact prerequisite versions and dependency/build gaps. Complete fresh live installation remains M10. |
| M9-12 | Independent review and safe closure | Reviewer maps all criteria to source/saved evidence and records PASS/BLOCKED/FAIL honestly. No Kubernetes mutations or provider calls occurred during M9 checks; existing shop/release untouched. Report remaining M10 steps and stop for user acceptance. |

The design will specify exact checker commands, tools and fixture inputs before implementation. No precision/recall metric applies: correctness here is valid configuration, secure boundaries and reproducible operator instructions.

## 7. Review decisions and next gates

These need concrete design after specification approval, inside this same file:

1. Final values structure, full-core enablement and namespace/release portability, without breaking independent module check profiles.
2. Backend image/runtime contract and safe handling of the unavailable M10 entry point; exact migration/bootstrap command handoff.
3. Same-origin dashboard/API/MCP ingress layout, trusted proxy settings, public HTTPS and internal Woo REST transport/certificate arrangement.
4. Schema/preflight boundaries, resource starting values, immutable image references and private distribution path.
5. Backup/restore, retained-PVC and credential recovery procedures, with any destructive rehearsal reserved for explicit isolated M10 work.

**Recommended smallest approach:** keep the existing chart and module contracts, add only missing release settings/templates/checks, write straightforward PowerShell/Linux instructions and defer full runtime demonstration to M10. Avoid introducing operators, GitOps systems, new secret managers or deployment frameworks.

**Review gate:** This document asks for approval of M9's scope and checks only. After your specification review, prepare and independently review the concrete design in this file. Implementation follows its approval. After M9 evidence and your module acceptance, M10 receives the combined-runtime work; a pending provider/module criterion must remain explicitly tracked rather than silently marked passed.

## 8. Concrete design for review

### 8.1 WHAT, WHY, HOW and boundaries

**WHAT:** Finish the installation recipe and operating instructions, without installing the combined application. **WHY:** The existing module check Pods are useful tests, but are not the final backend. **HOW:** Render the seven real workloads, check their references and security boundaries, and document the missing M10 startup work explicitly.

Assumptions: one store, one backend process, Traefik, cluster DNS suffix `cluster.local`, and local-path storage for the documented single-node k3s examples. Microsoft Learn remains external. Resource values below are starting settings from existing module checks, not a load-test promise. M7's live-provider gap remains visible. M8 and M9 are individually reviewed before M10 connects them.

No cluster mutation, Secret creation, provider request, disk restart, production deployment, image publication or private repository publication is part of M9 implementation/testing. Rendered placeholder images prove packaging structure only.

### 8.2 Files and concrete values contract

Keep existing component values and add the following small groups to `values.yaml`. Existing independent test profiles remain usable because `release.enabled` and all new workloads default to `false`.

| Setting | Exact meaning / starting value |
|---|---|
| `release.enabled`, `release.environment` | Complete-core validation switch; default `false`, environment `local` or `production`. |
| `backend.enabled`, `backend.replicas`, `backend.workers` | Default `false`, `1`, `1`; values other than one are rejected when enabled. |
| `backend.image.{repository,tag,digest,pullPolicy}` | Default `urumi/backend`, `m10-unavailable`, empty digest, `IfNotPresent`; digest takes precedence over tag. |
| `backend.origin`, `backend.allowedHosts` | Exact browser origin and permitted HTTP Host names; local `https://dashboard.urumi.test`; derive backend Service hosts for health checks and add the public hostname. |
| `backend.existingProviderSecret`, `backend.model` | `urumi-groq`, `openai/gpt-oss-20b`; Secret key `api-key`. |
| `backend.resources` | Requests `100m/256Mi`; limits `1000m/512Mi`, preserving the M5/M6 isolated starting envelope. |
| `backend.networkPolicy.{enabled,apiServerCidrs,apiServerPort}` | Enabled in release; operator supplies API endpoint CIDR(s), normally host `/32` or `/128`, and target port, currently `6443`. No machine address in shared values. |
| `dashboard.enabled`, `dashboard.image.{repository,tag,digest,pullPolicy}`, `dashboard.resources` | Default disabled; `urumi/dashboard:m8`; nonroot HTTP container `8080`, Service `80`; requests `25m/32Mi`, limits `250m/128Mi`, to be checked by M8. |
| `dashboard.ingress.{host,className,tlsSecret}` | Local `dashboard.urumi.test`, `traefik`, `urumi-dashboard-tls`; same Ingress carries API and MCP paths. |
| `store.ingress.tlsSecret` | Empty for the current local HTTP shop; production `urumi-shop-tls`. No automatic certificate issuance. |
| `woocommerceMcp.hostAliases` | Empty locally; production supplies public shop hostname mapped to the actual Traefik Service IP. This is ordinary DNS-routing configuration, not a TLS override. |
| `woocommerceMcp.networkPolicy.transportMode` | `direct-http` locally, `ingress-https` in production; selects WordPress TCP80 or Traefik TCP8443 egress respectively. |
| `networking.ingressNamespace`, `networking.ingressPodLabels`, `networking.ingressTlsTargetPort` | `kube-system`, existing Traefik name/instance labels, `8443`; override for a different installation after verifying its Service-to-Pod target. |
| `imagePullSecrets` | List of already provisioned image-pull Secret names; empty locally. Applied to image-consuming workloads without exposing credentials. |

M9 owns `templates/backend/{deployment,service,configmap,networkpolicy}.yaml`, `templates/dashboard/{ingress,networkpolicy}.yaml`, `templates/release-validation.yaml`, and `values.schema.json`. M8 owns the dashboard image/application/health endpoints and `templates/dashboard/{deployment,service}.yaml`, including their security and probes; M9 reviews their release compatibility rather than duplicating them. M9 edits existing Woo/Inventory caller policies, Woo host derivation/transport egress, store TLS/WordPress ingress policy and shared Secret-namespace retention only where required by this contract. Existing PVC names and mounts stay unchanged. Backend Docker packaging gains an explicit release target; existing check commands remain separate.

Use `.Release.Name` and `.Release.Namespace` to derive Service names, own-cluster URLs, shop labels and namespace selectors. Default internal allowlist is exactly `http://RELEASE-woocommerce-mcp.NAMESPACE.svc.cluster.local:8000/mcp` and `http://RELEASE-inventory-mcp.NAMESPACE.svc.cluster.local:8000/mcp`; no arbitrary internal CIDR is allowed by M5 registration. Additional internal targets require a separately reviewed operator setting, not free-form browser input. Woo MCP accepts its short Service name, namespace `.svc` name and fully qualified Service name; derive these as Inventory already does.

`platformAccess.secretNamespace` remains explicit, defaults to `urumi-upstream-secrets`, must differ from the application and system namespaces, and must be dedicated to one installation. A second installation must choose a distinct Secret namespace. Preserve its existing ownership labels, add Helm `keep` retention so uninstall does not recursively delete dynamic credentials, and document retained namespace/RBAC ownership on reinstall. Backend ServiceAccount stays in `.Release.Namespace`; its Role/RoleBinding only permit `get/create/update/delete` Secrets in the dedicated namespace. No cluster-wide role, list/watch permission, workload permission or application-namespace Secret read permission is added.

### 8.3 Two complete profiles and workload inventory

Both environment files explicitly enable `release`, `store`, `woocommerceMcp`, `inventoryMcp`, `platformDb`, `platformAccess`, `backend`, and `dashboard`. Both explicitly disable `foundation`, `m5Harness`, and `gatewayCheck`. A release with any harness enabled fails rendering. Base settings alone preserve disabled workloads and old module-specific check files remain separate.

| Workload | Service / container ports | Probes | Persistent disk / starting resources |
|---|---|---|---|
| WordPress Deployment | 80 / 80 | Existing `/urumi-live.php`, `/urumi-ready.php` | WordPress-content PVC 2Gi, `/var/www/html`; requests 100m/256Mi, limits 1000m/768Mi. |
| MariaDB StatefulSet | 3306 / 3306 | Existing `healthcheck.sh` | MariaDB-data PVC 2Gi, `/var/lib/mysql`; 100m/256Mi -> 1000m/768Mi. |
| Woo MCP Deployment | 8000 / 8000 | Existing `/livez`, `/readyz` | None; 100m/128Mi -> 500m/256Mi. |
| Inventory MCP Deployment | 8000 / 8000 | Existing `/livez`, `/readyz` | None; 50m/64Mi -> 250m/128Mi. |
| PostgreSQL Deployment | 5432 / 5432 | Existing `pg_isready` | Platform-data PVC 2Gi, `/var/lib/postgresql/data`, existing PGDATA child; 100m/128Mi -> 500m/512Mi. |
| Backend Deployment | 8000 / 8000 | `/health/live`, `/health/ready`; startup live check 2s x60, readiness 5s/timeout5s, liveness 10s/timeout2s | None; 100m/256Mi -> 1000m/512Mi. |
| Dashboard Deployment | 80 / 8080 | `/livez`, `/readyz`; startup 2s x30, readiness 5s, liveness 10s, timeout2s | No persistent disk; 25m/32Mi -> 250m/128Mi. |

Backend is `replicas: 1`, `strategy: Recreate`, one Uvicorn worker, UID/GID10001, read-only root filesystem, RuntimeDefault seccomp, no added capabilities, no privilege escalation. Dashboard follows M8's nonroot static-image contract and has no ServiceAccount token. Existing WordPress/database writable paths and image privilege exceptions are explained, not silently hardened.

Local values use release/namespace `urumi`, local-path PVCs, existing module image references for store/MCP, and visibly unavailable combined-backend reference. Production values use `shop.example.com` and `dashboard.example.com`, operator private image repositories/digests and existing TLS/image-pull Secrets. Both use one replica; production is a single VPS configuration, not high availability. Production example defaults to local-path only if the operator has verified it exists; actual storage class and capacity are preflight inputs. Seven workloads are structurally renderable even before the final backend image exists; deployment readiness is a different check.

### 8.4 Same-origin routing and network boundaries

Dashboard Ingress has `/api/v1` Prefix and `/mcp` Prefix to backend Service8000; `/` Prefix to dashboard Service80. Keep paths intact, no stripping/rewrite. Health endpoints remain internal. Store Ingress has only `/` to WordPress80. All Services are ClusterIP, including existing headless MariaDB; no MCP upstream/database public route or NodePort is introduced.

Both cluster profiles require an HTTPS dashboard because existing M5 Secure-cookie rules allow HTTP only on a loopback-only listener. For local use, the operator supplies a certificate trusted by their browser for `dashboard.urumi.test`; using a local CA such as mkcert is proposed. Certificate installation and changing the machine trust store are separate operator actions, not M9 checks. Production uses a publicly trusted certificate. Cert-manager automation remains optional. No wildcard CORS or credentialed cross-origin frontend request is needed.

Preserve backend `component=backend` for PostgreSQL and add `urumi.dev/gateway: "true"` to the same Pod. When `release.enabled=true`, Woo/Inventory ingress policies select name `urumi`, current release instance, `component=backend` and this gateway marker. Standalone M3/M4 profiles retain their existing exact `component=gateway` caller selectors; otherwise changing the final backend label would break their independently tested client Pods. Both modes receive parsed policy-selector regression checks. The isolated M6 policy/templates are separate and unchanged. Frontend receives neither the gateway marker nor backend token.

| Source -> destination | Allowed traffic / controls |
|---|---|
| Traefik -> WordPress / dashboard / backend | TCP80 / TCP8080 / TCP8000 with exact controller namespace+Pod selectors. Backend policy blocks arbitrary sibling callers. Kubernetes probe traffic remains subject to actual CNI/node behavior; static assertions are not enforcement proof. |
| Backend -> PostgreSQL / Woo / Inventory | TCP5432 / TCP8000 / TCP8000, exact release/workload selectors. |
| Backend -> Kubernetes API | Operator-verified API endpoint CIDRs and target port; mounted serviceaccount CA validates TLS. Service DNAT can affect enforcement, so M10 must verify the exact allowed path. |
| Backend -> DNS | kube-system kube-dns UDP/TCP53. |
| Backend -> public external providers/MCP | TCP443 to public addresses, excluding private/loopback/link-local/multicast/reserved ranges in policy where supported; M6 still independently validates DNS targets and enforces numeric checked dialing. Policies cannot identify a TLS hostname or prevent every DNS-rebinding/CNI risk. HTTPS origins on nonstandard ports are outside this release profile. |
| Woo -> shop | Local WordPress TCP80; production selected Traefik Pod TLS target8443 plus DNS, as explained below. |
| WordPress -> MariaDB | Existing exact TCP3306 policy; existing isolated M2 setup permission retained. |
| Dashboard / Inventory | No outgoing application access. Woo only DNS+its chosen shop path. Database existing ingress restrictions preserved. |

M9 will restrict WordPress ingress to Traefik and, locally, the exact Woo MCP Pod selector; existing M2 setup flows use `kubectl exec`/database access and their compatibility must be checked before changing this shared policy. This prevents arbitrary Pods spoofing proxy headers at WordPress. Production WordPress trusts the known Traefik TLS-termination path, not an Internet client's supplied HTTPS indicator. The operator must verify Traefik overwrites forwarded scheme/Host correctly and is not configured to trust arbitrary forwarded headers. Keep final backend proxy-header processing disabled; M10 uses the configured exact HTTPS origin/Host for cookie, CSRF and MCP checks rather than trusting arbitrary `X-Forwarded-*` values.

### 8.5 Production Woo transport: a decision to approve

**Recommended:** `canonicalOrigin` and `transportOrigin` both equal `https://shop.example.com`. Woo's outgoing TLS connection keeps that hostname for certificate verification and SNI; the HTTP Host and OAuth-signed origin are the same hostname and scheme. Operator-supplied `hostAliases` resolves the name to the actual Traefik ClusterIP, so the request stays on the internal ingress path rather than depending on public-IP hairpin routing. Query the Service IP at installation and after Service recreation; a changed IP requires a reviewed values update/restart.

Traefik terminates real TLS and passes to WordPress80 with its verified forwarded HTTPS indicator. WordPress's existing Docker-generated config must recognize that trusted proxy scheme; M9 documents/inspects the image configuration and fails deployment preflight if this compatibility has not been checked. Existing retained `wp-config.php` may differ, so image defaults alone do not prove the installed file. M10 must verify actual OAuth reads/writes through this path before declaring production readiness. Direct HTTP with an HTTPS canonical signature, fake forwarded headers from the connector, certificate-verification bypass and changing OAuth to Basic auth are excluded.

This leaves the short Traefik-to-WordPress hop unencrypted inside the cluster. NetworkPolicy limits callers, but does not encrypt packets. Full TLS to WordPress would require an additional reviewed component/configuration and is outside this minimum design. Local shop remains `http://shop.urumi.test` with internal HTTP transport and OAuth1.0a, preserving tested M3 behavior. Production TLS certificate is provided through `store.ingress.tlsSecret`; trust uses the image's system public CA bundle, with no private CA mount or `verify=False` addition.

Read-only inspection of the current local controller on 18 October found Service443 -> named target `websecure`, Pod8443, Traefik namespace `kube-system` and labels `name=traefik`, `instance=traefik-kube-system`. These are evidence for local starting values, not assumptions about a future VPS. Its corresponding values and API endpoint input must be checked there.

### 8.6 Secret inventory and missing M10 runtime

| Secret / keys | Consumer and ownership |
|---|---|
| `store.secrets.database`: `database-password`, `root-password` | Existing WordPress/MariaDB mounted files; root value only MariaDB/operator. |
| `store.secrets.salts`: `AUTH_KEY`, `SECURE_AUTH_KEY`, `LOGGED_IN_KEY`, `NONCE_KEY`, `AUTH_SALT`, `SECURE_AUTH_SALT`, `LOGGED_IN_SALT`, `NONCE_SALT` | Existing WordPress read-only Secret volume. |
| `store.secrets.admin`: `username`, `email`, `password` | Existing `scripts/store/bootstrap.php` operator setup only, not frontend/backend deployment. |
| `woocommerceMcp.existingSecret`: `consumer-key`, `consumer-secret` | Woo MCP env only; gateway does not read these credentials. |
| `platformDb.existingSecret`: `password` | PostgreSQL and backend PGPASSWORD env references. |
| `backend.existingProviderSecret`: `api-key` | Backend GROQ_API_KEY env reference only. |
| Operator bootstrap Secret: `email`, `password` | M5 host operator helper reads in memory and deletes original Secret with UID guard. Backend has no permission to read it. |
| Dynamic `urumi-upstream-UUID`: `value` | M5 SecretStore creates immutable credentials in dedicated namespace, owns them with installation/server labels; PostgreSQL stores reference only. |
| TLS `kubernetes.io/tls`: `tls.crt`, `tls.key`; image pull `kubernetes.io/dockerconfigjson`: `.dockerconfigjson` | Ingress/controller and image-pull mechanisms, not app/browser config. |

M9 backend template is a contract for future `python -m backend.main`, never a call to `scripts.m5.harness`. M10 must provide that entry point and `backend/orchestrator.py`. Packaging proposes these exact environment inputs: existing `PGHOST`, `PGPORT=5432`, `PGUSER=urumi`, `PGDATABASE=urumi`, Secret-backed `PGPASSWORD`; `URUMI_ORIGIN`, `URUMI_ALLOWED_HOSTS` JSON, `URUMI_INTERNAL_URLS` JSON, `URUMI_SECRET_NAMESPACE`, `URUMI_LISTEN_HOST=0.0.0.0`, `URUMI_WORKERS=1`, `GROQ_MODEL`, Secret-backed `GROQ_API_KEY`. No M5 harness env name becomes a hidden final-runtime dependency.

M10 startup must preserve M5's transactionally locked forward migration -> exclusive database owner -> identity/registry/audit construction -> audit and credential-operation recovery -> built-in upstream reconciliation -> discovery loop -> HTTP serving. Readiness checks database and current exclusive owner, plus completion of startup/recovery; it does not require every upstream to be reachable. Ownership loss fences dispatch and triggers the existing supervised recovery/restart behavior. Bootstrap remains an explicit operator command; it is not an initContainer, automatic password reset, Helm hook or command embedded in deployment. Stop backend before standalone credential reconciliation so owners cannot compete. M9 documents these as unimplemented composition contracts, not runnable final commands.

### 8.7 Build/preflight and evidence commands

`scripts/build-images.ps1` accepts explicit `-Module Store|Woo|Inventory|Dashboard|Backend|All`, `-ImagePrefix`, `-Tag`, optional reviewed base-image inputs; runs from repository root, rejects unknown inputs/missing source, checks each external process exit code immediately and never applies/imports/pushes. `Backend` and `All` check for both M10 entry-point files before any build and fail `M10_BACKEND_ENTRYPOINT_MISSING`; they cannot silently build a harness. A named `checks` Dockerfile target preserves existing isolated image usage; default/release target checks final entry-point existence and uses `python -m backend.main`. Existing test chart commands retain their explicit harness commands. Update only existing M5/M6 build invocation sites and their runbook build instructions to pass `--target checks`; preserve old evidence and recorded historical commands. Static checks assert that these paths still select their intended harness and that the checks target does not require M10 files. No rebuild/deployment of old module checks is required in M9 unless a specific compatibility defect appears.

`scripts/m9/check-m9.py` renders/lints through an explicit `--helm` executable and runs structural checks without Kubernetes calls. `scripts/m9/preflight.py` has `--mode render` and `--mode deploy`. Render mode permits clearly marked examples but validates types, topology and security invariants. Deploy mode rejects `.example.com`, `replace-*`, unavailable M10 image/runtime, empty image digests/release provenance, unresolved API CIDRs, TLS/Secret/image-pull/storage inputs and unchecked Woo proxy assumptions. It accepts an operator-prepared **names/types/key-names-only** inventory JSON (never Secret values), including checked certificate host/trust, actual ingress endpoint/target and storage class. Metadata validation cannot prove credentials work; real readiness is M10. No script shells out to create/fetch/apply Secrets as part of this check.

Planned PowerShell checks, from repository root using an ordinary isolated Python environment with the documented pinned checker dependencies and Helm installed:

```powershell
python -m pytest tests/release -q
python scripts/m9/check-m9.py --helm helm --output docs/evidence/m9
python scripts/m9/preflight.py --mode render --values deploy/charts/urumi/values-local.yaml
python scripts/m9/preflight.py --mode render --values deploy/charts/urumi/values-prod.yaml
helm lint deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-local.yaml
helm template urumi deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-local.yaml
helm lint deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-prod.yaml
helm template urumi deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-prod.yaml
# Expected safe failure until M10 provides its two entry-point files:
./scripts/build-images.ps1 -Module Backend -ImagePrefix urumi -Tag review
```

Exact runner may use a passed Helm path when it is not on PATH; it records versions, argv, exits and sanitized artifacts. `tests/release/test_release.py` parses complete YAML documents, checks object references and selectors, and has fixtures for both profiles plus alternate release/namespace, bad replica/worker counts, harness collision, missing required workload, origin/host mismatch, insecure production transport, missing TLS reference, malformed image/Secret settings, stale policy selectors and deploy placeholders. `test_preflight.py` proves render/deploy distinction, names-only inventory checks and missing-entry-point failure. `test_docs.py` verifies required files, local relative links and declared commands/limitations. Tests do not claim live network enforcement or backup success.

| Acceptance ID | Concrete saved proof |
|---|---|
| M9-01 | `component-inventory.json`, including M7/M8/M10 gaps and each owner. |
| M9-02 | Local/prod render YAML, Helm lint output, command/version inventory. |
| M9-03 | Positive/negative validation case outcomes and safe rejection reasons. |
| M9-04 | Parsed workload/Service/probe/resource/configuration reference inventory. |
| M9-05 | Parsed three-PVC names/mounts/keep assertions and recovery-guide review. |
| M9-06 | Parsed route/label/policy/RBAC path inventory, alternate namespace fixture. |
| M9-07 | Names-only Secret inventory and sanitized source/handoff sentinel scan counts. |
| M9-08 | Existing standalone build evidence/source inventory, M8 image evidence if available, explicit combined-build rejection and dependency gap list. |
| M9-09 | Values difference table, example deploy-mode rejection, fixture successful preflight and Woo/TLS assumptions list. |
| M9-10 | Documentation/link checklist and shell/working-directory review. |
| M9-11 | Copied source-only staging render, no `.tools`/`.env`/private environment dependency; explicit external prerequisites. |
| M9-12 | Independent `acceptance-review.md` / `acceptance-results.json`, final report and zero-mutation scope statement. |

### 8.8 Recovery/runbook design and decisions to review

`docs/operations.md` separates commands that exist now from future M10 actions. Operator first confirms explicit context, namespace, release and intended revision. Backups require a controlled maintenance window: stop new tool/write/chat/checkout traffic, drain or stop backend, make custom-format PostgreSQL dump and consistent transactional MariaDB dump, archive WordPress content and privately preserve corresponding static/dynamic Secrets/configuration. Store everything outside repository/handoff, encrypted/off-machine with restricted permissions and recorded time/schema/chart/image versions. PowerShell uses binary-safe subprocess/file transfer; never `>` for binary dumps. Shared evidence records only filenames/status/checksums where safe, never contents.

Restore first into an isolated namespace/storage target with a different dedicated Secret namespace and no public ingress. Restore matching database dumps/content/credential references; preserve installation-ID/Secret ownership consistency. Check versions/migrations, data counts, file permissions and scoped test operations before a separately approved cutover. An isolated restore rehearsal is M10 work, not an M9 test. No generic restore command is instructed against the retained `urumi` installation.

Before upgrade, retain chart/values/image digests, completed backup and reviewed migration compatibility; inspect `helm history` and the chosen revision. Run forward migrations only through the one backend owner's startup contract. Roll back Helm only to an explicitly selected compatible chart/image revision; it cannot undo schema changes, data writes, credential deletion or disk deletion. An incompatible schema requires a separately reviewed restore/forward repair procedure. Retained PVC/Secret namespace means uninstall is not a data reset; StorageClass reclaim and ownership conflicts are explained before any deletion.

**Please review these concrete choices:** trusted local dashboard TLS; the production Woo TLS-through-Traefik path with internal plaintext final hop and explicit hostname-to-Service-IP mapping; one backend owner/Recreate downtime during upgrade; manually provisioned Secrets/certificates; strict distinction between renderable examples and deployment-ready inputs. No hosting purchase, extra platform, certificate bypass or speculative scaling is proposed. Following your design approval, implement only this packaging/docs scope and report the twelve checks before M10.

## 9. Implementation and evidence - 19 October 2026

Approved section8 is implemented. The [report](../evidence/m9/report.md) records 60 passing release tests, seven passing existing store compatibility checks, both full-profile lint/renders, parsed policy/RBAC/storage references, actual fail-closed backend build rejection, 35 prior runtime-source matches and a private-sentinel/source-only staging check. The [runbook](../evidence/m9/runbook.md) names exact commands and boundaries. No M9 cluster/provider call or combined deployment occurred.

Compatibility detail: full local/production profiles now enable the release as designed. Existing M1/M2 runners instead load preserved original `values-module-local.yaml` / `values-module-prod.yaml` opt-in profiles, so running an old module check cannot accidentally enable final workloads. Five touched PowerShell files parse cleanly. M5/M6 runbooks explicitly select the Docker `checks` target. Existing raw historical evidence remains intact.

The static runner preserves its historical M9-12 independent-review-pending result. The separate independent [review](../evidence/m9/acceptance-review.md) and [acceptance results](../evidence/m9/acceptance-results.json) now record all 12 static package criteria PASS; user module acceptance remains pending. M7 real-provider evidence, M8 acceptance and M10 combined-runtime/live installation/two-user proof remain explicit external gates. Neither these test results nor production-shaped values claim a working VPS or complete system.
