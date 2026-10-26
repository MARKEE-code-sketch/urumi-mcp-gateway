# Backend owner-monitor recovery image verification

**Final result: PASS**, using only the approved fresh `urumi-m10` and disposable `urumi-m10-clean` releases. The root independently reviewed the two-line owner-monitor recovery fix and ran its controlled checks; this task verified actual image/runtime deployment, without claiming another full user-flow demonstration.

Exported `urumi/backend:m10-recovery` to an ignored local archive and hashed the actual Docker-exported configuration bytes. [Image configuration identity](image-identity-backend-recovery.json) records config `sha256:160ae7b13c17f4a0e94a02a855b0ffae5181081cb9f97136846c5f50e0982d43`. [OCI descriptor identity](image-descriptor-backend-recovery.json) records immutable index `sha256:2c842ad25e4e09f3ffd5a2ae515942e1bf51f2e2df42250e7ee24c7dab20aabe`.

The image was imported by its explicit tag into existing cluster `urumi`. Read-only containerd inspection resolved the actual index to its linux/amd64 manifest and configuration, independently verified each content blob's SHA256, and matched the exported config. All 41 current frozen source/build inputs matched `image-source-inputs.json`; the historical freeze remains separately retained. Each actual backend container also returned the frozen SHA256 for `/app/backend/orchestrator.py`.

## Initial failure and correction

[Initial attempt](monitor-fix-runtime-initial-attempt.json) remains FAIL/TimeoutExpired. Main Helm revision 3 timed out; read-only diagnosis after host/cluster availability recovered found the new backend in ImagePullBackOff. The tag existed in node containerd, but the immutable index alias was absent from CRI, so Kubernetes attempted to pull the local-only image from Docker Hub. Docker Desktop and API availability were also interrupted overnight. No claim is made that source changes caused the host interruption; this task did not restart Docker, a node or the cluster.

Root authorized adding only the verified alias:

```powershell
docker exec k3d-urumi-server-0 ctr -n k8s.io images tag docker.io/urumi/backend:m10-recovery docker.io/urumi/backend@sha256:2c842ad25e4e09f3ffd5a2ae515942e1bf51f2e2df42250e7ee24c7dab20aabe
```

[Import recovery](monitor-fix-import-recovery.json) records successful CRI digest resolution to the expected config. The already-created backend Pod became Ready automatically; no additional Pod delete was required.

## Final deployed observations

[Final runtime evidence](monitor-fix-runtime.json) records the exact commands, before/after allowlisted state and PASS for both image-only upgrades. For each release, current deployed Helm effective values were captured privately, and only backend image tag/digest were changed. This preserves current deployed settings, including the main shop's newer HTTPS Ingress configuration, even though older operator input files had drifted from live values. Exact upgrade values are under ignored `.tools/operator/m10/values-monitor-fix.yaml` and `.tools/operator/m10-clean/values-monitor-fix.yaml`; no private values are published in evidence. The existing README inputs `.tools/operator/m10/values.yaml` and `merged-values.yaml` were then synchronized in only three fields: `backend.image.tag`, `backend.image.digest` and `store.ingress.tlsSecret`. All other private settings and historical encrypted backup inputs remain untouched.

| Target | Final Helm state | Runtime checks |
|---|---|---|
| `urumi-m10` | Revision 4 deployed | Seven workloads Ready; backend uses verified recovery index/config; three Bound PVC UIDs unchanged; registry/Woo marker unchanged; shop and dashboard TLS references preserved |
| `urumi-m10-clean` | Revision 2 deployed | Seven workloads Ready; same verified backend image/source; three Bound PVC UIDs unchanged; registry/Woo initialization state unchanged, preserving prior deliberate deletion |

All seven original `urumi` Pod/PVC/Service UIDs remained unchanged. Historical build/image/runtime evidence was retained, and initial failure is linked separately rather than rewritten as success. The root and browser acceptance agent were notified that main MCP reads and the clean release's final source/deletion verification could proceed. The clean release was deliberately left installed for the root's separately guarded cleanup. Provider calls, registry edits, backup restore and fault testing were outside this image-update task.
