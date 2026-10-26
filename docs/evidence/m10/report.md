# M10 implementation progress and observed checks

**Historical controlled-build checkpoint; superseded for current live status by [the acceptance ledger](acceptance-results.json) and [live acceptance report](live-report.md).** The statements below describe the earlier source/build phase only. A separate fresh release, HTTPS, real provider, browser and external-client checks were subsequently exercised on 20 October 2026.

## What changed and why

`backend/main.py` starts one real backend worker. `backend/orchestrator.py` connects the existing database, identity, key, registry, audit, discovery, gateway and chat factories, runs recovery before readiness, and owns their shutdown. Browser sessions and external personal keys keep their existing separate authentication paths; chat and external tools share the same router.

Schema 3 adds an atomic one-time Woo initialization marker. First startup inserts the built-in server; later startup preserves administrator edits, disable and deliberate deletion. The marker is independent of the deletable server row. Existing schema-2 installations upgrade without losing their installation UUID.

Integration review found and corrected two real problems: cancelled API requests could leave untracked database threads, and the composed chat disconnect watcher could hang after cancellation. Tracked API/lifecycle workers now retain ownership until actual work drains; the chat watcher checks its cancellation state. Regression tests reproduce these paths. Monitor failures also complete cleanup. Undrained work requests process termination without ordinary ownership release; interrupted writes remain uncertain rather than replayed.

The Docker release stage contains runtime backend/contracts and starts `backend.main`; historical check scripts remain only in the explicit `checks` stage. The package checker's missing-source negative now runs in a staged checkout before Docker. Historical M6 hashes remain historical comparisons, not false current-image parity requirements. Read-only inventory, controlled test runner and demo guidance were added; they do not silently deploy or fabricate live scenarios.

## Observed results

These rows are separate suites with some shared tests; do not add them into a unique-test total.

| Check | Observed result | Evidence and limit |
|---|---|---|
| Fresh dependency installation | Existing backend lock plus PyYAML 6.0.3 installed; pip check PASS | [environment](environment.json), [pip check](dependency-check.txt). Initial attempt combining two historical locks failed because pytest pins differed; no dependency pin was loosened. |
| Controlled composition/gateway/chat | **161 PASS, 6 SKIP, 57.33 seconds** | [output](controlled/controlled-tests.txt), [JUnit](controlled/controlled-tests.xml). The six opt-in PostgreSQL tests are deliberately skipped; the runner removes their DSN from inherited environment. No provider, cluster or real database in this run. |
| Separate real PostgreSQL suite | **6 PASS, 10.08 seconds** | [output](postgres-tests.txt), [JUnit](postgres-tests.xml). Fresh loopback database and unique disposable schemas. Real migrations, exclusive owner, marker rollback/adoption/edit/delete and real factory/account/invitation/key/router/audit/revocation composition. Kubernetes Secret access and remote MCP replies are substituted, provider key empty; this is not real upstream acceptance. |
| Package/store/target checks | **79 PASS, 15.99 seconds** | [verification](checker-verification.json), [JUnit](release-tests.xml). Static release/store compatibility and read-only guards. Later focused runner guard check: 11 PASS, 0.20 seconds, including inherited-DSN removal. |
| Current package checker | Local/production lint/render, staging, negatives, documents and private known-value scan pass | [package results](package-checks/check-results.json). Eleven static groups PASS; independent review separate. No Docker build, cluster or provider call by this checker. |
| Actual backend release image | Docker build exit 0; Linux import/no-harness smoke PASS with networking disabled | [build log](docker-build-backend.txt), [smoke](image-smoke.json). This does not prove application startup in Kubernetes. |
| Image/source identity | Actual exported Docker configuration hashed; 41 frozen source inputs unchanged after build | [image identity](image-identity-backend.json), [original source inputs](image-source-inputs-before-monitor-fix.json), [final check](final-root-check.json). No running Kubernetes Pod comparison claimed in this historical phase. The later monitor correction has separate current image/runtime evidence. |
| Cleanup/data boundary | Disposable PostgreSQL container removed; seven retained shop resource identities unchanged | [cleanup](postgres-cleanup.json), [final check](final-root-check.json). Original Pods remain Ready; no retained release upgrade or disk mutation. |
| Independent review | No unresolved blocking source defect | [design review](design-review.md), [implementation review](implementation-review.md), [final acceptance review](acceptance-review.md). Final review confirms the recorded counts and source freeze; complete-system verdict remains BLOCKED, with no unresolved source blocker. |

