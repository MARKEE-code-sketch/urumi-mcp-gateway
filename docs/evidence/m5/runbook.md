# M5: learning and operating notes

**Verified 17 October 2026:** 41 real-PostgreSQL host tests, 11 live runtime checks and all 12 specification groups passed independent review. Both disposable namespaces were cleaned; user module acceptance is pending. See the [report](report.md), [acceptance results](acceptance-results.json) and [independent review](acceptance-review.md). Repeating live checks requires the fresh isolated setup below.

## WHAT, WHY, HOW

**WHAT:** The platform remembers people, login sessions, personal gateway keys, registered upstream servers and tool activity.

**WHY:** A restart must not forget who owns a key or undo its revocation. A member must not gain admin permission by changing a URL or JSON field. An upstream credential must stay behind the backend.

**HOW:** FastAPI receives a dashboard request. The identity module verifies the session cookie and current role. A changing request must also present the correct Origin and session CSRF value. A small module performs its permitted database transaction and returns only safe fields. Registry credentials go into an owned Kubernetes Secret; PostgreSQL stores the reference. Later gateway execution will use these adapters, but M5 itself dispatches no tool.

A PostgreSQL PVC is like a Docker named volume: replacing the container/Pod preserves the records on its disk. A ServiceAccount is the backend Pod's Kubernetes identity. Its Role is a short permission list: dynamic Secret operations in one dedicated namespace, with no access to the shop credentials or workloads.

## File walkthrough

| File | Responsibility |
|---|---|
| `backend/db/database.py` | Bounded connections, SQL migrations, lifecycle ownership and per-server locks. |
| `backend/db/migrations/001_initial.sql` | Account/session/key, registry-operation and audit tables/constraints. |
| `backend/db/migrations/002_canceled_secret_names.sql` | Retained non-secret names for an ambiguously completed remote creation. |
| `backend/identity/auth.py` | Argon2id password verification, sessions, stable CSRF, trusted principal and revalidation. |
| `backend/identity/members.py` | Admin invitations, atomic redemption and member listing. |
| `backend/identity/api_keys.py` | One-time key output, whole-key hashing/verification, ownership and revocation. |
| `backend/registry/servers.py` | Validated registry CRUD, staged credential changes and bounded recovery. |
| `backend/registry/secret_store.py` | Only positively owned Secret reads/writes/deletes; UID-guarded cleanup. |
| `backend/audit/records.py` | Durable attempts, conditional finalization, honest unknown recovery and filtered reads. |
| `backend/api.py` | Agreed M5 routes, safe error envelope, body limit and browser protection. |
| `scripts/m5/harness.py` | Isolated test composition and ownership-loss supervisor; final wiring remains M10. |
| `scripts/m5/operator.py` | Explicit bootstrap and reconciliation commands. |
| `tests/backend/` | Independently checked identity, registry, audit, API and supervisor behavior. |

## Repeat isolated checks safely

Use **PowerShell**, from the repository root. The host test fixture deliberately clears isolated fixture tables and requires exclusive lifecycle ownership. Do not run it while the M5 harness owns that same database. Do not point it at production or the shop.

After acceptance cleanup has removed the disposable namespaces, recreate the isolated setup in this order. Docker Desktop and the existing `k3d-urumi` cluster must be running. The commands use only the isolated release/namespaces; they do not upgrade the real `urumi` release.

1. If the M5 environment is absent, create it and install the pinned dependencies. The `pip --python` form also handles this machine's `venv`/`ensurepip` limitation:

```powershell
.venv/Scripts/python.exe -m venv --without-pip .tools/m5/venv
.venv/Scripts/python.exe -m pip --python .tools/m5/venv/Scripts/python.exe install -r backend/requirements.lock.txt
```

2. Prepare owned namespaces/throwaway credentials, then deploy only database and access resources:

```powershell
.tools/m5/venv/Scripts/python.exe -m scripts.m5.prepare
.tools/m1/helm.exe upgrade --install urumi-m5-check deploy/charts/urumi --namespace urumi-m5-check --kubeconfig .tools/m1/kubeconfig.yaml --kube-context k3d-urumi -f tests/backend/values-check.yaml --wait --timeout 3m
```

The original host tests used a loopback PostgreSQL port forward:

```powershell
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi-m5-check port-forward --address 127.0.0.1 service/urumi-m5-check-platform-db 15435:5432
```

In a separate PowerShell window, once the isolated harness is stopped and the private `.tools/m5/db.json` fixture exists:

```powershell
.tools/m5/venv/Scripts/python.exe -m pytest tests/backend -q --tb=short --assert=plain -p no:cacheprovider
.venv/Scripts/python.exe -m pip --python .tools/m5/venv/Scripts/python.exe check
```

3. After the tests pass, reset only their fixture records while the loopback database forward is still running. The helper verifies namespace ownership and compares the forwarded installation ID with the actual isolated Pod, then obtains exclusive lifecycle ownership before clearing the known fixture tables:

```powershell
.tools/m5/venv/Scripts/python.exe -m scripts.m5.reset_fixtures
```

Stop that port-forward window with Ctrl+C. Build/import the harness image and enable it in the isolated release:

```powershell
docker build --target checks -f backend/Dockerfile -t urumi/m5-harness:m5 .
.tools/m1/k3d.exe image import urumi/m5-harness:m5 --cluster urumi
.tools/m1/helm.exe upgrade --install urumi-m5-check deploy/charts/urumi --namespace urumi-m5-check --kubeconfig .tools/m1/kubeconfig.yaml --kube-context k3d-urumi -f tests/backend/values-check.yaml --set m5Harness.enabled=true --wait --timeout 3m
.tools/m5/venv/Scripts/python.exe scripts/m5/check-m5.py --cleanup
```

The live runner starts with zero users, generates private test credentials, proves the independent API/RBAC/restart checks and removes only positively owned disposable resources. Inspect its final result artifact; a failed command is not acceptance. Its cleanup also deletes disposable M5 storage, after persistence checks; the actual shop's retained volumes remain outside its target. Repeating live acceptance requires this fresh setup again rather than reusing prior test users.

The assertion mode avoids displaying dynamic credential-bearing values in failure explanations. The committed host evidence is from the completed test run, followed by a guarded fixture reset for fresh live bootstrap.

To inspect the isolated workloads without printing Secret contents:

```powershell
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi-m5-check get pods,deployments,services,pvc
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi-m5-check describe deployment urumi-m5-check-platform-db
```

Do not run `kubectl get secret -o yaml/json` in a shared log. Base64 is an encoding, not encryption.

## First admin and reconciliation

An operator provisions a Kubernetes Secret containing `email` and `password` through a private process. Never pass the password on a shell command line. The bootstrap helper receives only the Secret's name, reads its values in memory, serializes first-admin creation and deletes that exact Secret with a UID precondition after success. It never resets a saved password. The operator needs separate bootstrap Secret permission; the backend ServiceAccount does not receive it.

With PostgreSQL connection settings supplied privately through the process environment (`PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, `PGPASSWORD`), the command shape is:

```powershell
.tools/m5/venv/Scripts/python.exe -m scripts.m5.operator bootstrap --secret YOUR_BOOTSTRAP_SECRET --namespace YOUR_PLATFORM_NAMESPACE --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi
```

If admin creation commits but deleting the bootstrap Secret fails, the command reports safe failure and remains retryable; repeated bootstrap preserves the original account/password.

Registry reconciliation runs at exclusive startup. An operator can repeat a finite pass with the harness stopped, using the backend's in-cluster environment/ServiceAccount and `M5_SECRET_NAMESPACE`/`M5_INTERNAL_URLS` settings:

```text
python -m scripts.m5.operator reconcile
```

It checks at most 100 pending operations and 100 rotating canceled names per pass. Prepared operations roll back their staged credentials; committed operations retire the old credential; removal stays disabled until cleanup completes. Non-secret canceled-name tombstones remain indefinitely, allowing later safe cleanup if a timed-out creation completes late. Cleanup never lists the namespace or deletes objects without matching ownership.

## Upgrades, backups and rollback limits

Migrations 001 and 002 run transactionally under a migration lock. They are repeatable at the migration-runner level: applied versions are preserved, missing supported versions apply once, unsupported versions fail closed. PostgreSQL itself stores passwords only as Argon2id hashes and personal/invite/session credentials only as token hashes. Treat database backups as sensitive because they contain those hashes and account metadata.

Before upgrading, take a database backup through an operator-controlled process, save it outside source/submission artifacts, and restore it into a **separate disposable database** to verify it. The PostgreSQL tools are `pg_dump` and `pg_restore`; use custom format (`pg_dump -Fc`) when preserving binary bytes. Windows PowerShell 5 redirection can corrupt binary output: use a binary-safe process/file API or a container file followed by `kubectl cp`. Do not paste dump contents into tool logs. Also back up the dedicated dynamic-Secret namespace through the separately approved secure secret process; a DB dump alone cannot recreate credential values.

Helm rollback changes workload configuration; it does not reverse SQL migrations or restore lost data. M5 migrations are additive/forward-only. A future destructive migration requires a reviewed backup and restore plan. Actual backup/restore verification is only claimed when its recorded evidence exists.

## What remains for later modules

M6 must revalidate before every dispatch, enforce resolved URL destinations/no redirects, and coordinate actual audit begin/finalization. M7 passes the current signed-in user through that same execution path. M8 supplies browser pages. M10 wires the real application and proves the two-user flow. The M5 isolated HTTPS-origin cookie checks do not claim browser TLS, a dashboard, a working MCP gateway or the full assignment.
