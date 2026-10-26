# M1 live check results

**Dates:** 14–15 October 2026 (India time). **Status:** All nine M1 checks PASS. Implementation and verification complete; awaiting user module acceptance before M2.

## In simple terms

Our one-node Kubernetes environment is running. Helm deployed the temporary page. The page's saved file survived replacing its Pod. The connection rule allowed our permitted caller and rejected the unrelated caller, while the web route remained usable.

Docker access works through approved commands outside the sandbox. The standard sandbox command runner still fails before launch; it has not been repaired. Earlier access/download blockers are historical in report-initial-blocked.md and tool-install-attempt.json.

## Setup and observed test environment

| Part | Observed |
|---|---|
| Docker engine | 29.6.1; Linux containers; 12 CPUs and 8,007,598,080 bytes allocated memory. |
| Kubernetes | One k3d server node, k3s v1.36.3+k3s1, context k3d-urumi. |
| Installation | Project-local checksum-verified k3d v5.9.0 and Helm v3.21.3; release urumi in namespace urumi. |
| Page | foundation.urumi.test on loopback port 80, through Traefik Ingress. HTTP check passed using explicit local name resolution before cleanup. |
| Runtime image | python@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419. |
| Disk | 1 GiB local-path PVC urumi-foundation-data; retained after cleanup. The marker survived Pod replacement before cleanup. |

No shop, gateway, account system, AI chat, or real module integration was deployed.

## Acceptance results

| ID | Result | Evidence |
|---|---|---|
| M1-01 | PASS: prerequisites recorded and node Ready | preflight.json, tool-install.json, cluster-status.txt |
| M1-02 | PASS: local+M1 and production-shaped chart lint/render; production excludes temporary workload | helm-checks.txt, rendered-values-local.yaml.txt, rendered-values-prod.yaml.txt |
| M1-03 | PASS: supplied screenshot shows expected page; hostname/DNS and HTTP route corroborate it | foundation-browser.png, hosts-edit-result.json, ingress-check.txt |
| M1-04 | PASS: both baseline caller Jobs resolved internal Service DNS and received page | network-policy-check.txt |
| M1-05 | PASS: unique saved marker readable before and after replacement with different Pod UID | storage-check.txt, storage-result.json |
| M1-06 | PASS: both baseline calls succeed; policy then permits allowed caller, rejects other after successful DNS; fresh permitted call and Ingress succeed | network-policy-check.txt, node-firewall.txt, network-policy-diagnostic.md, ingress-check.txt |
| M1-07 | PASS: page probes and resource requests/limits present; replacement becomes Ready | workload-settings.txt, infrastructure-settings.txt, storage-result.json |
| M1-08 | PASS: application Service internal, sole application Ingress is page; infrastructure Services listed separately | exposure-check.txt |
| M1-09 | PASS: temporary page and all recorded test Jobs/Pods removed; original Bound PVC retained | cleanup-check.txt, cleanup-notes.md, after-cleanup.json |

All six PowerShell scripts passed parsing. After the cleanup correction, the changed checker was additionally gated by ParseFile before final execution, which exited zero. The independent reviewer audits source and raw evidence separately.

## Persistence proof

- Old Pod UID: d25f5830-cb49-4180-9410-beb64933e47f.
- New Pod UID: a3d01932-8f1e-455b-8216-344bb3dcea96.
- Saved marker: m1-7b437f1c5568483487d339ea48bd7d8f.
- HTTP reads inside the old and new Pods returned the same saved marker.

This proves Pod replacement on this local node. It does not prove survival after deleting the node/cluster, backup recovery, or real shop database persistence. M2 owns real WooCommerce persistence checks.

## Corrections found during live execution

1. Official k3d checksum filenames have an optional _dist/ prefix; exact matching now supports that prefix and still verifies SHA256.
2. A Ready node can precede its bundled Traefik Deployment. Setup now waits for addon creation and can explicitly resume our own saved partial setup without recreating the cluster.
3. The policy controller rejects disallowed traffic with icmp-port-unreachable. The original checker accepted only timeouts and failed on ConnectionRefusedError. After inspecting the actual firewall, corrected it to recognize a TCP refusal or timeout after DNS; baseline and fresh allowed controls remain mandatory. DNS/HTTP/other failures still cannot pass.
4. Resumed Helm upgrade now includes --create-namespace for a setup interrupted before initial installation.

The initial failed calls remain in appended raw logs. A denied verification Job exits42 intentionally; its Kubernetes Error/Failed status is expected test evidence, not a failed page workload.

## Commands and evidence

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/run-m1.ps1
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n kube-system get pods,deployments,helmcharts
docker exec k3d-urumi-server-0 iptables-save | Set-Content -Encoding UTF8 docs/evidence/m1/node-firewall.txt
~~~

The runner's exact native commands, timestamps, exits, and outputs are saved in the named evidence logs. Never include the ignored kubeconfig's credential contents in evidence or submission.

## Browser and final cleanup evidence

The user supplied Screenshot 2026-10-14 231804.png after opening the local test page. It visibly contains the expected heading and description. Saved unchanged as foundation-browser.png. The screenshot is cropped to page content and has no address bar; hosts-edit-result.json and ingress-check.txt independently establish the hostname and HTTP route.

Ran the approved cleanup after reviewing the screenshot. Final audit initially found nine test Jobs and Pods left behind: PowerShell had loaded the JSON list as one space-joined string, and ignore-not-found hid the skipped deletion. That false-positive result was corrected to FAIL before retrying. Preserved after-first-cleanup.json and check-jobs-first-cleanup.json.

Fixed loading with explicit foreach over the parsed array, saved an explicit string array, verified each Job's M1/release labels before deletion, used foreground deletion, and added a zero-Jobs/Pods postcondition. A malformed edit was caught by PowerShell before execution, repaired, and syntax-gated before the final successful run. No cluster changes occurred in that parser-failed attempt.

Final after-cleanup.json contains only the retained PVC among the queried Pods/Jobs/PVCs/Ingresses. Its UID is unchanged: c6f386c1-ef1e-4996-ab86-ed888999226e; phase Bound. Other foundation resources are absent in cleanup-check.txt. The Kubernetes node remains Ready.

**Current user-visible state:** The temporary page has been removed as part of the successful cleanup check. Its URL will no longer serve the test page. The cluster, saved disk, source files, and screenshot remain. The Windows hostname entry and its ignored backup also remain.

All M1 checks are now observed and reviewed; obtain user module acceptance before M2. No actual VPS deployment is claimed; complete application/VPS packaging remains M9.
