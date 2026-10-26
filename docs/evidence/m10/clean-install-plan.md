# C10-17 clean source installation rehearsal

This is a disposable second installation, not an upgrade of either existing shop.
It proves that the packaged chart/source, explicitly supplied operator inputs and
immutable release images can start from empty storage. No provider call is needed.

1. Create a source-only stage using the reviewed M9 handoff roots. Record every
   relative filename and SHA-256. Reject `.tools`, virtual environments,
   `node_modules`, `.env`, kubeconfigs, generated output and private files. Execute
   Helm and repository helpers with this stage as their working/source directory.
   Supply Python, Helm, kubectl and kubeconfig as explicit external prerequisites;
   create a fresh operator virtual environment from staged pinned dependency files.
2. Use release/application namespace `urumi-m10-clean` and credential namespace
   `urumi-m10-clean-secrets`. Require both names absent before creation. Generate
   separate random database, administrator, store REST and WordPress salt inputs
   under a restricted private operator directory. Use a syntactically valid dummy
   provider key and never call chat; do not copy the working release's credentials.
3. Supply explicit images pinned by manifest digest for all seven workloads.
   For the five application images, compare staged build-input hashes with the
   recorded immutable image provenance. Rebuild from the stage if comparison
   fails; do not substitute an old fixture/check image. Database images remain
   explicit pinned external dependencies. No provider/registry publication occurs.
4. Use `dashboard-m10-clean.urumi.test` and `shop-m10-clean.urumi.test`. Sign only a
   new leaf certificate using the already trusted constrained local CA. Keep its
   private key outside source/evidence; do not install another CA. Resolve only
   these names inside the verification process while preserving TLS Host/SNI.
   Do not change the machine hosts file or trust store for this rehearsal.
5. Render the staged same Helm chart with local values plus explicit private
   overrides; run deploy preflight against names/types/key-names inventory.
   Apply only the two fresh namespaces and their separately supplied Secrets,
   then install the exact `urumi-m10-clean` release with three new PVCs. Record
   namespace/PVC UIDs so cleanup cannot target another release.
6. Initialize the fresh store using the source-owned WooCommerce bootstrap and
   establish the first platform administrator using the existing operator
   bootstrap while the new backend is stopped. Helpers need explicit scoped
   namespace/release/input arguments rather than the original hardcoded target.
   Verify seven real workloads Ready, three PVCs Bound, immutable Pod image IDs,
   successful trusted HTTPS dashboard login, and real Woo tool discovery/read.
7. Close C10-02 one-time registration on this disposable database: record exactly
   one builtin WooCommerce row and its marker; edit its display name and disable
   it through the authenticated API; restart only this backend; verify the same
   row ID and edited/disabled state. Delete that row through the API; restart only
   this backend again; verify absence and persisted marker. No direct database
   mutation substitutes for these observed API/restart checks.
8. Clean up only after recording checks: require exact release, namespace UID and
   ownership label; uninstall that release; explicitly remove its three retained
   PVCs and two owned namespaces. Verify
   absence and compare the pre-existing releases' namespace/PVC identities and
   readiness. Delete no original or working release data. Report failed phases
   honestly; do not claim a clean install from Helm rendering alone.

Safe evidence contains source hashes, versions, command templates, object IDs,
image IDs, readiness/status counts, login success booleans, builtin row ID/state,
marker existence and cleanup checks. It excludes passwords, API keys, certificates'
private keys, cookies, raw environment, dumps and raw failing command output.

The isolated backup-restore rehearsal and production-shaped HTTPS/OAuth read/write
remain separately evidenced C10-17 checks. This clean target does not repeat them
or claim a VPS deployment.
