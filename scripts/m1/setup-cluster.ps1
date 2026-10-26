param([switch]$Resume)
. "$PSScriptRoot/common.ps1"
if (-not (Test-Path $K3d) -or -not (Test-Path $Helm)) { throw 'Run scripts/m1/install-tools.ps1 first.' }
$null = & "$PSScriptRoot/preflight.ps1" -ExistingCluster:$Resume
$preflight = Get-Content (Join-Path $EvidenceDir 'preflight.json') -Raw | ConvertFrom-Json
$clusters = @(Invoke-Native $K3d @('cluster','list','-o','json') 'existing-clusters.txt' 20 | ConvertFrom-Json)
if (@($clusters | Where-Object { $_.name -eq 'urumi' }).Count -gt 0) {
    if (-not $Resume -or -not (Test-Path $KubeConfig) -or -not (Test-Path (Join-Path $ToolDir 'k3d-resolved.yaml'))) {
        throw 'Cluster urumi already exists without an explicit project resume. It will not be replaced.'
    }
    Assert-LocalCluster
}
$source = Join-Path $ProjectRoot 'infra/local/k3d.yaml'
$config = (Get-Content -LiteralPath $source -Raw).Replace('127.0.0.1:80:80',"127.0.0.1:$($preflight.port):80")
$resolved = Join-Path $ToolDir 'k3d-resolved.yaml'
$config | Set-Content -Encoding UTF8 $resolved
if (-not $Resume) {
    $null = Invoke-Native $K3d @('cluster','create','--config',$resolved) 'cluster-create.txt' 240
    Invoke-Native $K3d @('kubeconfig','get','urumi') | Set-Content -Encoding UTF8 $KubeConfig
}
Assert-LocalCluster
$base = @('--kubeconfig',$KubeConfig,'--context','k3d-urumi')
$null = Invoke-Native $Kubectl ($base + @('wait','--for=condition=Ready','node','--all','--timeout=120s')) 'node-ready.txt' 135
foreach ($name in 'coredns','traefik','local-path-provisioner') {
    # Bundled charts may create Deployments after the node first becomes Ready.
    $deadline = (Get-Date).AddSeconds(120)
    do {
        $present = Invoke-Native $Kubectl ($base + @('-n','kube-system','get','deployment',$name,'--ignore-not-found=true','-o','name')) "$name-ready.txt" 20
        if ($present.Trim()) { break }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    if (-not $present.Trim()) { throw "System deployment $name was not created within 120 seconds." }
    $null = Invoke-Native $Kubectl ($base + @('-n','kube-system','rollout','status',"deployment/$name",'--timeout=120s')) "$name-ready.txt" 135
}
$null = Invoke-Native $Kubectl ($base + @('get','nodes','-o','wide')) 'cluster-status.txt' 20
$docker = (Get-Command docker.exe).Source
$tag = 'python:3.13.5-slim-bookworm'
$null = Invoke-Native $docker @('pull',$tag) 'image-pull.txt' 240
$digests = Invoke-Native $docker @('image','inspect',$tag,'--format','{{json .RepoDigests}}') 'image-digests.txt' 20 | ConvertFrom-Json
$image = @($digests | Where-Object { $_ -match '^python@sha256:[a-f0-9]{64}$' })[0]
if (-not $image) { throw 'No immutable Python image digest found; refusing a tag-only deployment.' }
$digest = ($image -split '@')[1]
@{port=$preflight.port;image=$image;digest=$digest} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $ToolDir 'runtime.json')
@{port=$preflight.port;image=$image;digest=$digest} | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'runtime-image.json')
$chart = Join-Path $ProjectRoot 'deploy/charts/urumi'
$null = Invoke-Native $Helm @('lint',$chart,'-f',"$chart/values-module-local.yaml",'-f',"$chart/values-m1.yaml") 'setup-helm-lint.txt' 30
$releases = Invoke-Native $Helm @('--kubeconfig',$KubeConfig,'--kube-context','k3d-urumi','list','--all','--all-namespaces','-o','json') 'existing-releases.txt' 30 | ConvertFrom-Json
if (@($releases | Where-Object { $_.name -eq 'urumi' }).Count) { throw 'An urumi release already exists; refusing to take ownership.' }
$null = Invoke-Native $Helm @('upgrade','--install','urumi',$chart,'--kubeconfig',$KubeConfig,'--kube-context','k3d-urumi','--namespace','urumi','--create-namespace','-f',"$chart/values-module-local.yaml",'-f',"$chart/values-m1.yaml",'--set-string',"foundation.image.digest=$digest",'--set','foundation.networkPolicy.enabled=false','--wait','--timeout','5m') 'foundation-install.txt' 330
Write-Host "Foundation installed. Add 127.0.0.1 foundation.urumi.test to your Windows hosts file, then open http://foundation.urumi.test:$($preflight.port)."
Write-Host 'Next: run scripts/m1/check-foundation.ps1. Do not delete/recreate the cluster to fix a failed later step.'
