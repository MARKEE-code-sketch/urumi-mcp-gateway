# M5 implementation evidence - 17 October 2026

**PASS: 12/12 specification groups after independent review.** There are **41 passing host tests** against real PostgreSQL and **11 passing live runtime checks**. User module acceptance remains pending; final gateway integration is outside this module.

[Acceptance results](acceptance-results.json) map the checks to the specification. [Independent review](acceptance-review.md) records a source/evidence assessment, not a claim that the reviewer reran commands. The raw [cluster result](cluster-results.json) keeps its original `PASS_RUNTIME_REVIEW_PENDING` status.

## What changed and why

M5 remembers users, invitations, fixed login sessions, personal hashed/revocable keys, upstream registrations and tool activity. These independently tested modules give later gateway code a verified caller and durable records. A restart must preserve account ownership and key revocation. Upstream credentials stay in owned Kubernetes Secrets; the database stores their references.

FastAPI owns agreed dashboard routes; Psycopg performs parameterized SQL transactions; Argon2id hashes passwords. Random session/invitation/key tokens persist only as hashes. Origin and session-bound CSRF checks protect changes. Registry updates save a durable operation intent before creating an immutable replacement Secret. Known canceled names remain as non-secret recovery tombstones. Audit adapters save running before execution and permit one honest terminal outcome. No M6/M7/M8 business logic or final M10 orchestrator was added.

The [runbook](runbook.md) explains each file, WHAT/WHY/HOW, reproducible isolated setup, operator bootstrap/reconciliation and migration/backup limits.

## Exact verification commands

Executed from the repository root in PowerShell:

```powershell
.tools/m5/venv/Scripts/python.exe -m pytest tests/backend -q --tb=short --assert=plain -p no:cacheprovider
.venv/Scripts/python.exe -m pip --python .tools/m5/venv/Scripts/python.exe check
docker build -t urumi/m5-harness:m5 -f backend/Dockerfile .
docker run --rm urumi/m5-harness:m5 python -m pip check
.tools/m1/k3d.exe image import urumi/m5-harness:m5 -c urumi
docker save urumi/m5-harness:m5 -o .tools/m45/m5-image.tar
.venv/Scripts/python.exe scripts/m4/image_identity.py .tools/m45/m5-image.tar --image urumi/m5-harness:m5 --output docs/evidence/m5/image-identity.json
.tools/m1/helm.exe upgrade --install urumi-m5-check deploy/charts/urumi --kubeconfig .tools/m1/kubeconfig.yaml --kube-context k3d-urumi -n urumi-m5-check -f tests/backend/values-check.yaml --set m5Harness.enabled=true --wait --timeout 180s
.tools/m5/venv/Scripts/python.exe scripts/m5/check-m5.py --cleanup
```

The migration helper source was executed through stdin in the existing harness Pod, with its private PostgreSQL environment. It created and removed a guarded separate disposable database. `scripts/m5/reset_fixtures.py` was executed on the host under exclusive ownership between checker attempts. These operator/test helpers were added after the tested runtime image build and were run on the host or through stdin; do not infer their inclusion in that earlier image. Future builds copy the current helper sources.

## Host and migration results

[Host output](host-tests.txt): **41 passed in 36.89 seconds**, with one upstream Starlette/AnyIO deprecation warning. Windows and Linux `pip check` reported no broken requirements. These tests used actual PostgreSQL through loopback forwarding, not SQLite.

Coverage includes concurrent first-admin bootstrap and invitation redemption; expiry/spent/invalid invitations; session rotation/logout/expiry; exact Origin/stable CSRF and cookie/key separation; own/other-user API permissions; hash-only keys with concurrent revocation; registry modes/retention/clear/status/slug/URL/header rules; real SQL trigger failures before intent/activation and after remote deletion; controlled delayed Secret creation with actual PostgreSQL lock loss; ownership/UID checks; audit visibility and abandoned/current-process recovery; and real SQL lock-timeout failures of initial/final audit writes. A blocked Secret request left process liveness responsive. Controlled Secret transport fixtures do not replace live RBAC evidence.

[Forward migration output](migration-preservation.json): schema **001 -> 002 passed**. Installation, user/password-hash, invitation, active/revoked session and active/revoked key rows remained exactly equal in private memory; the original password still verified and repeating migration preserved records. The disposable database was removed. No hashes or tokens were printed.

