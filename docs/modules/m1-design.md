# M1 design — our first Kubernetes environment

**Status:** Completed and verified: all nine M1 checks PASS; user module acceptance pending. See [results](../evidence/m1/report.md).  
**Date:** 14 October 2026.  
**Approved input:** [M1 specification](m1-spec.md). You approved the recommended choices and asked us to proceed with design.  
**Product authority:** Assignment DOCX. Technical references explain our choices; they do not add requirements.

## 1. The result, in plain language

**WHAT:** Run one temporary web page in Kubernetes, with a saved file and a connection rule.

**WHY:** Prove the environment is ready before M2 installs the shop.

**HOW:** Docker runs one Kubernetes node. Helm installs the page and its supporting resources. We open the page, replace its Pod, check its saved file, then test allowed and blocked callers.

Think of the **node as a hotel building** and **Pods as rooms inside it**. M1 needs one building and a few small rooms. The page is temporary; the cluster and shared Helm chart are foundations for later modules.

### The visible result

Open **http://foundation.urumi.test** and see **“Urumi M1 — Kubernetes is serving this page.”** If port 80 is occupied, use the approved fallback **http://foundation.urumi.test:8080** consistently.

## 2. What runs where

~~~text
Your browser
    |
    v
127.0.0.1:80 (or :8080)
    |
    v
k3d entry point → Traefik
    |
    v
Ingress: foundation.urumi.test
    |
    v
Service: urumi-foundation, port 80
    |
    v
Page Pod: Python HTTP server, port 8080
    |
    v
Saved file on a 1 GiB PVC
~~~

| Place | What it contains | Why |
|---|---|---|
| Docker Desktop | One k3s server container plus k3d helper containers | Runs the local node and its entry point. Helper containers are not extra Kubernetes nodes. |
| kube-system namespace | Bundled Traefik, DNS, and storage infrastructure | Provides routing, Service-name lookup, and disk provisioning. |
| urumi namespace | Temporary page and short-lived checking Jobs | Keeps our application resources together. A Job is a task that runs and finishes. |
| Later: upstream-credential namespace | Created by M5 when its reviewed Secret adapter needs it | No empty credential namespace or API permissions needed in M1. |

The page and checking Jobs get no Kubernetes API permissions and no mounted service-account token. M1 uses no .env content, LLM keys, or shop credentials.

## 3. Tool versions and the current machine

### Observed during this design

| Item | Observed result |
|---|---|
| Docker CLI | Installed, version 29.6.1. Engine access denied from the agent tool. |
| kubectl | Installed, v1.36.1. |
| k3d / Helm | Not found on the checked PATH. This does not prove they are absent everywhere. |
| Available memory | Windows inventory query denied. Capacity remains unverified. |
| Ports 80 / 8080 | No listener printed, but query errors were suppressed; availability is not proved. Check again before binding. |

Saved separately in [design preflight](../evidence/m1/design-preflight.md). These observations do not establish cluster readiness.

### Selected starting versions

| Component | Design pin | Verification still needed |
|---|---|---|
| k3d | v5.9.0 | Official release exists; install project-local Windows amd64 binary and verify its checksum/version. |
| k3s | v1.36.3+k3s1; image rancher/k3s:v1.36.3-k3s1 | Official release exists; verify image availability and successful startup. |
| kubectl | Existing v1.36.1 | Same Kubernetes minor as selected server; verify connection. |
| Helm | v3.21.3 | Official release exists; project-local verified archive; prove lint/render/install behavior. |
| Page and checking image | python:3.13.5-slim-bookworm | Verify registry tag, resolve its immutable digest, and save that digest before deployment. No image availability claim yet. |

These are explicit starting pins, not claims that this combination has been tested. If a pin cannot be downloaded or started, report the exact issue and revise the documented pin; do not silently switch to latest. Use portable binaries under ignored .tools/m1/; scripts use their explicit paths. This avoids a global installation or persistent PATH change. Existing Docker Desktop and kubectl remain the prerequisites.

## 4. Cluster and Helm layout

