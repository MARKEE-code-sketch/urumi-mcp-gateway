# M10 verification runbook

Use PowerShell from repository root. Read the [current live report](live-report.md), [historical implementation report](report.md) and [M10 design](../../modules/m10-spec.md#12-concrete-runtime-composition-design) for scope. This runbook does not authorize additional deployments or machine trust changes beyond those already approved in the session.

## Controlled checks

```powershell
python -m venv .tools/m10/venv
./.tools/m10/venv/Scripts/python.exe -m pip install -r scripts/m10/requirements.txt
./.tools/m10/venv/Scripts/python.exe -m pip check
./.tools/m10/venv/Scripts/python.exe scripts/m10/check-m10.py --mode controlled --output docs/evidence/m10/controlled
```

This tests composition/gateway/chat with controlled dependencies. It explicitly strips `URUMI_M10_TEST_DSN` from the subprocess environment and excludes `tests/backend`, whose old fixtures reset their database. Six opt-in PostgreSQL tests skip; run them separately only against a fresh disposable database. No model key is needed.

## Separate PostgreSQL checks

The observed owned container was `urumi-m10-test-postgres`, label `urumi.dev/module=m10-test`, published only on `127.0.0.1:15440`, with memory-only `/var/lib/postgresql/data`, fresh private password and no retained volume. The private env file is ignored under `.tools/m10/`. Before creating a new test container, refuse any existing container with that name until its identity/ownership is checked. A port conflict is a stop condition, not permission to kill another service.

Use an explicitly chosen local PostgreSQL image and record its actual configuration identity. The observed image was the already available `postgres:17-bookworm`; its actual identity is recorded in [cleanup evidence](postgres-cleanup.json). The test fixture requires loopback and database name starting `urumi_m10_test`; each test creates/removes only its own unique schema. These guards reduce accidental targeting; they do not authorize using an existing database just because its name matches.

The observed container command was:

```powershell
docker run --detach --rm --name urumi-m10-test-postgres --label urumi.dev/module=m10-test --publish 127.0.0.1:15440:5432 --env-file .tools/m10/postgres-test.env --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=256m postgres:17-bookworm
docker exec urumi-m10-test-postgres pg_isready -U urumi_m10_test -d urumi_m10_test
```

Generate the password into the ignored private file without printing it. Supply `URUMI_M10_TEST_DSN` privately in the Python subprocess environment using `psycopg.conninfo.make_conninfo`; never use a password-bearing CLI argument or save environment dumps. Then invoke the six tests using the exact pytest command in the report. Clear that environment variable afterward. Capture only sanitized results; failures must not expose credentials. Stop the container only after checking its exact name, ID, ownership label, loopback binding and tmpfs, then verify its automatic removal. Do not stop any historical shop/database container.

## Static package and image

Use a fresh M10 package output; the updated checker refuses the frozen M9 output directory. The missing-entrypoint negative is staged and cannot start a Docker build in the current checkout. Actual image building is a separate explicit step. The final `release` stage excludes check scripts; the historical `checks` target still exists for old module procedures. Follow the exact build/export/hash commands in the report. An image smoke with `--network none` cannot prove real dependencies work.

## Remaining live deployment

Approved and installed target: release/application namespace `urumi-m10`, dynamic Secret namespace `urumi-m10-secrets`, new disks, shop `shop-m10.urumi.test`, dashboard `https://dashboard-m10.urumi.test`. Use the existing Helm chart and explicit context/kubeconfig; never mutate retained `urumi` as a default. Private inputs and trusted HTTPS were supplied for this test release. No certificate bypass or insecure-cookie workaround. See the [current live report](live-report.md) for observed results.

The inventory mode only reads selected runtime metadata from an owned namespace labelled `urumi.dev/module=m10`. It cannot create an installation or prove a two-user flow. Explicit live helpers and browser/client evidence now record those separate actions. Use the [demo checklist](../../demo-checklist.md), record real results against all eighteen criteria, and perform each mutation only after target/recovery review. The user confirmed the current free plan before the observed real Groq calls; a fake model or controlled upstream is never final acceptance evidence.
