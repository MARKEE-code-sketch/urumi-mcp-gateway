# M10 persistence and recovery scope

[Restart persistence](persistence.json) passed four separate WordPress/MariaDB/backend/PostgreSQL Pod replacements. Each replacement recovered before the next fault. Products12/18, orders16/19, attachment13 content hash and selected account/key/revocation/registry/audit records remained unchanged, as did all three persistent-claim identities. The original shop's seven tracked resource identities also remained unchanged. See the [persistence review](persistence-review.md) for exact commands and timings.

The [snapshot capture](recovery-capture.json) contains both databases, installed WordPress files, matching static/dynamic Secrets, configuration and reviewed image/value metadata. Capture ran only after the fresh test backend, WordPress and Woo MCP writer Pods were absent. Root restored their original one-replica settings in `finally` and waited for readiness. Database dumps used binary subprocess pipes, a PostgreSQL custom archive and a transactional MariaDB dump with passwords read from the existing mounted file. No plaintext dump or Secret object was written into evidence.

The private snapshot is encrypted with AES-GCM and a fresh random key; Windows DPAPI wraps that key for this Windows user and machine. Snapshot directory ACL permits only that user and SYSTEM. This is a local recovery rehearsal, not an off-machine backup. Copying the encrypted files to another machine alone does not make the DPAPI key recoverable; a production backup needs a separately designed secure key/destination procedure.

Restoration uses newly named `urumi-m10-recovery-<id>` namespaces, separate credential namespace and disposable `emptyDir` volumes. It starts only database/content Pods under deny-all network policies; there is no public Service/Ingress, backend or provider call. It compares complete platform-table row hashes/counts, deterministic shop data, WordPress file hashes/modes/ownership and matching Secret/reference state. Created object UIDs guard cleanup. It does not overwrite or cut over the working shop.

The [final isolated restore](recovery-restore.json) passed: all11 platform tables, complete deterministic MariaDB data, 9,289 WordPress files and matching Secret bytes agreed. There were zero active registry credential references in this installation, so that result does not claim a nonempty bearer/header-secret restore exercise. It proves data/file/Secret restoration, not a running restored application or automatic cutover.

The earlier attempts failed during WordPress archive extraction after the databases started/restored. The temporary volume root was root-owned; even with a writable group, GNU tar could not change its metadata as UID33. Restoring into a child directory created by UID33 corrected the rehearsal. Earlier failures remain historical evidence and were not counted as success; owned temporary namespaces were cleaned up.

Explicit restore command from repository-root PowerShell, using the already captured private snapshot:

```powershell
./.tools/m10/venv/Scripts/python.exe scripts/m10/recovery.py restore --context k3d-urumi --kubeconfig .tools/m1/kubeconfig.yaml --directory .tools/operator/m10/recovery/acceptance-20261020 --output docs/evidence/m10/recovery-restore.json
```

Do not run capture against active writers. `recovery.py capture` refuses when the three writer workloads are running. Replacing, rotating or restoring credentials separately from database/reference state can break a recovery point. Helm rollback restores chart configuration; it cannot undo database writes or migrations.
