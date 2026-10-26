# Clean source installation and one-time builtin registration

**Result: PASS.** Clean installation, real fresh-store MCP read, durable builtin
registration checks, current-image post-upgrade verification and guarded cleanup
completed. The remaining handoff/video acceptance is separate.

The disposable `urumi-m10-clean` installation started from a source-only package,
fresh credentials and three empty PVCs. It used the same Helm chart as the working
release, with explicit local overrides. No original shop was upgraded or deleted,
and no LLM/provider request was made.

## Observed installation and registration checks

- Staged chart lint, render and deploy preflight passed with separately supplied
  names/types/key-names inventory and private operator inputs.
- The source store bootstrap created a fresh demonstration product and REST key;
  its temporary Job was removed. A new administrator was established while the
  disposable backend owner was stopped; the one-time bootstrap Secret was removed.
- Seven real workloads became Ready and three separate PVCs became Bound.
- Trusted HTTPS served the real dashboard and accepted the new administrator login.
- A temporary administrator key initialized the real gateway MCP connection and
  read one actual WooCommerce product using the fresh REST credentials. The key
  was revoked afterward. See [earlier live read](runtime-before-builtin-finish.json).
- Builtin WooCommerce ID `dfa4a742-5e51-44aa-b985-032faf2704c2` was edited and
  disabled through the API. Its same ID and settings remained after a backend
  restart. It was then deleted through the API; another backend restart preserved
  its absence and the same durable initialization marker. See [runtime](runtime.json).

## Source, images and explicit prerequisites

[Source manifest](source-manifest.json) records the actual packaged filenames and
SHA-256 values. Private/generated trees, virtual environments, kubeconfig and
`node_modules` were excluded. The handoff allowlist was corrected to retain
`.mjs` browser helpers, infrastructure files and dependency `.in` inputs.

Cached release images were explicit immutable inputs, not historical fixture
images. [Image/source parity](image-source-parity.json) distinguishes frozen build
inputs for frontend/backend from independently read contained source bytes for
WooCommerce MCP, Inventory MCP and the store. No unchanged application image was
rebuilt just for this rehearsal. MariaDB and PostgreSQL were separately pinned
external image dependencies. Runtime `status.image` may show a canonical tag;
the chart declares digest references and actual `imageID` identifies the artifact.

Operator prerequisites were supplied outside the package: Python 3.13, kubectl,
Helm 3.21.3, explicit `k3d-urumi` kubeconfig, already available immutable images,
and the existing trusted constrained development CA. A new private operator
virtual environment installed staged-equivalent `backend/requirements.lock.txt`
plus `PyYAML==6.0.3`; `pip check` passed. No previous `.tools` Python environment
or historical fixture image was needed by the staged runtime/helper execution.
The external executable/kubeconfig paths happened to live in the operator's
existing tools directory; they were explicit prerequisites, not copied source.

Fresh private values and leaf keys stayed under an access-restricted operator
directory. A dummy provider key was used because this rehearsal never calls chat.
Only a new leaf certificate was signed; hostname resolution was overridden inside
the check process while preserving TLS SNI and certificate verification. No hosts
file or trust-store change was made for this clean target.

## Commands and recovery observations

From the source-only staged directory, with every operator path absolute:

```powershell
& <fresh-operator-python> scripts/m10/clean_install.py --action install `
  --context k3d-urumi --private-dir <protected-clean-directory> `
  --kubeconfig <operator-kubeconfig> --helm <helm-executable> `
  --input-values <digest-pinned-merged-values> --inventory <names-only-inventory> `
  --ca-cert <trusted-ca-certificate> --ca-key <protected-ca-signing-key> `
  --output <evidence-directory>/runtime.json
```

`--action resume` continues verification after a completed bootstrap; it never
replays namespace/Secret/store/admin provisioning. `--action finish-builtin`
requires the observed edited/disabled ID, earlier real MCP read, and changed Pod
UID before performing the remaining delete and restart checks. These modes were
used after the following actual failures; initial evidence was retained:

1. The first verifier selected PVCs by an instance label that the platform PVC
   does not have. Verification now reads all three exact names and checks Helm
   owner annotations and UIDs. No chart label was changed to hide this mismatch.
2. Strict TLS rejected the new leaf's missing Authority Key Identifier. The
   helper was corrected and only the disposable TLS Secret was replaced while
   preserving UID/resourceVersion. Certificate verification stayed enabled.
3. Post-restart API access returned 503. A read-only inspection confirmed the
   same edited/disabled builtin row. Safe GET-only convergence retries were added;
   PATCH/DELETE were not automatically replayed.
4. Root completed the guarded remaining builtin checks after correcting operator
   absolute paths and restarting a stalled disposable backend Pod. The precise
   cause of that stalled Pod was not established. This is not proof that every
   earlier 503 had a single diagnosed cause.

The fresh installation initially used the earlier reviewed backend image. A
separate reproduced monitor-adapter recovery defect subsequently received a
small reviewed fix. The same chart upgrades this clean target to the new frozen
image. Both working and disposable releases became seven-of-seven Ready on the
new artifact; see [canonical upgrade evidence](../monitor-fix-runtime.json).
The [post-upgrade check](post-upgrade.json) independently verified all 41 current
frozen backend/contracts source files inside the actual clean Pod, strict HTTPS
login, no recreated builtin row and the same persisted marker. Its declared
image is digest-pinned; actual image ID is
`sha256:2c842ad25e4e09f3ffd5a2ae515942e1bf51f2e2df42250e7ee24c7dab20aabe`.
The current source package contains 267 files. Earlier package/image provenance
is preserved in `source-manifest-before-monitor-fix.json` and
`image-source-parity-before-monitor-fix.json`. This distinction avoids claiming
the first empty-storage boot used the later image.

An image parity/upgrade operation stalled while Docker/Kubernetes became
unresponsive across the overnight interruption. No clean deletion was attempted
during that outage. Verification and cleanup resumed only after root recovered
the API and both upgraded releases were observed healthy. This does not establish
the precise underlying cause of the host/API interruption.

## Cleanup and limits

[Cleanup guard tests](cleanup-guard-tests.txt): **10 passed**, including negative
ownership/UID/name cases that performed no uninstall/delete. Cleanup requires the
exact recorded namespace UID, Helm ownership and all three claim UIDs; raw API
deletions include UID preconditions. Only this disposable release and its own
PVCs/namespaces may be removed.

[Cleanup](cleanup.json): **PASS, five checks**. The exact clean Helm release was
uninstalled, all three recorded claims were removed with UID preconditions, and
both `urumi-m10-clean` and `urumi-m10-clean-secrets` namespaces were observed absent.
The original shop and working `urumi-m10` release were outside every deletion
target. Final project checks separately recheck their readiness and identities.

The cleanup command used the same absolute external arguments shown above, with
`--action cleanup` and `--output <evidence-directory>/cleanup.json`, from the final
source-only stage. No provider call, product/order mutation or new trust/hosts
change was performed during final verification or cleanup.

The separate backup restore and production-shaped Woo HTTPS/OAuth observations
belong to their own evidence. This report does not claim a VPS deployment, video,
private repository publication or final submission handoff.
