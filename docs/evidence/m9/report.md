# M9 implementation and static package results

**19 October 2026. Status: implemented; independent acceptance review PASS for all 12 static package criteria. User module acceptance pending.** M9 made no Kubernetes changes, Docker builds/imports/pushes or provider calls. M10 still owns combined runtime and complete deployment proof.

The shared Helm recipe now describes all seven mandatory workloads: WordPress, MariaDB, Woo MCP, Inventory MCP, PostgreSQL, backend and dashboard. Local and production examples use that same chart. The new backend is a packaging contract for `python -m backend.main`; those M10 files do not exist yet. The real build command therefore stops before Docker instead of silently starting a test harness.

WHAT changed: release values/schema, backend ConfigMap/Deployment/Service/policy, same-origin dashboard/API/MCP Ingress, exact policy caller labels, store TLS/proxy transport contract, namespaced Secret retention, build/preflight/check scripts and operating/design/threat/handoff guides. WHY: a reproducible release must make missing infrastructure/runtime inputs visible and keep internal services/credentials private. HOW: static lint/render and parsed positive/negative checks, with deployment-time input validation kept separate from renderable examples.

| Check | Observed result | Evidence |
|---|---|---|
| Release tests | **60 PASS, 15.15 seconds** | [tests.txt](tests.txt), [JUnit](tests.xml). |
| Existing store chart compatibility | **7 PASS, 1.00 second** | [store-compatibility-tests.txt](store-compatibility-tests.txt). |
| Shared chart | Local and production lint/render exit0; seven workloads, three kept PVCs | [local render](render-local.yaml), [production render](render-prod.yaml), [resource inventory](resource-inventory.json). |
| Values/security negatives | Reject wrong types, bad resources/image references/ports, owner count, harness collisions, missing workload/TLS, origin/transport mismatch, stale selectors/references and unsafe deploy metadata | [tests.txt](tests.txt), [example preflight](preflight-examples.json). |
| Exposure/policies/RBAC | Parsed routes, allowed/denied traffic paths and dedicated namespace permissions; alternate release/namespace cases pass | [resource-inventory.json](resource-inventory.json). This is not live CNI proof. |
| Known credential scan | 229 source files and 307 existing evidence files; **6 privately held sentinels, 0 matches**, no prohibited private evidence file | [source-scan.json](source-scan.json). Unknown-secret absence is not guaranteed. |
| Build contract | Actual Backend request rejected with `M10_BACKEND_ENTRYPOINT_MISSING` before Docker; checks target preserved | [rejection](backend-build-rejection.txt), [build inventory](build-inventory.json). |
| Existing runtime parity | All **35** prior backend/M6/M7 runtime/dependency/contract files match saved image-source hashes | [runtime-source-parity.json](runtime-source-parity.json). No new combined backend image is claimed. |
| Checker dependencies / PowerShell | pip check PASS; five touched PowerShell files parse with zero errors | [pip](checker-pip-check.txt), [syntax](powershell-syntax.json). |
| Source-only reproducibility | 229 files copied; both profiles render; zero forbidden private/generated paths | [staging-check.json](staging-check.json). Fresh running installation remains M10. |

Exact invocations/exits are in [commands.json](commands.json); prerequisites in [versions.json](versions.json). The full static runner was:

```powershell
./.tools/m9/venv/Scripts/python.exe scripts/m9/check-m9.py --helm .tools/m1/helm.exe --output docs/evidence/m9 --sentinels .tools/m6/access.json
./.tools/m9/venv/Scripts/python.exe -m pytest tests/store -q -p no:cacheprovider --basetemp .tools/m9/pytest-store-compat
```

Run from repository root in PowerShell. The optional sentinel file is private and ignored; its values are never copied or printed. Running the checker without it records a truthful zero known-sentinel count. The initial sandbox test attempt hit Windows temporary-directory permission errors; the authorized isolated test run then worked. Early checks also caught missing dashboard startup/selector alignment, invalid production repository casing and schema expectation wording. Those were fixed; the saved final results above are authoritative.

Compatibility correction: the original M1/M2 scripts used `values-local.yaml`, which now intentionally enables the full release. Their references now use `values-module-local.yaml` / `values-module-prod.yaml`, preserving the original opt-in profiles and avoiding accidental M10 workloads. Existing tests verify those profiles; no old live check or retained-shop upgrade was rerun. M5/M6 build instructions now explicitly choose Docker target `checks`; historical raw evidence is preserved.

Production values still contain marked example hosts, documentation address and image placeholders. Deploy preflight rejects them, missing image digests/provenance/API endpoint data, unchecked Secret/TLS/storage metadata and absent M10 entry points/runtime image. A successful synthetic metadata fixture tests the validator only. Production Woo TLS through Traefik, actual retained WordPress proxy configuration, DNS/hostAliases freshness, network enforcement, real credentials, backup/restore/rollback and VPS operation are **unverified**. The production final Traefik-to-WordPress hop is plaintext inside the cluster.

M7's real Groq probe remains pending free-plan confirmation. M8 has its own independent frontend/browser gate. M10 must compose the real database/identity/registry/audit/gateway/chat services in startup order, build their combined image, install the complete release and demonstrate two users, checkout, chat, external MCP, revocation, failure recovery, audits and persistence. M9 does not label those complete.

The runner's [raw results](check-results.json) intentionally retain `PASS_STATIC_REVIEW_PENDING`. The independent [review](acceptance-review.md) and [acceptance results](acceptance-results.json) record **12/12 PASS** for M9's static package scope; user module acceptance remains pending. The reviewer inspected source and saved evidence without rerunning tests or mutating a live system.
