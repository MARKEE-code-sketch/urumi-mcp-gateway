# Teal dashboard image and runtime verification

**PASS for image build and the approved dashboard-only deployment.** Live authenticated browser verification is recorded separately by the root agent.

Only the dashboard image was replaced in the existing `urumi-m10` release. The build used the approved current frontend, including local fonts and SVG assets, and made no frontend edits. [Source inputs](image-source-inputs.json) freeze all 57 Docker build/runtime inputs, including font/SVG license files and build configuration. All remained unchanged through deployment. [Host assets](host-build-assets.json) freeze the latest host build.

Exact commands from workspace-root PowerShell (the helper files are private operator utilities):

```powershell
.tools/m10/venv/Scripts/python.exe .tools/m10/build_teal_dashboard.py
.tools/m10/venv/Scripts/python.exe .tools/m10/upgrade_teal_dashboard.py
```

[Build command evidence](build.json) records all successful command exit codes. The helper ran:

```powershell
docker build -t urumi/dashboard:m8-teal -f frontend/Dockerfile frontend
docker image save -o .tools/m10/dashboard-teal.tar urumi/dashboard:m8-teal
.tools/m10/venv/Scripts/python.exe scripts/m4/image_identity.py .tools/m10/dashboard-teal.tar --image urumi/dashboard:m8-teal --output docs/evidence/ui-refresh/teal-dashboard/image-identity.json
.tools/m1/k3d.exe image import urumi/dashboard:m8-teal -c urumi
```

[Docker build output](docker-build.txt) includes successful TypeScript checking and Vite build. The exported image archive remains private and ignored. Docker inspect evidence used only Descriptor and RepoDigests fields; it did not dump environment variables.

Actual image identities:

- OCI index: `sha256:d1ef2a73eca5116926879979fdc1dc03e66801ea20e8340b0a6fd65e0e3f5a14`.
- Linux/amd64 manifest: `sha256:ae891202fb140a02c4dd06aca175e06b0c894002c3c71c10e25eaa1012a7fdea`.
- Actual exported configuration: `sha256:3d1de55cc546b65db161fa8eea096e12ba5e310789a4ffe8979a679cf608f420`.

[Runtime evidence](runtime.json) records SHA256 verification of the actual node containerd index, manifest and configuration bytes. The configuration matched the Docker export. The exact immutable digest alias was registered and resolved by CRI before Helm upgrade.

The helper checked namespace ownership before accessing release resources. It read the deployed effective Helm values privately and changed only `dashboard.image.tag` and `dashboard.image.digest`. Helm revision **6** is deployed. Effective values after the upgrade exactly match the intended values. Only those two dashboard image fields were synchronized in the existing private operator `values.yaml` and `merged-values.yaml`; no credentials were printed.

Observed after upgrade:

- All seven workloads Ready; the running dashboard image matches the verified immutable image.
- Other six Pod UIDs unchanged; all three Bound PVC names and UIDs unchanged.
- Backend remains `m10-recovery` at `sha256:2c842ad25e4e09f3ffd5a2ae515942e1bf51f2e2df42250e7ee24c7dab20aabe`.
- Shop TLS secret reference remains `urumi-m10-dashboard-tls`.
- All **27** deployed HTML/JS/CSS/font/SVG assets have the same SHA256 as the frozen latest host build.

No other namespace, backend image, provider, shop data, Secret contents or public repository was changed. These are deployment and asset checks; they do not replace the separately recorded authenticated browser checks or the full assignment acceptance flow.