The controlled composition tests include actual MCP protocol initialization at exact `/mcp`, cookie/key separation, API/chat routes, explicit child lifespan once, startup failure cleanup, ownership/readiness fencing, actual cancelled-thread draining and separate body budgets: API above 16 KiB rejected, authenticated MCP initialization at 20 KiB accepted and MCP above 64 KiB rejected.

## Commands and reproducibility

From repository-root PowerShell, after installing [M10 pinned requirements](../../../scripts/m10/requirements.txt):

```powershell
./.tools/m10/venv/Scripts/python.exe scripts/m10/check-m10.py --mode controlled --output docs/evidence/m10/controlled
./.tools/m10/venv/Scripts/python.exe -m pytest tests/release tests/store tests/e2e/test_target_guard.py -q -p no:cacheprovider --basetemp .tools/m10/pytest-release --junitxml docs/evidence/m10/release-tests.xml
./.tools/m10/venv/Scripts/python.exe scripts/m9/check-m9.py --helm .tools/m1/helm.exe --output docs/evidence/m10/package-checks
docker build --file backend/Dockerfile --target release --tag urumi/backend:m10 .
docker save --output .tools/m10/backend-image.tar urumi/backend:m10
./.tools/m10/venv/Scripts/python.exe scripts/m4/image_identity.py .tools/m10/backend-image.tar --image urumi/backend:m10 --output docs/evidence/m10/image-identity-backend.json
```

The observed package invocation additionally supplied private `--sentinels .tools/m6/access.json`; contents were never printed or copied. Its count and scan scope are in the saved package evidence. Unknown-secret absence is not guaranteed. The later [final artifact scan](final-artifact-scan.json) additionally checks the freshly generated disposable PostgreSQL password across selected source and all evidence, without saving any scanned value.

The PostgreSQL invocation was `python -m pytest tests/e2e/test_runtime_postgres.py -q -p no:cacheprovider --basetemp .tools/m10/pytest-postgres-final --tb=short --junitxml docs/evidence/m10/postgres-tests.xml`, using the fresh M10 Python. A parent process loaded a newly generated password privately and supplied `URUMI_M10_TEST_DSN` only in the child environment, redacting it from captured output. Never paste a real DSN into shared commands or run the historical `tests/backend` fixture against retained state: it truncates its historical database. See the [runbook](runbook.md) for the disposable target contract.

Earlier exploratory runtime tests hung at the chat cancellation integration bug. Their scoped processes were cleaned up after the fix. They are not counted as passing evidence; the final outputs above replace those incomplete attempts. Historical M8/M9 raw evidence remains unchanged.

## What is still required

The [acceptance ledger](acceptance-results.json) keeps all eighteen complete-system criteria incomplete; supporting tests do not replace live proof. Required next inputs are the separate-release target decision, certificate/hostname trust procedure and private inputs, current Groq free-plan confirmation, and actual Codex/Inspector setup. Full deployment then needs real Woo/Inventory/Learn tools, browser checkout/chat, two-user external prompts, revocation, disable/outage recovery, network/RBAC enforcement, persistence and isolated restore evidence. Production-shaped Woo HTTPS/OAuth transport also remains unverified.

No provider charge/fallback, trust-store or hosts change, VPS operation, publication, recording/upload, repository creation or submission occurred. The implemented code is ready for the next scoped deployment decisions; the mandatory core is not yet declared complete.
