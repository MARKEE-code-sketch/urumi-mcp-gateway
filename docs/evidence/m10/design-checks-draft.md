# M10 verification and deployment design review notes

This is a temporary design-review artifact for the single M10 spec, not an additional spec. No cluster operation, credential read, provider call or trust change was performed for these notes.

## Proposed ownership

- Root: append the approved concrete design to `docs/modules/m10-spec.md`, shared chart/config changes, workflow history, live operations and all target/private-input decisions.
- Composition implementer: `backend/main.py`, `backend/orchestrator.py`, configuration and built-in reconciliation helpers only where needed; `tests/e2e/test_lifecycle.py`, `test_composition.py` and `test_builtins.py` with controlled dependency contracts. Reuse existing API/router/chat factories.
- Verification implementer: `scripts/m10/check-m10.py`, small target/evidence helpers, `tests/e2e/test_target_guard.py`, live read-only inventory and explicitly selected live scenarios; `scripts/demo.ps1`, `docs/demo-checklist.md`, M10 runbook/report. Changes to existing M9 tests limited to now-present entry points and documented runtime behavior.
- Independent reviewer: read-only source and acceptance review; separate observed results from NOT RUN/BLOCKED criteria. Root accepts no reviewer verdict as user acceptance.

## Smallest safe deployment proposal

Use a separate release `urumi-m10` in application namespace `urumi-m10` and dedicated dynamic Secret namespace `urumi-m10-secrets` on explicit context `k3d-urumi`. Use fresh PVCs; never mount/copy the retained `urumi` disks or reuse its dynamic credential namespace. Proposed hostnames are `dashboard-m10.urumi.test` and `shop-m10.urumi.test`. These names and the separate-target choice require root/user confirmation before applying. This protects the existing working shop while proving the final chart.

The new shop is intentionally separate: create labelled disposable demo records there. Its data is not proof that old shop data was migrated. Retained `urumi` Pod/PVC/Service UIDs, readiness, restarts, image identities and selected safe store data identifiers must be inventoried before and after. Do not stop, bootstrap or upgrade retained `urumi` as a side effect.

No combined release can be installed until runtime entry points pass tests, final images are built/imported with actual configuration identity proof, private inputs exist, and HTTPS trust decisions are resolved. Use the existing chart and profiles plus ignored `.tools/operator/m10/values.yaml`; use merge helper to create ignored merged values for preflight. Never commit operator values, inventories containing secrets, backups or credentials.

For trusted HTTPS, prefer an explicitly supplied certificate/key whose SAN covers the proposed hostname and whose CA is already trusted by Windows/browser and the selected external clients. Operator supplies TLS Secret privately. If unavailable, root explains user-run hosts/DNS and CA-trust steps and obtains informed approval. Do not use browser certificate bypasses, insecure cookies, global TLS-verification disabling or trust-store installation during implementation. Public browser HTTPS validation and production Woo HTTPS verification remain separate checks. Production-shaped shop transport needs a real trusted certificate, actual Traefik Service IP/8443 mapping and WordPress trusted-proxy handling.

## Guard and private input contract

Every live helper requires explicit `--context`, `--kubeconfig`, `--namespace` and `--release`. Mutating commands additionally require a reviewed target descriptor with exact application namespace, separate Secret namespace and an installation ownership label. Refuse `urumi`, Kubernetes system/default namespaces, mismatched labels, existing unowned resources or omitted target fields. Reject cross-namespace secret/disk reuse. A read-only inventory operation can inspect retained `urumi`; it cannot authorize mutations there.

Private inputs: PostgreSQL password, shop database/salts/admin secrets, newly scoped Woo REST consumer pair, Groq key after free-plan confirmation, TLS materials, exact image digests and names-only input inventory. Do not read/reuse historical credentials automatically. API endpoint CIDRs, storage class, ingress selectors/ports and host resolution are observations rather than guessed defaults. Existing `scripts/m9/preflight.py` remains the metadata check; it is not proof that supplied assertions are true.

