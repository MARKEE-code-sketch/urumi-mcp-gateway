# Dashboard tools preview image verification

**PASS for the reviewed image build and image-only deployment.** Actual authenticated admin/member View tools verification is performed separately by the root.

The existing backend preview response uses `gateway_name`; the UI now consumes that canonical field consistently. The independent source review is in [independent-review.md](independent-review.md), and [source-comparison.json](source-comparison.json) compares the new dashboard inputs against the retained M8 freeze. This task did not redesign CSS, add Markdown, introduce dependencies or change backend contracts/data.

Exact build command from workspace-root PowerShell:

```powershell
docker build -t urumi/dashboard:m8-tools-fix -f frontend/Dockerfile frontend
docker image save -o .tools/m10/dashboard-tools-fix.tar urumi/dashboard:m8-tools-fix
.tools/m10/venv/Scripts/python.exe scripts/m4/image_identity.py .tools/m10/dashboard-tools-fix.tar --image urumi/dashboard:m8-tools-fix --output docs/evidence/ui-refresh/tools-preview-fix/image-identity.json
.tools/m1/k3d.exe image import urumi/dashboard:m8-tools-fix -c urumi
```

All completed successfully. The image build itself ran TypeScript checking and Vite build. [docker-build.txt](docker-build.txt) retains actual build output. [image-source-inputs.json](image-source-inputs.json) freezes 25 exact build/runtime inputs, all unchanged through deployment. The Docker archive remains ignored and private.

Actual image proof:

- OCI index: `sha256:5af4f7eee31d98ac09a817d484458c7065c2d9e4dfe784dee87639d44083e03b`.
- Actual exported configuration: `sha256:7c78f06e6192e877e87a4918b258a5e8c10cf57dec2255933029fbbf956eeefd`.
- Node containerd index, linux/amd64 manifest and configuration bytes were each SHA256-verified; the configuration matched the export. The exact immutable digest alias was added and successfully resolved with CRI **before** Helm upgrade, preventing the earlier local-image digest registration problem.

[Runtime evidence](runtime.json) records exact commands/exit codes and actual before/after allowlisted state. Upgrade used current deployed Helm effective values in an ignored private file, changing only `dashboard.image.tag` and `dashboard.image.digest`. It preserved backend `m10-recovery` and its immutable digest, the latest main shop TLS reference and all other values. Existing documented private input files had only these two dashboard image fields synchronized.

All seven main-release workloads were Ready after upgrade; the actual dashboard Pod image identity matched the verified image. The other six Pod UIDs and all three Bound PVC UIDs were unchanged. The deployed index/JS/CSS asset hashes exactly matched the host build. No other namespace, provider, public repository, Secret contents or application data was changed.

Historical evidence limitation: a recent focused fixture-browser harness run refreshed the old M8 network summary artifact. That refreshed metadata must not be described as the original M8 run. This fix's image/runtime evidence is deliberately retained in this separate directory.