| Setting | Design |
|---|---|
| Cluster name / context | urumi / k3d-urumi. Every Kubernetes and Helm command specifies this context. |
| Nodes | One server, zero extra agents. The server also runs our workloads. |
| Cluster configuration | infra/local/k3d.yaml, k3d Simple configuration v1alpha5. |
| Web binding | Map 127.0.0.1:80 to port 80 on the k3d load balancer. Use 8080 only if 80 is unavailable; save the chosen configuration. |
| Kubernetes API binding | Loopback address; let k3d allocate an available host API port. No fixed external API exposure. |
| Bundled services | Keep Traefik, CoreDNS, local-path provisioning, and NetworkPolicy controller enabled. |
| Namespace / release | Helm creates release namespace urumi via --create-namespace. The chart does not also template that Namespace. |
| Context protection | Check for an existing cluster/release first. Never delete, replace, or take ownership of an existing installation automatically. Preserve existing kubeconfig entries and current context. |

The setup command uses the pinned image and writes/merges the new connection entry without switching the user's active context. All later commands use explicit context flags. If the selected k3d configuration cannot preserve that behavior, write a project-local ignored kubeconfig instead and pass it explicitly; document the chosen path without exposing its contents.

### One shared Helm chart

~~~text
deploy/charts/urumi/
    Chart.yaml
    values.yaml                     safe defaults; foundation disabled
    values-local.yaml               local host/storage; foundation disabled
    values-prod.yaml                production-shaped settings; foundation disabled
    values-m1.yaml                  opt into the disposable M1 page
    templates/
        _helpers.tpl
        foundation/
            configmap.yaml
            deployment.yaml
            service.yaml
            ingress.yaml
            pvc.yaml
            networkpolicy.yaml
~~~

All foundation templates are guarded by foundation.enabled. M1 deploys local values plus values-m1.yaml. Ordinary local and production renders exclude the temporary page. M9 completes all application values, schema validation, and production operating instructions. M1 does not create empty templates for future services.

## 5. The page and its disk

Use Python's built-in HTTP server rather than write a new FastAPI application just for this check. Python is also our approved backend language. This server serves only disposable test content and is removed after M1.

| Resource / file | Design | Observable behavior |
|---|---|---|
| ConfigMap | Holds index.html with the page marker and a small seed/check script if needed. No secrets. | Expected page text is reproducible. |
| Deployment | One replica, Recreate update strategy; Python serves /data on port 8080. | Kubernetes replaces a deleted Pod; avoids overlapping PVC users during upgrades. |
| Service | ClusterIP named urumi-foundation; port 80 → container 8080. | Stable internal address: urumi-foundation.urumi.svc.cluster.local. |
| Ingress | Class traefik, host foundation.urumi.test, path /. | Browser reaches the page through the cluster entry point. |
| PVC | urumi-foundation-data; 1 GiB; ReadWriteOnce; storageClass local-path. | /data survives page Pod replacement on this local node. |
| Container identity | UID/GID 1000, fsGroup 1000, no privilege escalation, drop capabilities. | Non-root process can write its mounted test disk; verify actual permissions. |

At startup, create /data/index.html from the mounted ConfigMap only when absent, then start the HTTP server. Do not overwrite existing saved files on every restart. A unique persistence marker is written separately to /data/persistence-marker.txt during the check; HTTP reads of that file confirm the same marker before and after replacement.

Keep the PVC with Helm's keep annotation when disabling/uninstalling the temporary workload. Document the retained PVC as intentionally outside later Helm cleanup; do not assume it can automatically be adopted into a new release. Deleting this disposable PVC requires explicit approval. No cluster deletion is part of normal cleanup.

Local-path storage lives within the local node's storage environment. Pod replacement is the promised check. Cluster/node deletion, backup restoration, multi-node failover, and actual shop database persistence are not proved here.

## 6. Health and resource settings

| Component | Requested CPU / memory | Maximum CPU / memory |
|---|---|---|
| Page container | 50m / 64 MiB | 250m / 128 MiB |
| Each short-lived checking Job | 25m / 32 MiB | 100m / 64 MiB |

