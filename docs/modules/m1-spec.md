# M1 specification — Kubernetes playground

**Status:** Specification and recommended choices approved by user on 14 October 2026; detailed design requested. Implementation subsequently approved; completed with all nine checks passing; user module acceptance pending.  
**Date:** 14 October 2026.  
**Sources:** Assignment DOCX, [blueprint M1](../../blueprint.md#m1-kubernetes-foundation), [project decisions](../decisions.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Prepare a small Kubernetes environment on your laptop and run a temporary test page in it.

**WHY:** Before putting the real shop here, we need to know three things: can we open it, can it save files, and can it block unwanted connections?

**HOW:** Docker Desktop runs our k3d cluster. Helm installs a temporary page and the rules around it. We open the page, replace its running container, and check that its saved file remains. We then prove one test caller is allowed and another is blocked.

**What you will see at the end:** A page in your browser and saved evidence that networking, storage, and access rules work. This is preparation for M2, where we install the actual shop.

## 2. The few words you need now

| Word | Think of it as |
|---|---|
| k3d / k3s | k3d creates our local environment inside Docker; k3s is the Kubernetes distribution running there. |
| Node / cluster | A node is a machine Kubernetes uses; the cluster is the whole environment. One local node is proposed. |
| Pod / Deployment | A Pod runs the container. A Deployment keeps the requested number of Pods running and replaces a deleted one. |
| Service | A stable address for the page, even after its Pod changes. |
| Ingress / Traefik | Ingress is the routing rule; Traefik is the software that reads the rule and directs incoming web traffic. |
| PVC | A request for saved disk space, similar to a Docker volume. |
| NetworkPolicy | A rule saying which Pods may connect to which other Pods. It must be tested to prove it is enforced. |
| Helm chart / values | The installation recipe / its settings. We keep one recipe and change settings for local or VPS use. |
| Readiness / liveness probe | Readiness asks “can it receive traffic?” Liveness asks “is it healthy, or should Kubernetes restart it?” |
| Resource settings | The container’s requested and maximum CPU and memory. |

## 3. One request, in order

~~~text
Your browser
     |
     v
Laptop's local web port
     |
     v
Traefik reads the Ingress rule
     |
     v
Service: stable internal address
     |
     v
Temporary page Pod
     |
     v
PVC: saved test file
~~~

Inside Kubernetes, a permitted test Pod also reaches the page through its Service name. A second test Pod must be blocked. These Pods stand in for a future allowed gateway and an unrelated application; they are not the real gateway.

## 4. Scope and assignment connection

| M1 must provide | Why it belongs here |
|---|---|
| A working local k3d cluster | Assignment requires local Kubernetes; k3d is your confirmed choice. |
| A minimal Helm chart | Helm is mandatory. Later modules add their own templates to this chart. |
| Working hostname and Ingress route | Assignment requires stable URLs; M1 proves the foundation using a temporary page. |
| Internal Service-name lookup | Later containers must find each other without hardcoded Pod addresses. |
| Saved storage across Pod replacement | Prepares for mandatory persistent shop data; M2 separately proves real database and uploads survive. |
| Readiness, liveness, requests, limits | Required for every project workload, including our temporary test workload. |
| Tested allow/deny network rule | Prepares for the mandatory gateway-only WooCommerce MCP boundary. Broad security hardening remains optional. |
| Local/VPS settings boundary | Same application chart must support both environments; complete packaging and VPS instructions belong to M9. |

**Not included:** WordPress, WooCommerce, MariaDB, PostgreSQL, accounts, gateway, AI chat, MCP clients, a purchased VPS, TLS, or multi-store provisioning. No real modules are wired together in M1.

## 5. Design choices — recommendations approved

Existing choices remain Python/FastAPI, k3d, and Helm. You approved the following M1 recommendations; the detailed design records implementation settings:

| Choice | Recommendation and reason | Alternative / tradeoff |
|---|---|---|
| Local cluster size | One k3s server node; simplest and lighter on the laptop. | Multiple nodes teach scheduling but consume more memory; unnecessary for this assignment's core. |
| Incoming web traffic | Use bundled Traefik with Ingress. | A separate controller adds installation work. Port-forward alone does not prove the required Ingress path. |
| Local URLs | Keep shop.urumi.test and dashboard.urumi.test; use foundation.urumi.test for this temporary page. Map selected names to 127.0.0.1. | Automatic loopback DNS avoids a hosts-file edit but relies on external DNS behavior. |
| Laptop port | Prefer loopback port 80 if free; check first. If occupied, propose 8080 and show the port in every local URL. | Do not stop existing software to free a port. A changed port needs a consistent update to documented URLs. |
| Local saved disk | Use the k3s local-path storage provisioner and a small test PVC. | A network storage system adds work. Local storage proves Pod replacement, not backups or survival after cluster deletion. |
| Helm foundation | Start the shared chart with application components disabled; opt into a temporary foundation test workload. | A second application chart would duplicate settings and make the later same-chart story harder. |

**No administrator changes are automatic:** if Windows needs an elevated hosts-file edit, provide exact instructions for you to run. Do not change Docker settings, firewall rules, or permissions silently.

Exact k3d, k3s, Helm, and test-image versions will be selected and pinned during design after checking compatibility and what is installed. No latest-only image tags in the saved reproducible setup.

## 6. Requirements and measurable acceptance

All rows below are planned checks. None is currently marked PASS.

| ID | Required result | Evidence to save |
|---|---|---|
| M1-01 | Docker is accessible; required CLIs run; cluster nodes become Ready. Record available CPU/memory, free ports, tool versions, and selected context. | preflight.txt, cluster-status.txt |
| M1-02 | Helm lint and template succeed for local and production-shaped values using the same chart. Production render contains no local-only test workload. | helm-checks.txt, reviewed rendered YAML |
| M1-03 | Browser opens the temporary page using its documented local hostname through Ingress, returning the expected marker. | ingress-check.txt and browser screenshot |
| M1-04 | A test Pod resolves and reaches the page through its Service DNS name. | dns-check.txt |
| M1-05 | Write a unique marker to the PVC, delete only the page Pod, wait for a new Ready Pod, and read the same marker. Keep Pod IDs before and after. | storage-check.txt |
| M1-06 | Before policy enforcement both test callers can connect. After enforcement the permitted caller succeeds and the unrelated caller fails within a bounded timeout. A fresh permitted call still succeeds. | network-policy-check.txt |
| M1-07 | Page Deployment has both probes and explicit CPU/memory requests/limits. Observe Ready status and automatic replacement after deletion. | workload-settings.yaml, cluster-status.txt |
| M1-08 | No application test Service uses NodePort or LoadBalancer; only the test page has an Ingress. Record bundled Traefik’s infrastructure LoadBalancer Service separately. Public/internal routes are listed. | exposure-check.txt |
| M1-09 | Test resources can be removed without deleting the cluster or unrelated resources. Record PVC handling explicitly; preserve it unless its disposable deletion is approved. | cleanup-notes.md |

M1-06 must distinguish a network denial from a broken page or DNS: use a known-good destination, show the initial success, record the failed caller's exit/result, and repeat the allowed request. The policy must also preserve the Ingress and DNS paths needed by these checks. Scope test restrictions to labelled test resources; do not install blanket restrictions on future applications prematurely.

The test Pods/Jobs also receive explicit resources and appropriate health checks for their role. Short-lived verification Jobs use bounded completion/deadlines rather than meaningless HTTP probes. Inspect cluster-managed infrastructure separately and document any settings outside our application's chart.

## 7. Planned files and ownership

These are future implementation files, not created by this specification.

| Owner / files | Responsibility |
|---|---|
| M1: infra/local/k3d.yaml | Local cluster name, pinned k3s version, loopback port mappings. |
| M1: deploy/charts/urumi/Chart.yaml and templates/_helpers.tpl | Shared chart identity and common naming/labels. |
| M1 initial; M9 final: values.yaml, values-local.yaml, values-prod.yaml | Start with minimal safe settings; M9 completes full application values and validation. |
| M1: templates/foundation/ | Temporary page, Service, Ingress, PVC, config, and isolated policy checks; disabled by default. |
| M1: namespace/policy foundation templates | Establish agreed namespace ownership and test boundaries. Design must avoid conflicts with Helm release namespace creation. |
| M1: scripts/m1/ | Named PowerShell setup/check steps; bounded checks and explicit Kubernetes context. |
| M1: docs/local-cluster.md | Beginner setup, hostname instructions, expected output, stop/start and cleanup guidance. |
| M1: docs/evidence/m1/ | Exact commands, results, screenshots, version inventory, and remaining gaps. |

M5 owns Kubernetes API permissions for dynamic upstream Secrets. M2 owns actual shop disks. M9 completes production operations. M10 proves the real gateway-only network boundary and full user journey.

## 8. Work order and gates

| Step | What happens | Stop condition |
|---|---|---|
| 1. Specification review — now | Review this scope and the proposed choices. | User approves specification before detailed design. |
| 2. Design and review | Pin versions, define templates, selectors, policy paths, namespace ownership, storage behavior, probe/resource starting values, and commands. | Present design for user approval. |
| 3. Implement | Create only the approved M1 files and local foundation. | Review changes before acceptance checks. |
| 4. Check and explain | Run M1-01 to M1-09 and explain each observed result. | Record PASS/FAIL/BLOCKED with evidence; never infer cluster success from YAML alone. |
| 5. Module handoff | Show the page, explain the files and request path, summarize gaps. | User accepts M1 before M2 begins. |

Plan for one focused setup-and-check cycle. Downloads, machine permissions, and hardware may delay it. With the 20 October deadline, keep this module to the required foundation and postpone optional infrastructure.

## 9. Known gaps and recovery

- Docker Desktop was started by you, but the agent's previous Docker access check was denied. Verify current access before setup. If still blocked, provide short PowerShell commands for your terminal and inspect their saved output.
- The standard workspace command runner still fails before starting a shell. The alternate workspace tool works for documents; this does not prove it can control Docker.
- k3d and Helm were previously absent from PATH; current installation state needs checking. Explain any required installation before making machine changes.
- Free ports, available memory, and hostname privileges are unverified. Do not assume the laptop can run the full stack based on this small page.
- Local PVC survival after Pod replacement does not prove survival after deleting the node/cluster, disaster recovery, or multi-node storage.
- Inspector shutdown failure and live Codex interoperability remain deferred M0 gaps, to be checked against the real gateway in M10. They do not block writing this specification.

## 10. Review result and next action

**Specification verdict:** Approved by user after independent review found no blockers. Clarified probe meanings and distinguished application test Services from Traefik infrastructure. **Implementation:** completed and verified; all nine checks PASS, user module acceptance pending.

The user approved the recommendations and requested the [M1 design](m1-design.md). Implementation was subsequently approved; current results are in [M1 report](../evidence/m1/report.md). Approval of this specification does not automatically approve elevated host changes, full-blueprint implementation, or M2.

### Technical references

These explain implementation behavior; the DOCX remains the product specification.

- [k3d: expose services through Ingress](https://k3d.io/stable/usage/exposing_services/) — host port mapping to the cluster entry point.
- [k3s networking services](https://docs.k3s.io/networking/networking-services) — bundled DNS, Traefik, and NetworkPolicy controller; actual behavior still needs local checks.
- [k3s storage](https://docs.k3s.io/storage/) — local persistent storage; no assumption of high availability.
