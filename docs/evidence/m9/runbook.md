# Re-run M9 without touching Kubernetes

Use PowerShell from repository root, Python3.13 and Helm3. The checker environment is isolated and not used by the application.

```powershell
python -m venv .tools/m9/venv
./.tools/m9/venv/Scripts/python.exe -m pip install -r scripts/m9/requirements.txt
./.tools/m9/venv/Scripts/python.exe scripts/m9/check-m9.py --helm helm --output docs/evidence/m9
```

If Helm is not on PATH, pass its explicit path. An optional `--sentinels PRIVATE_FILE.json` loads known string sentinel values from a private JSON object and reports counts only; never put the file in source/evidence. The saved final project run checked six privately held M6 fixture credentials. On this Windows workspace, the sandbox denied pytest-created temporary directories; the same authorized offline test command completed with the project-local environment outside that restriction.

The runner lints/renders local/production, runs focused release tests, parses resource/policy references, checks names-only preflight examples, verifies prior runtime source hashes, checks dependencies, invokes the expected blocked Backend build request and stages an explicit source-only package under ignored `.tools/m9`. It never invokes kubectl, Helm install/upgrade, Docker builds, image imports/pushes or a provider. Its raw twelfth group remains independent-review pending.

Standalone manual checks:

```powershell
./.tools/m9/venv/Scripts/python.exe -m pytest tests/release -q -p no:cacheprovider
./.tools/m9/venv/Scripts/python.exe -m pytest tests/store -q -p no:cacheprovider
./.tools/m9/venv/Scripts/python.exe scripts/m9/preflight.py --mode render --values deploy/charts/urumi/values-local.yaml
./.tools/m9/venv/Scripts/python.exe scripts/m9/preflight.py --mode render --values deploy/charts/urumi/values-prod.yaml
# Expected safe failure until real M10 entry points/runtime are available:
./scripts/build-images.ps1 -Module Backend -ImagePrefix urumi -Tag review
```

For actual operator inputs, setup, secrets, backups and rollback use [operations](../../operations.md). Those are future reviewed/M10 procedures, not M9 check commands. A chart render or synthetic successful deploy-preflight fixture proves neither an installed application nor live enforcement or VPS operation. Do not apply these full release examples to the retained store while validating this package.

The final independent [review](acceptance-review.md) and [results](acceptance-results.json) record all twelve M9 criteria PASS for static packaging. User module acceptance remains pending. The runner raw history stays review-pending by design; it cannot independently approve its own output. M7 provider evidence, M8 user acceptance and M10 final integration are separate gates.