`runtimeImageVerified` must be supported by exported image configuration hashes plus later running-Pod comparison. Before first install, imported image identity can support the preflight input; after deployment, verify actual Pod identity and update evidence. Do not set this boolean merely to bypass a failing preflight or claim pre-install Pod verification. Root should clarify this two-stage distinction in the final design.

## Verification sequence and exact planned invocations

Commands below are planned from repository-root PowerShell; implement helpers before presenting them as runnable. An isolated M10 virtual environment must install pinned locks from the packaged source, rather than depend on old M6/M8 fixture environments.

1. Run focused controlled composition/lifecycle/guard tests:
   `.tools/m10/venv/Scripts/python.exe -m pytest tests/e2e -q -p no:cacheprovider --basetemp .tools/m10/pytest`
   Controlled tests prove Python contracts only. Test child lifespans, exact `/mcp` path without redirect, API/chat/health routes, body limits scoped to API rather than breaking MCP streaming, ready-before-recovery refusal, competing owner failure, owner-loss fencing, bounded drain and cleanup on startup failure. Real hosted upstream discovery failure must not fail overall readiness.
2. Run existing platform/gateway/chat suites after inspecting their real folders; run release/store checks. M9 `tests/release/test_preflight.py::test_examples_render_but_fail_deploy` currently assumes missing M10 entry points; change to an explicitly empty temporary root for that negative assertion. Preserve missing-entrypoint coverage instead of deleting the check. Existing build script must still reject missing runtime source and must build final `release`, never `checks`.
3. `.tools/m10/venv/Scripts/python.exe scripts/m9/check-m9.py --helm .tools/m1/helm.exe --output docs/evidence/m10/package-checks`
   Keep final-package evidence separate from historical M9 evidence. Inspect checker CLI first; optional private sentinel flags are operator-selected. Both profiles, alternate release/namespace, source-only staging and secret scanner checks must pass.
4. `./scripts/build-images.ps1 -Module All -ImagePrefix urumi -Tag m10`
   Record frozen runtime inputs and actual image config hashes; use observed tag-based k3d import with final chosen tags, then compare actual running identities. Do not repeat the known Windows archive-import failure path or trust exit code alone.
5. `.tools/m10/venv/Scripts/python.exe -m scripts.m9.preflight --mode deploy --values .tools/operator/m10/merged-values.yaml --inventory .tools/operator/m10/inventory.json --namespace urumi-m10`
   Required values/inventory are private operator inputs, not generated passing fixtures. Helm render review precedes any install; root alone applies accepted target. Secrets never appear on shell command lines, command evidence or captured raw YAML.
6. Live runner scenarios, designed as opt-in commands rather than one enormous mutating test: inventory/probes/images; browser accounts and CSRF/role boundaries; gateway three-upstream list and five Woo tools; revoke/disable; labelled upstream failure and restore; persistent restart; backup/restore. Use a CLI `--scenario` selector with target descriptor and preconditions. Read-only default; explicit scenario mutation ownership. Record exact observed command, timestamps, outcome and sanitized IDs after implementation. Never prefill PASS results.
7. Provider and external-client scenarios run only after explicit current free-plan/client/trust decisions. M7 command is `.tools/m6/venv/Scripts/python.exe scripts/m7/check-m7.py --live-provider --confirm-free-plan` historically; clean M10 reproduction must replace the environment prefix with new compatible pinned environment. That probe alone uses a fake gateway and cannot satisfy integrated C10-16.

## C10 evidence mapping