1000m CPU means one CPU core. A request helps Kubernetes decide where the container fits; a limit caps its allowed usage. These are initial settings, to be adjusted only from observed scheduling or memory problems.

- **Readiness:** HTTP GET / on 8080, every 3 seconds, 2-second timeout, three failures mark it unready.
- **Liveness:** HTTP GET / on 8080, initial delay 10 seconds, every 10 seconds, 2-second timeout, three failures trigger restart.
- Page startup/rollout wait: at most 120 seconds after images are available; capture events on failure rather than extending forever.
- Checking Jobs: restartPolicy Never, backoffLimit 0, activeDeadlineSeconds 30; each HTTP call has a 5-second timeout. Jobs finish rather than expose HTTP health probes.
- Cluster-managed components are inspected separately; their bundled settings are recorded rather than represented as our chart's workload settings.

## 7. Connection rules: the smallest meaningful test

The policy selects only Pods labelled with this release and component=foundation. It does not restrict future shop/backend Pods. First deploy with the policy disabled for a baseline; then enable it through a Helm value.

| Caller → page | Baseline | Policy enabled |
|---|---|---|
| Allowed Job in urumi, label m1-access=allowed | Must succeed | Must succeed |
| Unrelated Job in urumi, label m1-access=denied | Must succeed | Must fail to connect |
| Traefik Pods in kube-system | Browser must work | Browser must still work |

**Policy design:** Ingress-only restriction on the page's TCP 8080. Allow the permitted Job using Pod labels in the same namespace. Allow Traefik using namespace AND Pod selectors in the same rule item; inspect its actual labels before implementation. Do not use a namespace-wide kube-system allow rule. Leave page/client egress unrestricted in M1, so DNS and responses work without introducing a cluster-wide egress policy.

Fresh Jobs run each phase with unique names. The check runner builds simple Kubernetes Job manifests with explicit labels, image, command, resources, context, and namespace. Their Python standard-library client checks DNS and HTTP without installing packages.

For the denied case, resolve the Service name first; verify the permitted caller still reaches the same destination. A DNS error, HTTP error response, or broken server is not a passing network-denial result. Retry fresh TCP attempts for at most 30 seconds after policy update; record timing and failure details. If Traefik's source identity does not match the selectors, inspect the actual traffic path and revise the narrow rule; do not bypass enforcement with allow-all.

These test labels are controlled by the local cluster operator. Label rules alone are not a security boundary against someone with permission to modify Pods. M5/M10 separately establish the real application's permissions, credential checks, and gateway-only access evidence.

## 8. Named files and their responsibilities