## Live runtime observations

The final [live checker](cluster-results.json) exited zero with all **11 runtime groups passing**:

- A real bootstrap Secret established the admin and was removed. Invitations, sessions, roles, CSRF and personal keys worked through the API.
- A real Secret-backed registration persisted; disabling and ownership/URL restrictions held.
- The actual ServiceAccount created/read/updated owned metadata/deleted credentials. Wrong UID deletion returned **409**. Secret list/watch, foreign namespace reads and workload access returned **403**. Foreign ownership was rejected. [RBAC declarations](secret-rbac.json) and [nine permission checks](auth-can-i.json) supplement the actual calls.
- During **15 seconds** of database outage, process liveness stayed 200, readiness became 503 and the harness did not repeatedly restart. After database recovery, the supervisor restarted once, from count 0 to 1, to regain exclusive ownership.
- The database Pod UID changed while PVC UID **210de06f-ccba-483d-a8b4-af4c7bf3b474** stayed the same. Full private user/invitation/session/key/registry rows remained exactly equal; the actual upstream credential resolved and matched. A separate harness Pod replacement preserved the same records and revocations.
- The actual key/session validators rejected revoked credentials and accepted active ones after replacement. Artificial running activity became unknown; a separate artificial attempt used the real audit module. These are explicitly synthetic activity fixtures, not upstream tool calls.
- A binary-safe `pg_dump` was restored into a separate disposable database: six table counts and active/revoked flags matched. The restored database was removed; the private dump remains only in ignored `.tools`.
- **32 saved evidence files** were scanned against actual generated credential/session/key values: **zero matches**. Logs contained no such values. Services were ClusterIP with no Ingress; probes and requests/limits were present.
- Both positively owned disposable namespaces were removed. Original `urumi` store resource and PVC identities remained unchanged.

The runtime image configuration digest **074b749942232c24870d63ea86140eab7f961ebfceac0c53194305ce1be755c6** matched the deployed Pod image ID. PostgreSQL was **17.11**, pinned to `sha256:3645570cccdfa447589da9f57dd740faa29b30938e861289a5574b6ca6b03826`; the Python 3.13.5 base was pinned to `sha256:4c2cf9917bd1cbacc5e9b07320025bdb7cdf2df7b0ceaccb55e9dd7e30987419`. [Image proof](runtime-image-check.json), [resource proof](cluster-resource-settings.json), [local render](render-local.yaml.txt) and [production render](render-prod.yaml.txt) are inspectable. No existing M3 environment was changed.

## Preserved checker failures

The first run observed container restart before the forwarded process was listening and reported a recovery failure. Direct health subsequently confirmed the application was Ready; [initial failure](cluster-results-initial.json), recovery observations and events remain saved. A resumed 17 October run exceeded the checker's 12-second client read timeout; its registration had committed and logs were empty. [Second failure](cluster-results-second-timeout.json) remains saved.

Only the checker changed: dead-forward recovery, a 45-second read timeout, safe action context and stronger private row/UID proof. No application code was changed to obtain the final runtime pass. Each retry cleared only disposable fixture rows under verified namespace/database identity and exclusive ownership, preserving schema, installation and PVC. A timeout was not automatically retried as an uncertain write.

## Limits and next gate

M5 supports one worker/replica. Canceled Secret names remain indefinitely for bounded rotating reconciliation; cleanup uses ownership and UID checks rather than namespace-wide listing/deletion. A postcommit retirement failure keeps the new usable credential plus cleanup intent and returns safe 503. Failed audit finalization stays honest until exclusive recovery can save unknown.

The isolated harness used an internal HTTP Service with HTTPS-origin/Secure-cookie settings and explicit in-memory cookies over loopback forwarding. This proves backend behavior, not browser TLS or dashboard pages. Registration validation alone is not complete SSRF protection. M6 must enforce resolved destinations, redirects, actual dispatch and revocation within existing MCP sessions; M8 supplies browser pages; M10 provides final wiring and the two-user demonstration. Live VPS deployment is unverified. Helm rollback does not undo SQL migrations or restore data.

Review this module's evidence for acceptance before proceeding to another module.
