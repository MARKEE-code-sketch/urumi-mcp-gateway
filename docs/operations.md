# Operating guide

These commands run from the repository root. **Windows commands use PowerShell; VPS commands explicitly use Linux shell.** M9 performed static package checks only. M10 subsequently installed the separate `urumi-m10` release and observed real browser/client/provider, security, controlled outage and restart-persistence checks. See the [current evidence](evidence/m10/live-report.md) and [ledger](evidence/m10/acceptance-results.json) for exact scope. Do not apply the full example release to the retained `urumi` shop as a packaging test.

## Confirm the target before any change

In PowerShell choose an explicit context/namespace/release and inspect them before proceeding:

```powershell
$context = 'k3d-urumi'
$namespace = 'urumi'
$release = 'urumi'
kubectl --context $context -n $namespace get pods,services,pvc
helm history $release --kube-context $context --namespace $namespace
```

These are read-only. On a VPS use Linux shell variables (`context=...`, `namespace=...`, `release=...`) and `"$context"` quoting. Never infer the destructive target from a current default context. Check resource identities/labels and recovery plan before changing an existing deployment. Do not delete PVCs to retry installation.

## Private input inventory and deployment preflight

Keep Secret values, operator overrides, keys and backups outside source/submission. A Kubernetes Secret is base64-encoded, not inherently encrypted at rest. Provision through your reviewed private operator process; avoid shell history, argument-list passwords, `kubectl get secret -o yaml` and shared logs. This guide lists names/types/key names only; the chart never generates credentials.

| Default Secret | Type / keys | Consumer |
|---|---|---|
| urumi-store-db | Opaque: database-password, root-password | WordPress/MariaDB; root only database/operator. |
| urumi-store-salts | Opaque: AUTH_KEY, SECURE_AUTH_KEY, LOGGED_IN_KEY, NONCE_KEY, AUTH_SALT, SECURE_AUTH_SALT, LOGGED_IN_SALT, NONCE_SALT | WordPress read-only mounted files. |
| urumi-store-admin | Opaque: username, email, password | Existing store operator bootstrap only. |
| urumi-woocommerce-rest | Opaque: consumer-key, consumer-secret | Woo MCP only. |
| urumi-platform-db | Opaque: password | PostgreSQL/backend PGPASSWORD. |
| urumi-groq | Opaque: api-key | Backend GROQ_API_KEY only. |
| urumi-dashboard-tls / production urumi-shop-tls | kubernetes.io/tls: tls.crt, tls.key | Ingress controller. |
| Production urumi-registry | kubernetes.io/dockerconfigjson: .dockerconfigjson | Kubernetes image pulls only. |
| Explicit operator bootstrap Secret | Opaque: email, password | M5 host operator helper, removed with UID guard. |
| Dynamic urumi-upstream-UUID | Opaque: value | M5 owned immutable credential Secret in dedicated namespace. |

The dedicated namespace defaults to `urumi-upstream-secrets`, differs from app/system namespaces and must be unique per installation. Backend ServiceAccount has get/create/update/delete Secret permission there only; it cannot read static/provider/bootstrap Secrets from the application namespace through the Kubernetes API. Backend's provider/password env references are mounted by Kubernetes. Retain the dynamic namespace and matching database installation ID/references during recovery. A second release must use a different namespace. Helm keep prevents automatic namespace removal; reinstall must account for retained ownership metadata and existing objects rather than blindly adopting/deleting them.

Use [preflight.py](../scripts/m9/preflight.py) with a merged non-secret values file and a private **metadata-only** inventory. Inventory fields are `secrets` (list of exact `{name,type,keys}` records), `certificates` (list of `{host,trusted:true}` checks), `storageClasses` (names), `ingress` (`namespace,podLabels,tlsTargetPort,serviceIP`), `apiServerCidrs`, `runtimeImageVerified` and `wooProxyVerified`. No Secret `data`/`stringData`/values are accepted. Match Secret entries to the table using actual override names. Render mode allows marked examples; deploy mode requires final files/runtime-image verification, real image digests/provenance, verified storage/TLS/API/ingress and production proxy confirmation. Even a passing metadata fixture does not establish real credential validity.

