# M1 — run our Kubernetes playground

## What you are doing

Docker Desktop runs one Kubernetes node. Helm installs a temporary page in a Pod. Its PVC saves a test file. Our check script proves the file survives a replaced Pod and checks which callers can connect.

This page is a learning fixture. It is not WooCommerce or the gateway.

## 1. Run the setup and checks

Open Docker Desktop and wait until its engine is running with Linux containers. Open normal PowerShell in this project folder. Run:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/run-m1.ps1
~~~

The execution-policy setting applies only to this PowerShell process. The script downloads two checksum-verified portable tools into ignored .tools/m1, checks Docker, creates cluster urumi if absent, installs the page, and runs the checks. It does not install anything globally or change Windows settings. Do not share .tools/m1/kubeconfig.yaml; it contains the local cluster connection credentials.

If it stops with an error, send the error and the saved result files. Do not delete the cluster or PVC to retry. The runner can resume a project-created cluster using its saved local connection file; it refuses an existing cluster it cannot establish as this project's setup.

### Individual steps, if we need to troubleshoot

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/install-tools.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/preflight.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/setup-cluster.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/check-foundation.ps1
~~~

The setup script deliberately refuses to recreate an existing cluster. The runner resumes only through the saved connection/configuration. All cluster operations target k3d-urumi explicitly.

## 2. Open the page in your browser

The hosts file is Windows' small address book. This line tells Windows that our test name means this laptop:

~~~text
127.0.0.1 foundation.urumi.test
~~~

1. Search for Notepad in Start, right-click it, and choose **Run as administrator**.
2. Open **C:/Windows/System32/drivers/etc/hosts**. In the Open dialog, choose **All files** so it appears.
3. Add the line above only if the name is not already present. If it points elsewhere, stop and tell us first.
4. Save. Open **http://foundation.urumi.test**. If the script selected 8080, open **http://foundation.urumi.test:8080**.
5. You should see **Urumi M1 — Kubernetes is serving this page.** Save a screenshot as docs/evidence/m1/foundation-browser.png and tell us which URL you opened.

The scripts can check routing without editing hosts by sending the correct Host header to loopback, but that alone does not prove the real browser visit. We review the screenshot before accepting M1-03. No automated check claims that your browser worked.

## 3. Understand the files

| File or folder | What you learn from it |
|---|---|
| infra/local/k3d.yaml | One node, Docker entry port, loopback-only API, separate connection configuration. |
| deploy/charts/urumi/values*.yaml | Settings: image, storage, URL, resource sizes, and whether the temporary page is enabled. |
| templates/foundation/deployment.yaml | How a Pod is started, checked, and replaced. |
| templates/foundation/service.yaml and ingress.yaml | Internal stable address and browser route. |
| templates/foundation/pvc.yaml | Request for saved disk; kept when the page is removed. |
| templates/foundation/networkpolicy.yaml | Only the permitted test caller and Traefik can reach the page after enforcement. |
| templates/foundation/configmap.yaml | The page and its small Python standard-library server. |
| scripts/m1/ | Setup and separate checks; command outputs go into docs/evidence/m1/. |

## 4. Check output and limitations

Read docs/evidence/m1/results.json after the check script. Each M1 acceptance ID has its observed status and explanation. Raw command logs sit beside it.

- A PASS from Helm proves chart rendering, not a running cluster.
- The persistence check replaces only the temporary page Pod. It does not prove node/cluster deletion recovery or real shop persistence.
- The connection test records a working baseline, an allowed request, a blocked caller, and another allowed request. DNS/server errors are not counted as policy enforcement.
- Browser and cleanup evidence remain pending until those actions are actually performed.
- The production render excludes the test page. Full application/VPS packaging is M9.

## 5. Stop or start the local environment

These commands affect only the urumi cluster. Stopping preserves its containers/storage; deletion is a different operation and is not part of M1 cleanup.

~~~powershell
./.tools/m1/k3d.exe cluster stop urumi
./.tools/m1/k3d.exe cluster start urumi
~~~

## 6. Remove the temporary page after review

After we have reviewed the page screenshot and check outputs, run:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/check-foundation.ps1 -Cleanup
~~~

This removes only labelled M1 checking Jobs and disables the foundation workload through Helm. The retained test PVC is inspected and kept. It does not delete the cluster, namespace, or future applications. Do not uninstall a later combined release to clean up this page.

To restore the page, rerun the project runner against the same existing release; retained PVC ownership must be checked before Helm adoption. Do not delete a retained PVC automatically. We will inspect any Helm ownership conflict and provide a targeted correction.

## Technical sources

Tool downloads use the official [k3d release assets](https://github.com/k3d-io/k3d/releases/expanded_assets/v5.9.0) and [Helm release](https://github.com/helm/helm/releases/tag/v3.21.3). Their SHA256 lists are checked before the executables are used. The runtime Python image digest is resolved from Docker and recorded before chart deployment.
