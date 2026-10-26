# M1 implementation and check results

**Date:** 14 October 2026. **Status:** Files implemented and reviewed; live acceptance BLOCKED. M1 is not complete.

## In simple terms

The installation recipe and checking scripts are ready. This tool cannot currently talk to Docker or download the portable tools, so no cluster or test page was created. Your normal PowerShell terminal is the prepared fallback.

## What changed

| Part | Purpose |
|---|---|
| infra/local/k3d.yaml | One-node cluster, pinned k3s, loopback port/API, isolated connection settings. |
| deploy/charts/urumi/ | Shared Helm chart; explicitly enabled temporary page, Service, Ingress, saved disk, probes/resources, narrow policy. |
| scripts/m1/ | Portable tools, preflight, setup, independent checks, one-command runner. |
| docs/local-cluster.md | Beginner setup, page/hosts instructions, stop/start, cleanup and limitations. |
| .gitignore | Ignore portable executables/downloads and local cluster connection credentials under .tools/. |

## Observed checks

| Check | Result | Evidence |
|---|---|---|
| Windows PowerShell parsing of all six M1 scripts | PASS; zero parser errors | powershell-syntax.json |
| Independent source review | No remaining blocking issue found | implementation-review.md |
| Docker preflight | BLOCKED; Docker config and engine pipe access denied | preflight.json |
| Portable tools download | BLOCKED; Invoke-WebRequest unable to connect to GitHub remote server | tool-install-attempt.json |
| Helm rendering and all live M1 acceptance | BLOCKED; prerequisites unavailable | results.json |

No runtime result has been inferred from a static review or syntax check. No tool executables were installed, images pulled, host settings changed, or cluster/application resources created in this attempt. Downloads directory and ignored local tooling folders were created.

## Commands actually attempted

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/m1/preflight.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/m1/install-tools.ps1
~~~

Syntax was checked with Windows PowerShell's System.Management.Automation.Language.Parser.ParseFile on each scripts/m1/*.ps1 file; powershell-syntax.json records the six checked filenames and zero errors.

~~~powershell
$results = foreach ($file in Get-ChildItem scripts/m1/*.ps1) {
    $tokens = $null; $parseErrors = $null
    $null = [System.Management.Automation.Language.Parser]::ParseFile($file.FullName, [ref]$tokens, [ref]$parseErrors)
    @{file=$file.Name; errors=@($parseErrors | ForEach-Object { $_.Message })}
}
$results | ConvertTo-Json -Depth 5
~~~

## Next action from your normal PowerShell

From this project folder with Docker Desktop running:

~~~powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/m1/run-m1.ps1
~~~

This performs checksum-verified project-local tool installation, preflight, setup, and acceptance checks. Send the terminal output or first error. After it runs, review results.json and complete the browser screenshot instructions in docs/local-cluster.md. Run explicit cleanup only after reviewing browser evidence. Elevated hosts editing stays user-run.

## Open gaps

All M1-01 through M1-09 are currently BLOCKED; see results.json. Image tag/digest, actual node readiness, Helm install, internal DNS, Ingress, Pod/PVC persistence, policy enforcement, resources/probes in the cluster, exposed routes, actual browser access, and cleanup need observed evidence. A failed setup should be inspected, not repaired by deleting the cluster/PVC. M2 awaits M1 completion and user acceptance.