```powershell
./.tools/m9/venv/Scripts/python.exe scripts/m9/preflight.py --mode deploy --values .tools/operator/merged-values.yaml --inventory .tools/operator/inventory.json --namespace urumi
```

All example `.example.com`, `replace-*`, documentation IP and `m10-unavailable` inputs must be resolved. API egress uses actual endpoint host `/32` or `/128` CIDRs and target port, not broad private-network allowances. Verify Service DNAT/CNI behavior at M10. For production Woo, resolve the shop hostname to actual Traefik ClusterIP through hostAliases, verify target8443 or override it, inspect retained `wp-config.php` trusted-forwarded-scheme handling and Traefik header overwriting. Recheck after Service recreation. No `verify=False`, fake proxy header, Basic-auth switch or public hairpin dependency is substituted.

## Startup, bootstrap and rotation

M10 implements migration lock -> exclusive database owner -> service construction -> audit/credential recovery -> one-time Woo upstream initialization -> discovery -> serving. One replica/worker and Recreate permit brief upgrade downtime. Readiness waits for startup/database/current ownership; an unreachable upstream does not itself make the whole backend unready. Owner loss fences dispatch and needs supervised restart/recovery. The chart runs `backend.main`; the release image excludes M5/M6 test harnesses. Verify the actual installed image and behavior before declaring acceptance.

The existing M5 operator helper is `python -m scripts.m5.operator bootstrap --secret NAME --namespace NAMESPACE --kubeconfig PATH --context CONTEXT`. Run only as the explicit operator with PGHOST/PGPORT/PGUSER/PGDATABASE/PGPASSWORD loaded privately into process environment; do not echo them. It migrates, creates the initial admin and removes the original bootstrap Secret with a UID precondition. A failure after admin creation requires private cleanup review, not an automatic password reset. No initContainer/Helm hook boots/reset users. Existing [M5 runbook](evidence/m5/runbook.md) owns the isolated procedure; final DB access/bootstrap scheduling is M10.

The existing `python -m scripts.m5.operator reconcile` additionally uses operator-provided M5_SECRET_NAMESPACE/M5_INTERNAL_URLS and in-cluster Secret API credentials. **Stop/drain the backend owner first** so reconciliation cannot compete for ownership; review its execution environment before use. These are helper inputs, not final-backend runtime names. Final packaging uses URUMI_SECRET_NAMESPACE/URUMI_INTERNAL_URLS. Rotate upstream credentials through the owned M5 workflow; do not directly overwrite immutable dynamic Secrets. Coordinate static database/password, Woo, provider, TLS and image-pull rotation with their consumers and recheck safe health/calls. Never erase audit history as a rotation step.

## Backups: one consistent recovery point

Schedule a maintenance window: stop new chat/tool/store writes and checkout, drain/stop backend, then take custom-format PostgreSQL dump, transactional MariaDB dump and WordPress-content archive while writes remain stopped. Privately preserve matching static/dynamic Secrets, installation ownership/configuration, chart/values/image digests, database schema and timestamps. A dump without its credential-reference state can be unrestorable. Backup credentials and data are sensitive; store encrypted, access-restricted and off-machine, outside repository/evidence. Three PVCs on local-path are not off-machine backups.

Use binary-safe transfer. **Do not use PowerShell `>` for binary `pg_dump -Fc` or tar output.** One explicit operator pattern uses Python subprocess with `stdout` opened in binary mode, checks return code and removes/marks incomplete files privately:

```python
# Operator example only; run after a reviewed maintenance plan and private path selection.
import subprocess
from pathlib import Path
command = ['kubectl', '--context', 'REVIEWED_CONTEXT', '-n', 'REVIEWED_NAMESPACE',
           'exec', 'REVIEWED_POSTGRES_POD', '--', 'pg_dump', '-U', 'urumi', '-d', 'urumi', '-Fc']
with Path('PRIVATE_BACKUP_PATH').open('wb') as output:
    result = subprocess.run(command, stdout=output, stderr=subprocess.PIPE)
if result.returncode:
    raise RuntimeError('Backup incomplete; inspect private error output without sharing credentials.')
```