| Criteria | Inputs and required assertions | Safe evidence |
|---|---|---|
| 01 | Real PostgreSQL ownership/recovery; controlled contract failures plus live health/startup/shutdown | lifecycle results; readiness transitions; no raw exception secrets |
| 02 | Installation-scoped first-run record/marker; initial Woo default, restart, rename/disable/remove | stable server IDs and marker/state transitions; never absence-only recreation |
| 03 | Accepted target/profile/private inputs, final images, trusted stable URLs | Pods/claims/probes/resources/image config IDs; safe browser TLS observation |
| 04 | Browser checkout using COD; disposable synthetic customer data | same order ID in confirmation and Woo admin, redacted captures |
| 05 | A's real session/provider loop; exact approved product name/price; today's order bounds | product/order IDs, tool attempts and attributed audit IDs, Asia/Kolkata bounds |
| 06-07 | B key, external Codex plus Inspector, three upstreams, SKU DEMO-001 conflict check, actual Learn discovered call | client config with key placeholder; actual answer/attempt metadata, B audit IDs |
| 08 | Open MCP connection, selected B key and independent active control key | next-call denial and no dispatch; control success; no raw keys |
| 09-10 | Recorded prior enabled state/replicas; test-owned upstream | fresh and stale catalog behavior; unreachable status; healthy peer call; restoration proof |
| 11,15 | Real member/admin sessions and direct API negatives | request/audit correlation matrix, denied ownership/admin/CSRF checks, same-origin request metadata |
| 12 | Labelled data IDs and all three PVC identities | before/after restart rows/counts and IDs, readiness recovery, same disks |
| 13 | Real non-gateway diagnostic Pod and backend identity; dedicated Secret namespaces | explicit allowed/denied network and RBAC calls; remove only owned probe Pod |
| 14 | Disposable test order with known before-status | all five Woo tool audits; order-status before/after; no unrelated order mutations |
| 16 | Current free-account confirmation and real provider secret | M7 probe closure plus integrated tool attempts; quotas/failures honestly recorded |
| 17 | Packaged clean source, independent private inputs, consistent private backup and isolated restore target, real production-shaped TLS transport | actual install/restore counts/checksums and OAuth read/write; no dumps, credentials or VPS claim |
| 18 | Current docs/chart/source and finalized evidence | all 18 statuses, independent review, private handoff index, dummy-only example inputs |

## Remaining blockers before live work

The user's design-and-implement request authorizes code development, but does not supply the target choice, hostname/CA trust action, actual client availability or current Groq free-plan confirmation. Root can finish composition, controlled regressions, package validation and reviewable scripts while those decisions are pending. Actual deployment/provider/client/restore checks must retain NOT RUN/BLOCKED until their specific prerequisites are resolved. M8/M9 progression acceptance should be recorded from the user's current direction consistently with existing gates; do not invent acceptance evidence.

Inspect the existing Secret API implementation before choosing bootstrap execution placement. The current chart gives only backend ServiceAccount access to the dedicated namespace; root should choose an explicitly owned one-shot operator Pod or a stopped-owner process using that scoped identity and the existing operator helper. Do not introduce broad new RBAC or a public bootstrap route. No two processes may compete for the same database owner.

## Additional package-runner correction found during design

Do not run the existing M9 checker unchanged after M10 entry points appear. Its current real build-script rejection invocation would start Docker building in the live checkout and then assert that it should have failed. Run this negative only from a small temporary staging root containing the build script but missing backend entry points; set subprocess cwd there. Add a regression proving the missing-entrypoint error occurs before any Docker executable is needed. Update generated component/build inventory language to distinguish current runtime source availability from actual build/deployment proof.

The M9 checker's comparison to historical M6 runtime source hashes currently hard-fails on legitimate M10 integration fixes. Keep the old evidence untouched. In a new M10 output directory record a historical comparison with changed/new/missing paths and explicit `historical_baseline_only` scope; do not call differences PASS parity or fail current package correctness merely because M10 changed source. Actual M10 source freeze and running-image identity are the new proof. Preserve genuine current syntax/tests/build checks.

The current backend Docker release inherits `checks`, so it includes scripts/m5,m6,m7 and their harnesses unnecessarily. Minimal stage design: `runtime` installs the pinned lock, copies `backend` and `contracts`, creates UID10001 and sets runtime defaults; `checks` inherits runtime, copies existing check scripts and keeps its historical harness CMD; `release` inherits runtime, asserts the two entry points and uses `python -m backend.main`. Explicit `--target checks` callers remain compatible; default final stage remains release. Verify rendered command, Dockerfile structural assertions and existing check-target callers. Root owns actual Docker builds after review.
