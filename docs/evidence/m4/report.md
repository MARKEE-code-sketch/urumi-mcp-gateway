# M4 implementation and independent checks

**Date:** 16 October 2026. **Result:** eight acceptance groups passed and independently reviewed PASS; user module acceptance remains pending. The real gateway integration remains M10.

## WHAT, WHY, HOW

Inventory is a small Python MCP server that looks up fixed sample warehouse data. It supplies the second predictable tool source without depending on shop credentials or a database. The separate Microsoft Learn probe proves a genuine third, externally hosted MCP source can be discovered and called from our cluster.

For an Inventory request, the SDK receives a Streamable HTTP message; our code validates `sku`, trims it, reads the already-validated sample records, and returns matching JSON text and structured data. `DEMO-001` returns Bengaluru quantity 12, `ZERO-001` remains found with quantity 0, and unknown/case-mismatched SKUs return a successful not-found result. It cannot update shop stock. The unchanged M0 definition controls the single tool's schemas and annotations.

## Observed results

| Check | Observed evidence |
|---|---|
| M4-01 | Strict fixture/argument cases, malformed/missing/bounded fixtures, booleans/floats rejected as quantities, trimmed/case-sensitive known/unknown/zero lookups, copied results, invalid fixture prevents startup. `host-tests.txt`, `linux-tests.txt`. |
| M4-02 | Real TCP SDK initialization/discovery exposes exactly `lookup_sku` with exact M0 schemas/annotations, successful text/structured agreement, invalid execution error and unknown-tool protocol error. Negotiated `2025-11-25`. Host/Linux tests and actual `m4-allowed-first.json`. |
| M4-03 | Helm lint plus local/production renders; isolated Ready Deployment with probes/resources, nonroot/no-token/read-only settings and ClusterIP-only exposure. Actual image config verified from Docker-exported bytes and matched Pod imageID. `workload-status.yaml.txt`, `exposure.json.txt`, `image-identity-check.json`. |
| M4-04 | Permitted call, unrelated connection refused after successful DNS resolution, permitted call again. Deliberate liveness404 causes kubelet Killing event and restartCount1 in the recorded same Pod UID; restoring the probe yields another successful call. `m4-allowed-first.json`, `m4-denied.json`, `m4-allowed-again.json`, `liveness-restart-pod.json`, `probe-events.txt`, `m4-probe-recovered.json`. |
| M4-05 | Actual local and cluster Microsoft Learn discovery and `microsoft_docs_search` call both pass; complete genuine schemas/results retained. `hosted-local.json`, `m4-hosted-cluster.json`. Human content review is recorded separately. |
| M4-06 | Real TCP missing/wrong/valid bearer and named-header cases, two controlled `service_info` names, no sentinel in saved output. Controlled fixtures only, not a real authenticated hosted-server claim. Host/Linux logs and `controlled-failures-final.txt`. |
| M4-07 | Bounded controlled HTTP503, malformed MCP, slow endpoint, response/aggregate bytes, compressed-response rejection, repeated cursors, page/tool limits; healthy Inventory answers afterward. Additional final host regression proves actual closed-port `ConnectError`. `controlled-failures-final.txt`. |
| M4-08 | Owned `urumi-m4-check` namespace removed; original `urumi` Deployment/StatefulSet/Service/PVC identity lists match exactly. `cleanup.txt`, `store-before.txt`, `store-after.txt`, `results.json`. |

The complete host suite passed **10 test methods**; the Linux image suite passed **10 test methods**. A subsequent host-only targeted run passed all **4 compatibility methods**, adding an explicit closed-port connection-refused case. This last addition changes test code only; Inventory/probe/client application source is unchanged from the checked image. Host and Linux tests are independent of the live cluster and are not substituted for cluster evidence.

Actual Microsoft Learn negotiated protocol `2025-06-18`, with an SDK-managed stateful session. The discovered tools were `microsoft_docs_search`, `microsoft_code_sample_search`, and `microsoft_docs_fetch`; these are observed names, not hardcoded production tool definitions. The cluster call completed in **4.102 seconds**, receiving **52,929 bytes** across the bounded session. It returned real Azure/Kubernetes documentation on readiness, liveness and startup probes, including [readiness probes](https://learn.microsoft.com/azure/container-instances/container-instances-readiness-probe) and [Kubernetes hosting](https://learn.microsoft.com/dotnet/orleans/deployment/kubernetes#liveness,-readiness,-and-startup-probes). The complete raw result remains in the evidence artifact.

## Commands and reproducible inputs

PowerShell commands from the repository root:

~~~powershell
.venv/Scripts/python.exe -m unittest discover -s tests/sample_mcps -p 'test_*.py' -v
.venv/Scripts/python.exe scripts/m4/probe.py --output docs/evidence/m4/hosted-local.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/m4/check-m4.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/m4/check-m4.ps1 -SkipBuild
~~~

The initial full runner built the image and passed host/Linux checks, then safely failed an incorrect comparison of Docker's OCI index identity with Kubernetes' runtime-config identity. Cleanup completed. The corrected rerun exited **0**; it exported the actual Docker image, hashed its config bytes, verified the tag/config mapping, and matched that digest to the Pod. Initial failure artifacts are preserved as `results-initial-image-check.json` and `failure-initial-image-check.txt`; command logs append chronologically. The generic `failure.txt` is also historical from that initial run, not the final result.

- Python base: `python@sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419` (Python3.13.5).
- Direct pins: MCP1.26.0, HTTPX0.28.1, jsonschema4.26.0, Starlette0.52.1, Uvicorn0.40.0; exact full lock in `services/sample_mcps/requirements.lock.txt`; Linux `pip check` passed.
- Image tag: `urumi/inventory-mcp:m4`; OCI index `sha256:f7265bb0b31ee709d3b97d552512c9cd7113b482b0a50483ae141ad63e31d8bb`.
- Actual runtime config: `sha256:32f6307e850d6ccd3cb1e857ff949dfafbf63631594ed7196cc9684b20a57817` (Linux amd64), verified from exported bytes and observed in cluster.

Exact Helm/kubectl/Docker commands and exit codes are recorded beside the corresponding artifacts. [External MCP runbook](../../external-mcp.md) explains how to reproduce the checks and what each does.

## Limits and remaining integration

No real shop-to-Inventory/gateway wiring occurred. The server remains disabled in the real release; its checking namespace is gone. Registry authentication/credential injection, gateway aliases and failure isolation, personal user keys/audits, chat, cross-server natural language and the final two-user demo remain their later modules. A real authenticated hosted server remains unverified. Microsoft Learn's external availability/schema can change; this report describes the observed run, not an uptime guarantee.

Inventory needs no persistent disk, outgoing network or API token. The saved store resource/PVC identity comparison and scoped M4 command history prove resource isolation; M4 does not perform shop API/database writes or claim a fresh shop-content persistence test. No paid service, credential acquisition or public repository publication was performed.