For MariaDB, use the existing mounted password file through an in-container private options file rather than a command-line password; invoke `mariadb-dump --single-transaction` with that private options file and binary-safe output capture. Verify transactional-table assumptions; during the maintenance window no DDL/writes may invalidate consistency. Archive `/var/www/html` with ownership/permissions, capture checksums privately and inspect dump/archive integrity. No backup command has been executed by M9. Linux shell redirection is byte-preserving, but always check process exits and never treat a nonempty file as proof of restore success.

## Restore first into an isolated target

Never run generic restore commands over retained `urumi`. Create an explicitly approved isolated namespace/storage target, separate dedicated Secret namespace and no public Ingress. Restore matching database dumps and WordPress content, corresponding static/dynamic Secrets/configuration and ownership IDs. Check file UID/GID/permissions, schema/image compatibility, data counts, credential-reference consistency and scoped product/order operations. A second running installation must not share the original Secret namespace or disks. M10 must rehearse this and capture safe checksums/counts before a separately reviewed cutover. A successful dump is not proof of recoverability.

## Upgrade and rollback

Record `helm history`, selected chart/revision, exact values, image digests and completed coordinated backup before any upgrade. Review forward-migration compatibility and maintenance downtime. Inspect a same-chart render/preflight, then deploy reviewed store/MCP/backend/dashboard changes in the accepted M10 procedure, wait for probes and verify scoped calls/audits/checkout. Only the one backend startup owner runs migrations. Do not run a competing migration job or password reset.

In PowerShell, the rollback form is `helm rollback $release REVIEWED_REVISION --kube-context $context --namespace $namespace --wait --timeout 5m`. Replace REVIEWED_REVISION only after verifying its chart/image is compatible with the current schema/data. **Helm rollback cannot undo migrations, database writes, deleted credentials or disk deletion.** An incompatible schema requires reviewed forward repair or isolated backup restore/cutover. M9 did not execute upgrade/rollback/restore. Uninstall is not a reset: keep annotations retain PVCs/dynamic namespace, StorageClass reclaim policies govern underlying volumes, and retained ownership may require careful reinstall handling. Never prescribe disk deletion to resolve a Pending Pod.

## Troubleshooting without leaking secrets

### Local Kubernetes API address changes

The backend stores upstream credentials in Kubernetes Secrets. Its network policy allows the Kubernetes API's exact address; a Docker/k3d restart can change that address, like a Docker container receiving a new IP. The Helm value `backend.networkPolicy.apiServerCidrs` must match the currently observed API endpoint, rather than a copied historical address.

Read-only checks from repository-root PowerShell for the installed local release:

```powershell
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n default get endpoints kubernetes
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi-m10 get networkpolicy urumi-m10-backend -o yaml
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi-m10 get pods
```

Compare the API endpoint's IP/port with the policy's exact API `/32`/port. Do not open the whole private network. A mismatch can prevent credential storage and leave a prepared server-registration operation; readiness then intentionally stays unavailable until recovery. Have the operator capture registry/pending-operation metadata, update only the verified endpoint CIDR through the same Helm chart and current values, then restart only the backend to run existing startup recovery. Do not delete a pending database row or reset shop/platform data. A prepared new registration is rolled back, so re-enter its credentials only after the server list is healthy. A committed operation may instead be completed by recovery; inspect state before retrying.

Observed25October2026: API endpoint changed from172.18.0.2 to172.18.0.3; exact CIDR correction and backend startup recovery restored the gateway. This is a values/environment repair, not proof that addresses stay fixed after future restarts. [Incident evidence](evidence/fixes/server-registration-20261025/report.md).

Read scoped Pod/Service/PVC state and events first. Probe failure can indicate startup/ownership/database problems; Pending PVC means storage provisioning, not an application bug. Check internal DNS and exact policy selectors/ports, actual Traefik/API endpoint mapping, registry access and provider quota/availability. Backend traffic can reach healthy peers while one upstream is Unreachable. Preserve request/audit IDs and sanitized status/error codes; avoid raw tool/provider payloads, environment dumps and Secret YAML. The M9 chart checks verify structure only. Live policy denial/recovery, HTTPS, production OAuth, complete startup and external-client compatibility require M10 evidence.
