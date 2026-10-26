# M2 specification — our persistent online shop

**Status:** Implementation and verification complete; ten acceptance checks PASS with reviewed browser evidence. User module acceptance is pending. OAuth 1.0a over local HTTP is approved. See [verification report](../evidence/m2/report.md).  
**Date:** 15 October 2026.  
**Product source:** Assignment DOCX. **Planning sources:** [blueprint M2](../../blueprint.md#m2-the-persistent-woocommerce-store), [decisions](../decisions.md), [M1 results](../evidence/m1/report.md).

## 1. Start here: WHAT, WHY, HOW

**WHAT:** Install one working online shop that remembers its products, orders, and uploaded images.

**WHY:** This shop will supply the real product and order information for our AI tools later. First, it must work normally for a person shopping in a browser.

**HOW:** Kubernetes runs WordPress with WooCommerce and a separate MariaDB database. Helm installs their containers, saved disks, settings, and web route. We create a sample product, place a pretend order, and replace the running Pods to prove the information stays saved.

**What you will see:** Open http://shop.urumi.test, buy a sample product without paying real money, and see that order in the shop's admin page. The shop still remembers it after its containers are replaced.

## 2. The few words you need now

| Word | Simple meaning | Our use |
|---|---|---|
| WordPress | Website software. | Runs the website and its admin page. |
| WooCommerce | A WordPress add-on that adds shopping features. | Products, cart, checkout, and orders. We install it; we do not rebuild it. |
| MariaDB | Software that saves structured information. | Stores products, customers, orders, and settings. |
| WordPress content | Uploaded files and installed add-ons. | Saved separately from database records, including product images. |
| PVC | Kubernetes' request for a saved disk, similar to a Docker volume. | One disk for MariaDB; a separate disk for WordPress content. |
| Ingress / Service | Public routing rule / stable internal address. | Browser reaches the shop; the database remains internal. |
| Secret | Kubernetes' place for credentials. | Database passwords, shop setup credentials, and future REST integration keys. It is not automatically encrypted at rest. |
| REST API | A way for another program to ask the shop for data or actions. | Prepared now; our own MCP server will use it after final integration. |
| COD | Cash on delivery. | Lets us test checkout without connecting a payment provider. No actual payment or delivery occurs. |

## 3. One shopping request

~~~text
You open shop.urumi.test
           |
           v
Ingress directs the request
           |
           v
WordPress + WooCommerce Pod
           |
           +--> MariaDB Pod --> database disk
           |
           +--> WordPress content disk
~~~

For example, checkout saves an order in MariaDB. Uploading a product picture saves a file on the content disk and its reference in MariaDB. Keeping only one of those disks would lose part of the shop.

## 4. Scope and assignment connection

| M2 provides | Source / reason | Where it stops |
|---|---|---|
| One WordPress + WooCommerce store with MariaDB | Assignment store layer; MariaDB is your selected database. | No multi-store provisioning or custom storefront. |
| Persistent database and content | Explicit Kubernetes requirement. | Pod replacement proof; cluster deletion and backup recovery are separate concerns. |
| Stable shop URL through Ingress | Explicit assignment requirement; local domain from M1. | No purchased domain, VPS deployment, or TLS automation here. |
| Sample product, image, and COD order visible in admin | Store definition-of-done plus blueprint persistence check. | AI product creation and today's-orders questions wait for M10. |
| Helm resources with probes, resource settings, and Secrets | Explicit workload requirements. | Same chart retained; full production packaging belongs to M9. |
| Dedicated REST integration credential stored in a Secret | Approved blueprint preparation for the five tools. | No MCP connection, gateway registration, chat, or external client here. |

**Independent boundary:** M2 depends on M1's cluster and chart. It does not depend on M3's code. M3 can be built against a fake shop API while M2 is prepared; they connect in M10.

## 5. Design choices — approved scope and design defaults

MariaDB, INR prices, Asia/Kolkata timezone, k3d, and Helm are already selected. The following are proposed M2 defaults; exact versions and resource sizes belong to the detailed design.

| Choice | Recommendation and reason | Alternative / tradeoff |
|---|---|---|
| Shop installation | Thin image derived from standard WordPress, adding pinned WooCommerce and WP-CLI; repeatable setup script. | Section 10 makes this design proposal concrete: downloads occur at build time rather than every setup run; we maintain one small Dockerfile. |
| Running copies | One WordPress Pod and one MariaDB Pod; database controller keeps its disk association. | Multiple replicas require shared storage/database design beyond our single-store demo. |
| Checkout | Guest checkout with COD and one simple fixed-price product, using fictional customer details. | Dummy payment plugins add setup; real payment accounts are unnecessary. |
| Delivery and tax demo | Simple demo delivery setting with tax disabled so checkout is predictable. | Real shipping rates/tax rules add unrelated business configuration. |
| Setup method | A documented, rerunnable script installs/configures/seeds the shop without deleting existing data. | Manual installation alone is harder to reproduce; exact CLI/job approach is chosen during design. |
| REST authentication | Approved: signed OAuth 1.0a requests over local HTTP. | No browser sign-in flow. Signing does not encrypt responses or sign JSON bodies. HTTPS remains production guidance. No raw secret query parameters or disabled certificate checks. |
| REST identity | Dedicated shop integration identity with read/write access required by the five tools; save its keys server-side. | Reusing a human administrator's credential makes rotation and ownership less clear. |
| Disk handling | Separate named PVCs; routine cleanup/upgrade must preserve both. | Destructive reset only through a separately explained and approved action. |

Keep the storefront visually simple. This module proves a working shop and saved information, rather than spending time on a theme redesign.

## 6. Inputs, outputs, and ownership

**Inputs:** M1 cluster/context, domain, image/plugin versions, storage settings, Secret references, INR/timezone, and deterministic demo product details. **Outputs:** a usable shop, one visible test order, persistent image/data, and a dedicated integration Secret reference.

| Owner / files | Responsibility | Parallel-work rule |
|---|---|---|
| M2: deploy/charts/urumi/templates/store/ | WordPress and MariaDB workloads, Services, disks, shop Ingress, settings, and scoped database access rules. | M2 edits only its directory. |
| M2: scripts/store-setup.ps1 | Reproducible setup, safe rerun, seed, and credential preparation. | Never print passwords or REST keys; do not regenerate working credentials on every rerun. |
| M2: scripts/m2/ and tests/store/ | Separate deploy/check steps and module verification. | No M3/MCP/gateway orchestration. |
| M2: docs/store-setup.md | Beginner setup, checkout, safe restart, credential rotation, disk retention notes. | Include how to get admin access securely; no credential values. |
| M2: docs/evidence/m2/ | Commands, redacted results, screenshots, IDs, and gaps. | No Secret dumps, customer personal data, or kubeconfig contents. |
| Root integrator: shared Helm values and helpers | Merge reviewed module settings into the existing chart; local/prod values differ by configuration. | M2/M3 supply settings fragments for review; they do not concurrently edit shared files. |

Section 10 names the Services, Secret keys, Helm settings, and approved authentication contract used by M3. [WooCommerce authentication documentation](https://developer.woocommerce.com/docs/apis/rest-api/authentication/) describes the selected HTTP signing method. Credentials stay out of values files, Git, screenshots, and submitted artifacts. A temporary setup Job is bounded and must not expose credentials in command logs.

## 7. Measurable acceptance checks

These are planned checks. No M2 result is currently PASS. Exact runnable commands are finalized in design; all Kubernetes commands must name our context and namespace.

| ID | Required result / planned check | Evidence under docs/evidence/m2/ |
|---|---|---|
| M2-01 | Helm lint/template pass for local and production-shaped values. Both use the existing chart; rendered manifests reference Secrets without containing credential values. | helm-checks.txt; sanitized manifest review |
| M2-02 | Install store; WordPress and MariaDB become Ready within bounded waits. Inspect probes and CPU/memory requests/limits; record pinned versions. | workload-settings.txt; cluster-status.txt; versions.json |
| M2-03 | Browser opens shop.urumi.test through Ingress. Database uses only an internal Service; no MariaDB Ingress/NodePort. An unrelated caller cannot connect to its database port while WordPress still works. | storefront.png; exposure-check.txt; database-access-check.txt |
| M2-04 | Setup configures WooCommerce, INR, Asia/Kolkata, COD, and sample product. Rerun does not duplicate the seed product, reset the store, or replace working credentials. | setup-check.txt; settings summary; seed product ID |
| M2-05 | Add product to cart, complete COD checkout, then find the same order ID and product/price in WooCommerce admin. | storefront/cart/confirmation/admin screenshots; order ID |
| M2-06 | Upload and display a product image. Record image URL and content hash, product/order IDs, PVC names/UIDs, and current Pod UIDs. | persistence-before.json; image proof; pvc-status.txt |
| M2-07 | Delete only WordPress Pod; wait for a different Ready Pod UID. Product, order, uploaded image URL/hash, and original PVCs remain unchanged. | wordpress-restart.txt; persistence-after-wordpress.json |
| M2-08 | Delete only MariaDB Pod; wait for replacement and shop recovery. Confirm the same product, order, and image remain. | database-restart.txt; persistence-after-database.json |
| M2-09 | Dedicated REST keys are stored in a Kubernetes Secret, referenced by documented name/keys. From a temporary authorized checker, authenticated read succeeds and missing/wrong credentials cannot perform an administrative write. Save status/results only. | rest-preparation-check.txt; redacted Secret metadata |
| M2-10 | Reapply setup/chart safely; shop data remains. Document explicit disk-retention/upgrade handling and safe stop/start. Any temporary verification Jobs are removed. | rerun-check.txt; retention-check.txt; report.md |

M2-09 checks the shop API directly as setup verification; it does not connect the MCP server to the shop. Real five-tool compatibility and gateway-only upstream enforcement remain explicit M10 checks. No MCP Ingress is introduced by this module.

## 8. Work order and approval gates

| Step | Work | Gate |
|---|---|---|
| Scope completed | User approved M2/M3 scope and selected OAuth 1.0a. | Recorded approval; detailed design review remains below. |
| Design | Pin compatible image/plugin versions; define resources, Secret references, retention, setup strategy, and bounded check commands. | Independent design review, then user approval. |
| Implement | Build only M2-owned files and merge reviewed settings through the root integrator. | Source review before acceptance checks. |
| Verify and teach | Run M2-01 to M2-10; explain checkout, saved disks, restart behavior, and credential path. | Record PASS/FAIL/BLOCKED and exact evidence; user accepts M2. |

M2 and M3 specifications/designs can progress in parallel. Their module checks remain independent; a passing fake API test in M3 cannot substitute for a passing real shop check here.

## 9. Risks and next action

- M1 proves a small temporary page, not that the full stack fits the laptop. Set modest resource requests/limits and record actual readiness; do not assume unlimited capacity.
- Initial image/plugin downloads may need approved network access. Pin versions in design after checking compatibility; never leave a latest-only installation recipe.
- Local-path disks survive Pod replacement, not loss/deletion of the node or cluster. Preserve them during routine cleanup; production backup/storage guidance remains M9.
- WordPress/database upgrades can alter saved data. Helm rollback alone is not a database backup; do not promise automatic safe data rollback.
- Dedicated REST keys permit writes. They are upstream credentials, separate from future per-user gateway keys, and never go to dashboard users or external clients.

**Next:** Review section 10. The user has approved the scope and requested design followed by implementation; the project requires review of the concrete design before coding.

**Historical specification review:** [M2/M3 review](m2-m3-spec-review.md) found no blocking scope issues before approval. Its open authentication note is superseded by the user's OAuth selection. Current design and coordination details live in the two module specifications; no additional parallel-plan specification is needed.

## 10. Detailed design for review

### 10.1 What we will build and how it starts

**WHAT:** A standard shop container, a database container, two saved disks, and a short setup task. **WHY:** Existing commerce software handles checkout; our work makes its installation repeatable and its data persistent. **HOW:** Helm creates the resources, the database initializes, WordPress copies its files onto its disk, then a bounded setup Job installs/configures the site. A Job is a container task that finishes, similar to a one-off Docker command.

The existing cluster/context is `urumi` / `k3d-urumi`, namespace/release `urumi`; use ignored `.tools/m1/kubeconfig.yaml` explicitly. `.tools/m1/runtime.json` records port 80. The temporary M1 page stays disabled and its retained disk stays untouched. The 15 October preflight found the Docker Linux-engine named pipe missing and the saved API connection actively refused: start Docker Desktop's Linux engine and recheck/start the existing cluster before deployment. This does not prove any disk loss and does not authorize cluster recreation. Recheck node readiness and allocatable capacity; M1's historical approximately 8 GB engine allocation is not a current capacity measurement.

| Resource | Concrete design |
|---|---|
| WordPress | Deployment `urumi-wordpress`, one replica, `Recreate` updates; ClusterIP Service with the same name, port 80. |
| MariaDB | StatefulSet `urumi-mariadb`, one replica; internal governing headless Service of the same name, port 3306; database `woocommerce`, application user `woocommerce`. |
| Database disk | Separately templated PVC `urumi-mariadb-data`, 2 GiB, `ReadWriteOnce`, mounted at `/var/lib/mysql`. StatefulSet references this existing claim. |
| Website disk | PVC `urumi-wordpress-content`, 2 GiB, `ReadWriteOnce`, mounted at `/var/www/html`; saves WordPress files, plugins and uploads. This saves more than only `wp-content`, avoiding a second shared filesystem for setup. |
| Browser route | Ingress `urumi-wordpress`, Traefik, host `shop.urumi.test`, path `/`; WordPress home/site URL `http://shop.urumi.test`. Add only this hostname to loopback if missing, through the existing authorized host-edit workflow. |
| Setup | Unique `urumi-m2-setup-*` Job, shared website disk, no Kubernetes API token or permissions; reads mounted Secrets. Script records its exact name and removes only its owned Job after collecting safe results. |

Both PVCs use `helm.sh/resource-policy: keep`. Routine Helm upgrade, disabling store resources, and Pod replacement retain them. Uninstall/reinstall may require deliberate ownership reconciliation of kept objects; do not silently adopt or delete them. Node/cluster deletion can still lose local-path data. No reset command is part of ordinary setup. Retention is not a backup, and Helm rollback does not reverse database migrations.

### 10.2 Versions and a small reproducible image

| Component | Selected starting pin | Source checked during design |
|---|---|---|
| WordPress / PHP / Apache | `wordpress:7.1.3-php8.3-apache` | [Official image tags](https://hub.docker.com/_/wordpress/) |
| WooCommerce | `11.2.1` | [Official plugin metadata](https://wordpress.org/plugins/woocommerce/) lists WordPress 7.0 minimum and testing through 7.1.3. |
| WP-CLI | Copy the PHP executable archive from `wordpress:cli-2.12.0-php8.3` | [Official image tags](https://hub.docker.com/_/wordpress/); [WP-CLI release](https://github.com/wp-cli/wp-cli/releases/tag/v2.12.0). |
| MariaDB | `mariadb:11.4.13-noble` | [Official image manifest](https://github.com/docker-library/official-images/blob/master/library/mariadb) lists this maintained 11.4 tag. |

These source checks establish published tags and declared compatibility, not a tested installation. Before building, resolve the three image inputs to immutable registry digests and record them. Build `build/store/Dockerfile` from the WordPress digest, copy the WP-CLI PHP archive from its digest, and install only required download/extraction tools during the build. Fetch the exact WooCommerce archive from WordPress.org over validated HTTPS into `/usr/src/wordpress/wp-content/plugins/woocommerce`. Record its SHA256 and compare extracted files with the official versioned plugin checksums where available; do not describe a locally calculated hash alone as publisher verification. No credentials are used in this build.

The local image is `urumi-store:m2` and is imported into the existing k3d cluster; record its image ID and the Pod's actual `imageID`. Avoid a mutable-only image reference in the deploy evidence. Production uses the same chart with a published immutable image reference; pushing to a public registry is not authorized. The derived image also contains non-secret bootstrap/check scripts and health endpoints. Plugin/core automatic updates are disabled for this controlled demo; rebuilding/upgrading is deliberate. Because website files are persisted, a new base image alone does not upgrade an existing installation: setup checks actual core/plugin versions and stops on mismatch, preserving data for an explicit migration decision.

### 10.3 Secrets and safe, repeatable setup

| Secret | Keys and consumers |
|---|---|
| `urumi-store-db` | `root-password` only MariaDB; `database-password` MariaDB, WordPress and setup Job. |
| `urumi-store-admin` | `username`, `password`, `email`; setup Job only. Fictional local email; no mail service. |
| `urumi-store-salts` | The eight WordPress authentication key/salt names; WordPress and setup Job. Stable across reruns. |
| `urumi-woocommerce-rest` | `consumer-key`, `consumer-secret`; setup Job and M2 authorized checker now; M3 references them only at M10. |

`scripts/store-setup.ps1` creates missing Secrets using a cryptographic random generator. It sends in-memory Secret manifests to kubectl through stdin, never command-line values, transcript logging, saved manifest files or Helm values. Existing Secrets are reused. Reject a partial key Secret instead of regenerating silently. Set WordPress/MariaDB `_FILE` settings to mounted files; never log those contents. Operator credentials are retrieved only by a documented deliberate local operator step and excluded from evidence/screenshots. The running website does not mount the admin or REST credentials. No container gets a service-account token.

`scripts/store/bootstrap.php`, executed through WP-CLI `eval-file` as UID/GID 33, reads setup inputs from mounted files. The image's normal WordPress entrypoint initializes website files/permissions; the Job uses the same database settings and `fsGroup: 33`. It waits for files and database with bounded retries. Do not log bootstrap arguments, returned credential values, full REST headers or sensitive errors.

The bootstrap first checks whether WordPress is already installed; installs only when absent. It verifies canonical URLs, sets pretty permalinks, activates the pinned plugin, creates WooCommerce pages, chooses INR/Asia-Kolkata, fictional India store address, guest checkout, COD enabled, taxes off, and a virtual demo product so shipping configuration is unnecessary. Use classic cart/checkout shortcodes to keep the demo predictable. Product `DEMO-001` is a published simple virtual product priced `499.00`; locate by SKU and create only if absent. On rerun validate an existing product rather than overwrite user edits. Import a repository-owned small demo picture only when its saved attachment marker is absent, then associate it with the seed product.

Create dedicated user `urumi-integration` with `shop_manager` role, random non-human login password, and one `read_write` Woo REST key. The setup script pre-generates `ck_` / `cs_` values in the REST Secret; bootstrap stores the key using WooCommerce's native API-key hashing/table format and the associated user ID. An owned description `urumi-m2-integration` and a non-secret database option recording completed key initialization distinguish first setup from rerun. On first setup, with no completion marker or owned key, insert the pre-generated Secret's key; then record the key ID in the marker. If interrupted after insertion but before the marker, verify the uniquely owned row against the existing Secret and identity before completing the marker. An existing matching row/marker is reused, never duplicated.

Once the completion marker exists, a missing key row is treated as deliberate revocation or inconsistency and stops; setup must not recreate a revoked credential. A missing Secret with an existing owned row/marker, a mismatched Secret/row, multiple owned rows, or a marker referencing another identity also stops with a redacted reconciliation instruction. Automatic recovery is limited to the verifiable incomplete first-setup state above; keys are never silently rotated. Rotation is a deliberate create-new, verify, revoke-old operation documented for M10 integration. This role can manage orders/products; optional per-tool restrictions are not introduced here.

### 10.4 The exact REST handoff to M3

| Setting | Value / rule |
|---|---|
| Canonical base URL | `http://shop.urumi.test` |
| Internal connection URL | `http://urumi-wordpress.urumi.svc.cluster.local` |
| REST path | `/wp-json/wc/v3` |
| HTTP Host | Fixed `shop.urumi.test`; same canonical authority used by the signer. |
| Authentication | OAuth 1.0a one-legged signing, HMAC-SHA256, unique random nonce and current Unix timestamp; OAuth parameters in Authorization header, never secret query parameters. |
| Routing | Sign the canonical method/path/query; connect to the fixed internal Service with identical path/query. No redirects, user-provided destination, forged HTTPS indicator, or fallback to Basic. |

The public name tells WooCommerce which site it is, while the internal Service tells Kubernetes which Pod receives the packet. The [WooCommerce OAuth documentation](https://developer.woocommerce.com/docs/apis/rest-api/authentication/) requires the canonical store URL when signing. M2 proves this fixed internal connection succeeds against the real shop before M3 depends on it. Missing/wrong signature and a different signed canonical URL must fail administrative operations. Omit `oauth_version`; no browser OAuth consent screen is involved.

Local HTTP does not encrypt order responses, administrator login, or JSON bodies; WooCommerce explicitly says the JSON body is not signed. This is the user's selected local demo transport. Production guidance uses trusted HTTPS without disabled verification; no production security proof is claimed in M2. Never record Authorization headers, raw credential-bearing URLs, or customer details in request logs.

### 10.5 Health, resources and network boundaries

| Workload | Initial CPU / memory requests | CPU / memory limits | Checks |
|---|---|---|---|
| WordPress | 100m / 256Mi | 1000m / 768Mi | Startup/liveness HTTP GET `/urumi-live.php` executes simple PHP without DB dependency; readiness GET `/urumi-ready.php` checks installed WordPress, active WooCommerce and a lightweight DB query. Endpoints return only status codes, never settings/errors. |
| MariaDB | 100m / 256Mi | 1000m / 768Mi | Official `healthcheck.sh --connect --innodb_initialized` startup/readiness; liveness local server connection check with sufficient failure budget. |
| Setup Job | 100m / 128Mi | 500m / 512Mi | `backoffLimit: 0`, `activeDeadlineSeconds: 300`; completion and sanitized summary, rather than HTTP probes. |
| Verification Job | 25m / 64Mi | 250m / 128Mi | Deadline 60s, no retry; finite process exit is its health/completion evidence. |

WordPress probes every 10s, 3s timeout; startup allowance 180s, readiness three failures, liveness six. MariaDB startup allowance 180s, readiness every 5s/3s timeout, liveness every 10s/3s timeout/six failures. A database outage makes the website unready without repeatedly restarting WordPress. Bootstrap intentionally precedes final WordPress readiness: initial Helm apply does not wait on an uninstalled website; wait for DB readiness and WordPress files/Running state, run setup, then perform bounded rollout readiness waits. Steady-state reapply can use Helm `--wait --timeout 5m`.

NetworkPolicy selects only this release's MariaDB and allows TCP3306 from WordPress and the narrowly labelled setup Job in the same namespace. Baseline then allowed/denied controls prove real enforcement; remove temporary baseline relaxation immediately after the test. MariaDB has no Ingress or NodePort. The storefront remains public for shoppers. MCP access restriction belongs to M3/M10; M2 introduces no MCP route. Root initialization required by the official database/Apache entrypoints is documented rather than pretending these images run entirely as non-root; no privileged containers, host mounts or Kubernetes API permissions. Read-only Secret mounts and no token automount apply throughout.

### 10.6 File ownership and exact check plan

Only these additions are needed: `build/store/Dockerfile`; `scripts/store-setup.ps1`; `scripts/store/bootstrap.php`; `scripts/m2/deploy-store.ps1`, `check-store.ps1`, `rest-check.py`; `tests/store/` for focused bootstrap/rerun/manifest checks; `docs/store-setup.md`; `docs/evidence/m2/`. Helm resources stay under existing `deploy/charts/urumi/templates/store/`: `wordpress.yaml`, `mariadb.yaml`, `pvc.yaml`, `ingress.yaml`, `networkpolicy.yaml`, `configmap.yaml`. The root integrator adds a `store` settings block to existing shared values/helpers, guarded by `store.enabled`; no separate chart or parallel-plan file.

Common values specify image references, Secret names, resource/probe settings, persistence sizes, currency/timezone and policy selectors. Local values select host `shop.urumi.test`, `local-path` storage and imported image; production-shaped values require a replacement host, supplied Secret names, storage class and immutable registry image. Both render the same templates. Setup and checking Jobs are explicit bounded script-created resources, not Helm hooks that unexpectedly rerun during every upgrade.

Planned PowerShell commands after design review and implementation:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/deploy-store.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/store-setup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m2/check-store.ps1
kubectl --kubeconfig .tools/m1/kubeconfig.yaml --context k3d-urumi -n urumi get pods,svc,ingress,pvc
~~~

The deployment wrapper runs the explicit project-local Helm executable for lint/template with local and production-shaped values, builds/imports the image, and applies release `urumi` with `foundation.enabled=false`. It checks existing release ownership first and captures failed events without dumping Secrets. The checker implements M2-01–10, then reruns setup and asserts unchanged seed/credential-record IDs. Parse every PowerShell script before executing it; inspect PHP syntax and rendered probes/Secret references/resources before installation. No unrelated retrieval metrics or additional application framework is needed.

Browser checkout remains an actual browser check: buy the seed product with fictional details, find the same order in admin, record redacted screenshots and IDs. Record product/order IDs, attachment URL and fetched-byte SHA256, Pod/PVC UIDs; delete only the exact recorded WordPress Pod, wait up to 180s for a new Ready UID, repeat the assertions; then do the same for MariaDB, allowing shop recovery. Never delete a PVC or use namespace-wide deletion. REST checker reads only mounted fake/demo credentials, tests signed read and wrong/missing/replayed/incorrect-canonical signatures, and verifies an authorized write on a disposable product plus cleanup. Unsigned public product reads cannot prove authentication, so check protected administrative context. Raw signing values and response customer fields are redacted.

Every acceptance ID receives PASS, FAIL or BLOCKED with command, exit, timestamp, sanitized output and evidence file. No check has run yet. A unit test/build cannot substitute for checkout, policy enforcement, saved-image/data persistence, or signed real REST requests. No MCP/shop wiring happens until M10. After independent design review, present the concrete result for user approval; after implementation review and M2 acceptance evidence, obtain the module acceptance gate.

**Independent design review:** READY FOR USER REVIEW. The reviewer found no blocking scope, chart, storage, credential-boundary or module-boundary issues. The subsequent key-bootstrap clarification above makes interrupted first setup recoverable while preserving explicit revocation. This is a design verdict, not implementation or runtime acceptance.
