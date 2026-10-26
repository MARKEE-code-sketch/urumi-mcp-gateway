<div align="center">

# Urumi

### One workspace. One MCP endpoint. Your team's tools.

A Kubernetes-native commerce workspace that connects WooCommerce, warehouse inventory and documentation tools through a shared, auditable MCP gateway.

![MCP: Streamable HTTP](https://img.shields.io/badge/MCP-Streamable_HTTP-147d69?style=flat-square) ![Deployment: Kubernetes and Helm](https://img.shields.io/badge/Deployment-Kubernetes_%2B_Helm-326ce5?style=flat-square) ![Frontend: React and TypeScript](https://img.shields.io/badge/Frontend-React_%2B_TypeScript-087ea4?style=flat-square) ![Backend: Python and FastAPI](https://img.shields.io/badge/Backend-Python_%2B_FastAPI-009688?style=flat-square)

[Architecture](#architecture) · [Run locally](#local-development) · [Connect a client](#connect-an-mcp-client) · [Deploy to a VPS](#vps-deployment)

</div>

---

## Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Components and stack](#components-and-stack)
- [Local development](#local-development)
- [Using the workspace](#using-the-workspace)
- [Connect an MCP client](#connect-an-mcp-client)
- [VPS deployment](#vps-deployment)
- [Security and trust](#security-and-trust)
- [Operations](#operations)
- [Testing](#testing)
- [Source layout](#source-layout)
- [Current boundaries](#current-boundaries)

## Overview

Urumi brings a real storefront and a team's AI tools into one workspace. An administrator connects upstream MCP servers once. Team members use those tools from dashboard chat or their own MCP client, with individual identity and API keys.

| | Capability |
|---|---|
| 🛍️ **Commerce** | Browse products, use the cart, check out and manage orders in WordPress/WooCommerce. |
| 🔌 **Shared gateway** | Discover and call tools from multiple Streamable HTTP MCP servers through one endpoint. |
| 💬 **Tool-assisted chat** | Ask questions or perform supported actions as the signed-in user, with visible tool activity. |
| 👥 **Team workspace** | Admin/member roles, invitation links, personal keys and individual key revocation. |
| 🧾 **Audit trail** | Attribute tool attempts to a user, server and tool, with timestamps, duration and outcome. |
| 🛡️ **Credential separation** | Keep store, upstream and model-provider credentials on the server side. |
| ☸️ **Portable deployment** | Run locally on Kubernetes and configure the same Helm chart for a k3s VPS. |

**Repository scope:** this public repository publishes the product README and architecture assets. Runtime source is maintained separately. Deployment commands and source paths below refer to the complete application source checkout; cloning this documentation repository alone does not install the application.

## Architecture

<p align="center">
  <img src="docs/architecture/urumi-platform.svg" alt="Urumi architecture: browser and MCP clients enter through Traefik; the gateway routes authenticated tool calls to internal commerce and inventory services or external documentation services, with persistent databases and server-side credentials." width="1500">
</p>

[Open the full-size diagram](docs/architecture/urumi-platform.svg) · [PNG version](docs/architecture/urumi-platform.png)

### The request path

1. **Enter the workspace.** A browser uses a secure session; an external MCP client uses a personal bearer API key.
2. **Discover shared tools.** The backend connects to enabled upstreams as an MCP client and exposes their tools as an MCP server.
3. **Choose an action.** A client calls a tool directly, or the chat model proposes a tool and arguments.
4. **Authorize and record.** The gateway rechecks the caller, validates the request and starts a durable audit attempt before dispatch.
5. **Route once.** The gateway calls the upstream using its stored credentials. WooCommerce MCP translates tools into signed WooCommerce REST API requests.
6. **Return an observed result.** The gateway finalizes the audit outcome. Chat uses results to produce an answer while displaying attempted tools.

### What runs where

There are **seven Kubernetes workloads**: dashboard, backend, WooCommerce MCP, Inventory MCP, WordPress/WooCommerce, MariaDB and PostgreSQL. Services provide internal addresses; Traefik Ingress exposes browser routes and the gateway endpoint.

Microsoft Learn, optional Context7 and Groq are **external services**. The application runs on Kubernetes, but it is not an offline system and does not host those providers.

| Public route | Destination |
|---|---|
| `https://DASHBOARD_HOST/` | React dashboard |
| `https://DASHBOARD_HOST/api/v1/` | Browser-facing backend API |
| `https://DASHBOARD_HOST/mcp` | Streamable HTTP gateway |
| `SHOP_ORIGIN/` | WooCommerce storefront |
| `SHOP_ORIGIN/wp-admin/` | WordPress/WooCommerce administration |

WooCommerce MCP, Inventory MCP, databases and backend health endpoints have no public Ingress route. NetworkPolicies further restrict internal callers.

## Components and stack

| Component | Technology | Responsibility |
|---|---|---|
| 🖥️ Dashboard | React, TypeScript, Vite | Servers, members, keys, audits and Markdown chat responses. |
| 🧠 Backend/chat | Python 3.13, FastAPI, MCP Python SDK | Session APIs, identity, registry, routing and bounded tool execution. |
| 🔌 MCP gateway | Streamable HTTP | Tool aggregation, validation, routing, failure isolation and attribution. |
| 🛍️ WooCommerce MCP | Custom Python adapter | Product/order tools backed by the WooCommerce REST API. |
| 📦 Inventory MCP | Python, fixed JSON fixtures | Cross-server warehouse lookups by SKU. |
| 📚 Documentation MCPs | Microsoft Learn; optional Context7 | External documentation search/retrieval through the gateway. |
| 💬 Model provider | Groq, `openai/gpt-oss-20b` | Select tools and generate answers from observed results. |
| 🏪 Store | WordPress, WooCommerce, MariaDB | Storefront, checkout, products, orders and shop administration. |
| 🗄️ Platform database | PostgreSQL | Users, sessions, hashed API keys, registry metadata and audits. |
| ☸️ Deployment | Docker, k3d/k3s, Helm, Traefik | Images, workloads, routing, configuration and persistent storage. |

### Included integrations

- **WooCommerce** is registered during backend initialization, without overwriting later administrator edits.
- **Inventory** and **Microsoft Learn** are the baseline additional integrations; an administrator or operator registers them.
- **Context7** is an additional administrator-configured integration, not an automatically installed or registered service.

### WooCommerce tools

| Gateway tool | Action |
|---|---|
| `woocommerce__list_products` | List products and prices/SKUs. |
| `woocommerce__create_product` | Create a product with validated inputs. |
| `woocommerce__list_orders` | List orders with supported filters and pagination. |
| `woocommerce__get_order` | Read an order by ID. |
| `woocommerce__update_order_status` | Update an existing order's status. |

Aliases follow **`server_slug__tool_name`**, preventing collisions between tools from different servers. Examples assume the integration slug is `woocommerce`.

`inventory__lookup_sku` accepts **one SKU per call**. A missing entry means **not tracked / stock unknown**, not zero stock. Inventory is sample warehouse data, independent of WooCommerce stock; a storefront purchase does not decrement it.

## Local development

### Prerequisites

Use a complete application source checkout and install:

- Docker Desktop with Linux containers, or a compatible Docker engine.
- Python **3.13** and Node.js **24** with npm (matching the frontend build image).
- `kubectl`, **Helm 3** and **k3d**.
- A working local StorageClass and a NetworkPolicy-capable cluster.
- A Groq key for chat and credentials for authenticated upstreams.
- Trusted local HTTPS for the dashboard; its session cookies require it.

Commands below use **PowerShell**, from the source checkout root. Use `npm.cmd` on Windows if execution policy blocks `npm.ps1`.

### 1. Prepare the environment

```powershell
python -m venv .tools/dev-venv
./.tools/dev-venv/Scripts/python.exe -m pip install -r scripts/m10/requirements.txt
npm.cmd --prefix frontend ci
```

Use the pinned environment for checks. The backend pins MCP SDK **1.26.0**; an unrelated environment with a newer major SDK may not run its acceptance helpers.

### 2. Create or resume the cluster

For a **fresh** machine with no existing `urumi` cluster:

```powershell
k3d cluster create --config infra/local/k3d.yaml --kubeconfig-update-default=false --kubeconfig-switch-context=false
New-Item -ItemType Directory -Force .tools/m1 | Out-Null
k3d kubeconfig get urumi | Set-Content -Encoding utf8 .tools/m1/kubeconfig.yaml
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi get nodes
```

If it already exists, resume it instead:

```powershell
k3d cluster start urumi
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi get nodes
```

The cluster configuration maps HTTP/HTTPS to Traefik. Do not overwrite an existing kubeconfig or delete cluster storage as an installation retry.

### 3. Configure domains, trust and private inputs

Map your local hostnames to the Ingress address. For loopback port mappings:

```text
127.0.0.1 dashboard.urumi.test shop.urumi.test
```

Supply a valid dashboard certificate and trust its CA in the clients that use it. Python and Node may need separate CA configuration. Do not disable TLS verification.

The local storefront profile uses `http://shop.urumi.test`, with signed Woo REST requests internally. Production uses HTTPS with matching canonical hostname, TLS and signature settings. Local HTTP is for fictional test data only.

Create an application namespace and a **separate, unique upstream-Secret namespace**. Provision credentials privately before installation:

| Secret | Expected keys | Consumer |
|---|---|---|
| `urumi-store-db` | `database-password`, `root-password` | WordPress/MariaDB |
| `urumi-store-salts` | WordPress authentication keys/salts | WordPress |
| `urumi-store-admin` | `username`, `email`, `password` | Operator store bootstrap |
| `urumi-woocommerce-rest` | `consumer-key`, `consumer-secret` | Woo MCP only |
| `urumi-platform-db` | `password` | PostgreSQL/backend |
| `urumi-groq` | `api-key` | Backend only |
| `urumi-dashboard-tls` | `tls.crt`, `tls.key` | Dashboard Ingress |

Names are configurable. The chart references existing Secrets; it does not generate credentials or issue WooCommerce REST keys. Credentials later added through the dashboard become owned Secrets in the dedicated namespace.

Keep operator values outside version control. Supply selected domains, Secret references, storage, exact Kubernetes API endpoint CIDRs, image digests and provenance. A separate **metadata-only** inventory records verified Secret names/types/key names, TLS trust, Ingress/storage details and image verification. Neither input should contain exported Secret payloads.

### 4. Build and import images

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/build-images.ps1 -Module All -ImagePrefix urumi -Tag local
k3d image import urumi/store:local urumi/woocommerce-mcp:local urumi/inventory-mcp:local urumi/dashboard:local urumi/backend:local --cluster urumi
```

This builds five application images; MariaDB/PostgreSQL use configured upstream images. Set the matching Helm repositories/tags/digests and verify actual container-runtime identities. The build script does not install, provision credentials or push images.

### 5. Validate and install

Complete operator provisioning/image verification first. Replace the example private paths with your inputs. Use a new installation namespace rather than applying a fresh profile over a retained store.

```powershell
./.tools/dev-venv/Scripts/python.exe scripts/m9/preflight.py --mode deploy --values .tools/operator/merged-values.yaml --inventory .tools/operator/inventory.json --namespace urumi

helm lint deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-local.yaml -f .tools/operator/values.yaml

helm upgrade --install urumi deploy/charts/urumi --kube-context k3d-urumi --kubeconfig .tools/m1/kubeconfig.yaml --namespace urumi -f deploy/charts/urumi/values-local.yaml -f .tools/operator/values.yaml --wait --timeout 5m

kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi get pods,services,ingress,pvc
```

Preflight requires merged effective values and a verified metadata inventory; it is not provisioning or a runtime test. Use consistent overrides for rendering, preflight and installation.

### 6. Initialize the store and first administrator

Initialize WordPress/WooCommerce, enable a test checkout method, establish the integration user/REST key and bootstrap the gateway administrator. This is explicit operator provisioning, not public signup.

The source includes `scripts/store-setup.ps1`, scoped store bootstrap helpers and `scripts/m5/operator.py`. Inspect their target namespace/context first: some helpers deliberately target a retained development store. Do not copy their defaults into another installation.

Gateway bootstrap uses a temporary Secret with `email` and `password`, with database settings loaded privately into the operator process:

```powershell
./.tools/dev-venv/Scripts/python.exe -m scripts.m5.operator bootstrap --secret YOUR_BOOTSTRAP_SECRET --namespace urumi --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi
```

The helper removes that specific Secret after creating the administrator. Store and gateway admin accounts are separate. After bootstrap, open the dashboard, register additional integrations and invite a second user.

## Using the workspace

### 🛍️ Place a test order

1. Open the storefront and select a published product.
2. Add it to the cart; use fictional customer data at checkout.
3. Choose Cash on Delivery or a deliberately configured test payment method.
4. Note the order ID and verify it under **WooCommerce → Orders** in `/wp-admin/`.
5. Ask gateway chat about that order or today's orders.

The storefront/admin use WordPress/WooCommerce. The team gateway is separate, with its own login. Coordinated teal/mint styling connects the interfaces visually.

### 👥 Connect the team

| Action | Admin | Member |
|---|---|---|
| Use enabled shared tools and chat | Yes | Yes |
| Create/revoke own personal API keys | Yes | Yes |
| Inspect own tool activity | Yes | Yes |
| Manage upstream servers | Yes | No |
| Invite/manage members and administer others' keys | Yes | No |
| Inspect team-wide audit activity | Yes | No |

Members can use enabled shared tools, including product/order mutations. They are **not** automatically read-only store users. Per-tool permission policies are not implemented.

Under **Servers**, enter a name, unique slug, Streamable HTTP URL and optional static bearer/header credential. Inspect tools and status: **Connected**, **Unreachable** or **Disabled**. Disable hides its tools; remove deletes the registration. Discovery updates status; refreshing the server list alone reads recorded state.

### 💬 Ask the chat agent

Start with small, verifiable tasks:

```text
List our WooCommerce products with their IDs, SKUs and INR prices.
```

```text
Create a published WooCommerce product named "Demo Notebook" with price "129.00" INR and a unique SKU "DEMO-NOTEBOOK-01".
```

```text
Show me today's WooCommerce orders.
```

```text
Find SKU DEMO-001 in WooCommerce, tell me its price, and check its warehouse availability using Inventory.
```

```text
Use Microsoft Learn documentation search to explain Kubernetes Pods in three short bullets and include a source link.
```

Use disposable products and fresh SKUs for writes. Verify a write in the shop before repeating it. Chat shows terminal state, tool outcomes, request ID and audit references; tool success alone does not prove the model delivered a complete answer.

Each message is independent. A browser visit retains up to ten replies; conversations are not saved. Today's orders use one captured **Asia/Kolkata** window and consistent pagination. Provider quotas can interrupt multi-step answers after successful tool calls. Large documentation searches may use disclosed excerpts with intact source URLs.

## Connect an MCP client

Create a personal key under **Keys** and save it when issued. The gateway stores its hash, not a recoverable full key.

| Setting | Value |
|---|---|
| Transport | **Streamable HTTP** |
| Server URL | `https://DASHBOARD_HOST/mcp` |
| Header | `Authorization: Bearer YOUR_PERSONAL_API_KEY` |

Replace `DASHBOARD_HOST`. Configure a supporting MCP client, such as MCP Inspector or an appropriately configured coding client. Client formats differ; the URL/header above are the connection contract.

No WooCommerce, Inventory, Learn, Context7 or Groq credentials belong in that client. The gateway supplies upstream credentials internally. `/mcp` is a protocol endpoint, not a browser login page; an unauthenticated request should be rejected.

List tools, make a read-only call and inspect its audit record. Revoke the disposable key: its next request should be denied. Revoking one API key does not revoke that user's separate dashboard session.

## VPS deployment

Use the **same** `deploy/charts/urumi` chart with `values-prod.yaml` and private overrides. No alternate templates or Kustomize deployment are needed.

| Setting | Local | VPS / k3s |
|---|---|---|
| Domains | `.urumi.test` hosts entries | Real DNS pointing to the VPS |
| Ingress | k3d Traefik | Verified k3s Traefik/configured equivalent |
| TLS | Trusted local dashboard certificate | Trusted dashboard and shop certificates |
| Images | Built/imported locally | Registry images, immutable digests, pull credentials |
| Storage | Development StorageClass | Verified class/capacity and backup strategy |
| Credentials | Private local Secrets | Separately provisioned production Secrets |
| API access | Observed local endpoint CIDRs | Observed VPS endpoint CIDRs/port |
| Woo REST | Signed local HTTP to internal WordPress | Signed HTTPS through verified shop Ingress |

Provision k3s, DNS, storage, TLS, registry access and Secrets first. Replace `.example.com`, documentation IPs and image placeholders. Verify production Woo's canonical origin/Host/SNI, Traefik Service IP and trusted forwarded-scheme handling in persisted WordPress configuration.

Example **Linux shell**, from the full source checkout after provisioning and deploy preflight:

```bash
context="YOUR_K3S_CONTEXT"
namespace="urumi"
release="urumi"

helm lint deploy/charts/urumi --namespace "$namespace" \
  -f deploy/charts/urumi/values-prod.yaml \
  -f /etc/urumi/operator-values.yaml

helm upgrade --install "$release" deploy/charts/urumi \
  --kube-context "$context" --namespace "$namespace" \
  -f deploy/charts/urumi/values-prod.yaml \
  -f /etc/urumi/operator-values.yaml \
  --wait --timeout 5m

kubectl --context "$context" -n "$namespace" get pods,services,ingress,pvc
```

The production profile is statically validated; a live VPS deployment has **not** been demonstrated. Helm rendering alone does not prove DNS, TLS, network enforcement, storage durability or checkout. Repeat real user flows before serving real users.

## Security and trust

### Three credential boundaries

| Boundary | Authentication | Handling |
|---|---|---|
| Browser → dashboard API | Secure cookie, Origin and CSRF checks | Session belongs to the signed-in user. |
| External client → gateway | Personal bearer API key | Hashed, individually revocable, rechecked on requests. |
| Gateway → upstream | Static bearer/header or no credential | Server-side Kubernetes Secrets; never returned to clients. |

Woo MCP separately uses OAuth 1.0a signing for the Woo REST API. This is not gateway OAuth login. Client bearer keys are never forwarded as upstream credentials.

### Enforcement and remaining risks

- **Authorization:** identity, server state and routing version are rechecked before dispatch. Members cannot administer servers or another member's keys.
- **Audit:** attempts start before dispatch and finalize with observed outcomes. Denied/uncertain calls are distinct from success.
- **Isolation:** internal Services, scoped NetworkPolicies and namespace-scoped Secret RBAC limit access. Databases and Woo MCP are not public endpoints.
- **SSRF:** URL rules, checked DNS answers, preserved TLS hostname checks, bounded responses and no automatic redirects protect connections. Internal integrations use operator-controlled allowlists.
- **Prompt injection:** descriptions, results and model arguments are untrusted. Backend validation/gateway authorization remain the execution boundary.
- **Shared authority:** members can invoke authorized tools with the shared integration's authority without seeing its credential. Hiding a credential does not make an allowed write harmless.
- **Secret storage:** Kubernetes Secrets are not inherently encrypted at rest. Operators supply disk/etcd encryption and access controls where required.
- **Runtime:** Python services/dashboard use non-root security settings, dropped capabilities and read-only root filesystems where configured. Databases/WordPress retain required writable paths.

Keep keys, `.env`, kubeconfigs, TLS private keys, operator values, dumps, customer data and raw provider payloads out of version control. Use fictional checkout data locally.

## Operations

### Storage and recovery

Three PVCs hold **MariaDB data**, **WordPress content** and **PostgreSQL data**. Pod replacement preserves them. Retention is not backup; local-path storage remains a single-machine failure domain.

Back up both databases, WordPress files and matching configuration/credentials as one coordinated recovery point. Keep encrypted backups off-machine. Rehearse recovery in isolation before cutover; database credential references and the dedicated Secret namespace must remain consistent.

### Upgrades and rollback

1. Record release/chart, image digests, schema and private effective values.
2. Back up and review migration compatibility.
3. Preflight and inspect a render with the same chart/selected values.
4. Upgrade, wait for probes, then verify checkout, a tool call and its audit.
5. Roll back only to an image/chart compatible with current schema/files.

```powershell
helm history urumi --kube-context k3d-urumi --namespace urumi
helm rollback urumi REVIEWED_REVISION --kube-context k3d-urumi --namespace urumi --wait --timeout 5m
```

Rollback is an operator action after compatibility review. Helm cannot undo database writes, migrations, deleted credentials or disk deletion. The backend uses one replica/worker and **Recreate** updates with exclusive database ownership; upgrades can briefly interrupt service.

### Troubleshooting

| Symptom | Inspect |
|---|---|
| Dashboard/API unavailable | Backend readiness, database access, startup recovery; inspect state before retrying mutations. |
| Upstream Unreachable | URL/auth mode, DNS/TLS, egress, upstream availability and recorded reason. Discovery is bounded. |
| Registration fails after Docker/k3d restart | Compare actual API endpoint with `backend.networkPolicy.apiServerCidrs`; update only verified CIDRs through Helm. |
| Chat fails after successful tools | Tool activity/audit IDs, then provider availability/quota; retries cannot increase quota. |
| SKU not found | Treat as untracked/unknown, not zero stock or a Woo stock state. |
| One upstream fails | Independently verify calls/audits from a healthy peer. |
| PVC Pending | StorageClass, capacity, permissions and events; preserve retained data. |
| Write times out | Check Audit and remote shop before repeating; effects may already exist. |

Tool dispatches are not automatically replayed. Chat permits bounded provider-completion retries after tool activity, with identity revalidation and the original deadline; it does not replay successful tools.

## Testing

Checks are separated by component. These commands use the pinned environment and do not alone prove a live deployment.

```powershell
# Gateway, chat safety and runtime composition: controlled/local checks.
./.tools/dev-venv/Scripts/python.exe -m pytest tests/gateway tests/chat tests/e2e/test_runtime.py -q

# Helm/release packaging.
./.tools/dev-venv/Scripts/python.exe -m pytest tests/release -q
helm lint deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-local.yaml
helm template urumi deploy/charts/urumi --namespace urumi -f deploy/charts/urumi/values-local.yaml

# Dashboard checks.
npm.cmd --prefix frontend run test -- --run
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run build
```

Integration checks require a deliberately selected environment. Use disposable databases for migrations; never point historical reset helpers at retained data.

A meaningful running-system check:

1. Complete checkout and verify the same order in shop administration.
2. As one user, create a disposable product through chat and verify it; place an order and query today's orders.
3. As a second user, connect using only their key/gateway URL; read orders and combine WooCommerce with Inventory.
4. Revoke a disposable key and verify its next call is denied.
5. Disable an upstream and verify its tools disappear.
6. Replace an owned upstream Pod; if needed use a controlled sustained outage. Observe Unreachable, check a healthy peer and restore original replicas.
7. Match calls to attributed audits and check persistence after a scoped restart.

Local browser/MCP, revocation, failure-isolation and persistence checks have been exercised. Provider-dependent chat remains subject to rate limits and model decisions; one successful run is not a reliability guarantee. Fault/write tests need an explicit target and restoration plan.

## Source layout

Logical layout of the complete runtime source tree:

```text
backend/
  orchestrator.py          # Runtime composition, startup/shutdown
  identity/               # Sessions, members, personal keys
  registry/               # Upstream registration and Secret references
  gateway/                # Discovery, routing, MCP endpoint
  audit/                  # Durable attempt records/outcomes
  chat/                   # Provider client and bounded tool loop
  db/                     # PostgreSQL access/migrations
frontend/                 # React dashboard
services/
  woocommerce_mcp/         # First-party Woo REST adapter
  sample_mcps/             # Inventory service and fixed fixtures
build/store/              # Store image definition
contracts/                # Shared tool/data contracts
deploy/charts/urumi/       # Helm templates/local-production values
  files/store-theme/      # First-party storefront/admin theme
infra/local/              # Local cluster configuration
scripts/                  # Build/bootstrap/preflight/scoped checks
tests/                    # Component/integration/release checks
docs/                     # Architecture/operations/design records
```

## Current boundaries

- One store/one gateway owner; multi-store provisioning and horizontal gateway scaling are not implemented.
- No gateway OAuth login, granular per-tool permissions or automatic cert-manager provisioning.
- Inventory is a reproducible sample with per-SKU lookups, not a production warehouse integration.
- Groq/hosted documentation are external dependencies; availability/quota can interrupt chat.
- Check model answers against tool activity. Completed does not prove every requested SKU was checked.
- Helm supports production-shaped configuration; live VPS operation, high availability and off-machine disaster recovery are not claimed.

---

<div align="center">

**Shared tools. Individual identity. Inspectable activity.**

</div>