| File | Responsibility |
|---|---|
| infra/local/k3d.yaml | The one-node cluster configuration and selected host port. |
| deploy/charts/urumi/Chart.yaml | Chart metadata, initial version 0.1.0, API v2. |
| templates/_helpers.tpl | Names and release/component labels used consistently by resources and policies. |
| templates/foundation/* | The seven resources listed above, enabled only for M1. |
| values*.yaml | Common defaults, local/VPS differences, temporary M1 opt-in, and policy switch. |
| scripts/m1/preflight.ps1 | Tool versions, Docker server access, capacities/ports/context; bounded commands and safe failure report. |
| scripts/m1/setup-cluster.ps1 | Create only the named cluster if absent; stop on conflicts. No administrator settings changes. |
| scripts/m1/check-foundation.ps1 | Baseline, DNS, policy phases, Pod replacement, exposure inspection, structured results and raw evidence. |
| docs/local-cluster.md | Plain-language commands, hostname setup, expected outputs, stop/start, and cleanup. |
| docs/evidence/m1/* | Commands, JSON/text results, screenshot, settings, and limitation report. |
| .gitignore | Ignore portable binaries and any project-local kubeconfig; keep source/config and safe evidence. |

No orchestrator or application backend entry point is created. The scripts coordinate only M1 infrastructure checks.

## 9. Implementation and checks, in order

These are planned commands; setup files do not exist yet. Run from project root in PowerShell after implementation approval. Scripts will handle native command exit codes explicitly; a PowerShell command returning text is not automatically PASS.

| Order | Action | Acceptance IDs |
|---|---|---|
| 1 | Run preflight; verify portable binary/archive checksums; confirm Docker engine, resources, versions and available port. | M1-01 |
| 2 | Create named cluster; wait for node, DNS, Traefik, provisioner readiness. Save exact versions/status. | M1-01 |
| 3 | Helm lint/render common+local+M1 and common+prod. Inspect policy selectors, probes, resources, and test-workload exclusion. | M1-02, M1-07, M1-08 |
| 4 | Install foundation with policy disabled. Confirm both fresh test callers resolve DNS and get the page marker. | M1-04, baseline for M1-06 |
| 5 | Explain hosts-file entry; user adds foundation.urumi.test → 127.0.0.1 if elevation is required. Open actual browser and save screenshot. | M1-03 |
| 6 | Enable policy; repeat allowed/denied calls and browser access with bounded waits. | M1-06 |
| 7 | Write unique marker, save old Pod UID, delete that page Pod only, wait for replacement, read marker, save new UID. | M1-05, M1-07 |
| 8 | Inspect all public/internal routes; record infrastructure exception for Traefik. | M1-08 |
| 9 | Remove only M1 test Jobs and disable foundation through Helm while retaining PVC; inspect remaining resources. Record restore steps. | M1-09 |

Expected Helm installation shape (portable executable path will be explicit in the runbook):

~~~powershell
helm upgrade --install urumi deploy/charts/urumi --kube-context k3d-urumi --namespace urumi --create-namespace -f deploy/charts/urumi/values-local.yaml -f deploy/charts/urumi/values-m1.yaml --set foundation.networkPolicy.enabled=false --wait --timeout 5m
~~~

The check script then upgrades with the same files and foundation.networkPolicy.enabled=true. Cleanup upgrades the same release with foundation.enabled=false. Cleanup never uninstalls a later combined release or deletes resources by broad namespace selectors.

If agent Docker access remains denied, you run the same prepared scripts in your normal PowerShell terminal. We inspect their saved output. A failed query or missing output remains BLOCKED/unverified; do not invent a PASS. Browser screenshots require an actual browser visit, not just a successful HTTP request.

## 10. Evidence and handoff

The check runner saves a result per acceptance ID: PASS, FAIL, or BLOCKED, exact command, timestamp, exit code, observed result, and relevant file. Raw logs accompany the summary. Do not dump kubeconfig contents, Kubernetes Secrets, environment values, or Docker credential configuration.

Deliver docs/evidence/m1/report.md with the page screenshot, node/Pod status, PVC before/after marker, policy baseline and enforcement outputs, exposed endpoint list, and exact rerun instructions. Explain why the evidence proves only M1. Review implementation before acceptance checks; after results, obtain module acceptance before M2.

Independent [design review](../evidence/m1/design-review.md) found no blocking issues. Runtime checks remain pending.

### Your approval gate

Approve this design to authorize M1 implementation and its listed checks. Elevated hosts-file edits stay user-run. No M2 or application integration is included.

### Official technical references

- [k3d v5.9.0](https://github.com/k3d-io/k3d/releases/tag/v5.9.0), [k3s v1.36.3+k3s1](https://github.com/k3s-io/k3s/releases/tag/v1.36.3%2Bk3s1), [Helm v3.21.3](https://github.com/helm/helm/releases/tag/v3.21.3): release existence verified; local compatibility not yet tested.
- [kubectl version compatibility](https://kubernetes.io/releases/version-skew-policy/): kubectl may be within one minor version of the API server.
- [k3d configuration](https://k3d.io/stable/usage/configfile/): named cluster, pinned image, port mappings, and kubeconfig behavior.
- [k3s networking](https://docs.k3s.io/networking/networking-services): bundled DNS, Traefik, and NetworkPolicy support; enforcement needs our live checks.
- [Kubernetes NetworkPolicy](https://kubernetes.io/docs/concepts/services-networking/network-policies/): selected Pods and combined namespace/Pod selectors define permitted traffic.
- [Official Python image](https://hub.docker.com/_/python): image source; exact tag/digest remains to be resolved.
