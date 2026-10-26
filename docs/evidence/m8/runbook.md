# M8 dashboard runbook

M8 is the browser interface. React owns the screen state; TypeScript checks message shapes; Vite builds static files. NGINX serves those files in a non-root container. The separate Python fixture acts like the backend only during these checks. M10 connects the real account, gateway and chat modules.

Run from the repository root in **PowerShell**, using Node 24.18.0 and npm 11.16.0:

```powershell
npm.cmd --prefix frontend ci --offline=false --cache .tools/m8/npm-cache --fetch-retries=0 --no-audit --no-fund
npm.cmd --prefix frontend run typecheck
npm.cmd --prefix frontend run test -- --run
npm.cmd --prefix frontend run build
npm.cmd --prefix frontend exec -- playwright install chromium
npm.cmd --prefix frontend run test:browser
```

Browser tests start the explicit loopback fixture at `http://127.0.0.1:18080` and stop it afterward. The default Python path reuses the existing isolated M6 environment. For a fresh machine, create a project-local Python 3.13 environment, install `backend/requirements.lock.txt`, and point `M8_PYTHON` at that Python executable; it is a fixture-process setting, never a frontend build variable. For example:

```powershell
python -m venv .tools/m8/venv
./.tools/m8/venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
$env:M8_PYTHON = (Resolve-Path .tools/m8/venv/Scripts/python.exe).Path
npm.cmd --prefix frontend run test:browser
Remove-Item Env:M8_PYTHON
```

The fixture accounts are dummy `admin@example.test` and `member@example.test`, password `Fixture-password-123`. They exist only in the separate fixture process. Production static files have no fixture fallback or embedded account/role/provider credentials. Fixture control endpoints are never packaged in the production dashboard image.

The seven pages live in `frontend/src/pages/`. `api.ts` owns same-origin requests, byte/deadline limits and safe errors; `App.tsx` owns verified session, navigation, session generation, pending-work warnings and logout. `invitation.ts` captures and removes invitation fragments before API work, including a link opened while the invitation screen is already mounted. Repeated UI behaviors live in `components/`; there is no router, CSS framework, Markdown renderer or client-side MCP/provider SDK.

The image Dockerfile pins Node and NGINX by digest. The final image contains only static files and NGINX configuration. It listens on 8080 behind a Service on port 80. Health checks cover static serving, not upstream/provider availability. The chart gives it a read-only filesystem, no Kubernetes token, non-root UID 101, bounded memory-backed temporary space, and CPU/memory requests/limits. Coordination with M9 adds its startup probe and uses a five-second readiness period; liveness remains ten seconds.

The isolated runtime runner is:

```powershell
./.tools/m6/venv/Scripts/python.exe scripts/m8/check-m8.py --cluster --context k3d-urumi --cleanup
```

Prepare/import the frozen dashboard and separate fixture images first, following the image identities in this evidence directory. The runner refuses an existing/conflicting test namespace, records the original shop resources, deploys only `urumi-m8-check`, verifies runtime settings, runs Chromium through its loopback fixture Service, and removes only its labelled test namespace after success. A failure preserves owned resources for inspection. Never upgrade the existing `urumi` release for M8 checks.

Screenshots are explicit, with one-time values dismissed or masked; Playwright automatic screenshots/videos/traces are off. `network-summary.json` contains browser request origin/path/method/status, header-presence booleans and body field names only. It deliberately contains no query strings, fragments, body values, cookies or raw one-time values.

Fixture browser success proves screen behavior and static runtime. It does not prove real backend authorization, persistent key revocation, real tool writes, provider quality or final two-user acceptance. Those remain M10, and M7's unrun live provider criterion remains separate.

## Frozen runtime preparation used in this workspace

These PowerShell commands build the static dashboard and separate test fixture. The fixture requires the already verified local M6 image `urumi/gateway-check:m6`; its original local identity is recorded in `image-source-inputs.json`. Do not silently substitute a different local tag. A fresh machine can run the host fixture using the Python lock above; reproducing this historical cluster image additionally requires the documented frozen M6 base or a newly reviewed base/build identity record.

```powershell
New-Item -ItemType Directory -Force .tools/m89 | Out-Null
docker build --pull=false -f frontend/Dockerfile -t urumi/dashboard:m8 frontend
docker build --pull=false -f scripts/m8/Dockerfile.fixture -t urumi/dashboard-fixture:m8 .
docker save -o .tools/m89/m8-images.tar urumi/dashboard:m8 urumi/dashboard-fixture:m8
./.tools/m6/venv/Scripts/python.exe scripts/m4/image_identity.py .tools/m89/m8-images.tar --image urumi/dashboard:m8 --output docs/evidence/m8/image-identity-dashboard.json
./.tools/m6/venv/Scripts/python.exe scripts/m4/image_identity.py .tools/m89/m8-images.tar --image urumi/dashboard-fixture:m8 --output docs/evidence/m8/image-identity-fixture.json
./.tools/m1/k3d.exe image import urumi/dashboard:m8 urumi/dashboard-fixture:m8 -c urumi
./.tools/m6/venv/Scripts/python.exe scripts/m8/check-m8.py --cluster --context k3d-urumi --cleanup
```

Run each dependent command only after the previous one succeeds. The local Docker build/export/import commands require the existing Docker Desktop engine and `k3d-urumi` cluster. Archives stay in ignored `.tools/`, not in the submission. Regenerating evidence files above records a new run; preserve historical evidence separately when comparing builds.

Use **image tags** for this Windows k3d import. Two archive-path attempts misleadingly returned exit code zero without importing; `runtime-preparation.json` records them. The tag import succeeded in 16 seconds and actual running Pod image IDs subsequently matched the SHA256 of the exported configuration bytes. A zero import exit code alone is insufficient proof.

The observed isolated run passed fifteen Chromium cases in 30.0 seconds. Both Pods were Ready with zero restarts; all three actual static assets matched the frozen host build. Owned namespace removal, preservation of the original seven resource identities, original shop readiness/PVC binding and port-forward cleanup are recorded in `cluster-results.json`, `final-root-check.json` and `port-cleanup-check.json`. Host-only follow-ups make sixteen distinct host browser cases; the final disabled/never-checked preview case was not rerun in the cluster and is not counted there.

Independent module review is complete: all twelve M8 criteria PASS for this fixture/browser/static-runtime scope. Read [acceptance review](acceptance-review.md) and [results](acceptance-results.json). User module acceptance, M7's real-provider check and M10 integration remain separate.
