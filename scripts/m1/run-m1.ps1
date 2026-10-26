. "$PSScriptRoot/common.ps1"
if (-not (Test-Path $K3d) -or -not (Test-Path $Helm)) { & "$PSScriptRoot/install-tools.ps1" }
if (-not (Test-Path $KubeConfig)) {
    & "$PSScriptRoot/setup-cluster.ps1"
} else {
    # Resume only a project-created cluster; do not adopt another installation.
    if (-not (Test-Path (Join-Path $ToolDir 'k3d-resolved.yaml'))) { throw 'Saved project cluster configuration is missing; inspect before reuse.' }
    Assert-LocalCluster
    if (-not (Test-Path (Join-Path $ToolDir 'runtime.json'))) {
        & "$PSScriptRoot/setup-cluster.ps1" -Resume
    }
    $null = & "$PSScriptRoot/preflight.ps1" -ExistingCluster
}
& "$PSScriptRoot/check-foundation.ps1"
