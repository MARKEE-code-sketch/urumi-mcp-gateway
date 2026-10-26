param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../m1/common.ps1')
$EvidenceDir = Join-Path $ProjectRoot 'docs/evidence/m4'
New-Item -ItemType Directory -Force $EvidenceDir | Out-Null
$Namespace = 'urumi-m4-check'
$Release = 'urumi-m4-check'
$McpName = "$Release-inventory-mcp"
$Image = 'urumi/inventory-mcp:m4'
$Created = $false
$Results = [ordered]@{module='M4';status='RUNNING';checks=@()}
function Kube {
    param([string[]]$KArgs, [string]$Log='cluster-commands.txt')
    Invoke-Native $Kubectl (@('--kubeconfig',$KubeConfig,'--context','k3d-urumi') + $KArgs) $Log 180
}
function Add-Check {
    param([string]$Id, [string]$Summary)
    $Results.checks += [ordered]@{id=$Id;status='PASS';summary=$Summary}
    $Results | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'results.json')
}
function Snapshot-Store {
    $resources = Kube @('-n','urumi','get','deployments,statefulsets,services,pvc','-o','json') | ConvertFrom-Json
    return @($resources.items | ForEach-Object { "$($_.kind)/$($_.metadata.name)/$($_.metadata.uid)" } | Sort-Object)
}
function Client-Check {
    param([string]$Name, [string]$Mode)
    $component = if ($Mode -eq 'allowed') {'gateway'} else {'unrelated'}
    $url = if ($Mode -eq 'hosted') {'https://learn.microsoft.com/api/mcp'} else {"http://${McpName}.${Namespace}.svc.cluster.local:8000/mcp"}
    $job = @{
        apiVersion='batch/v1';kind='Job';metadata=@{name=$Name;namespace=$Namespace}
        spec=@{backoffLimit=0;activeDeadlineSeconds=90;template=@{
            metadata=@{labels=@{'app.kubernetes.io/name'='urumi';'app.kubernetes.io/instance'=$Release;'app.kubernetes.io/component'=$component}}
            spec=@{restartPolicy='Never';automountServiceAccountToken=$false
                securityContext=@{runAsNonRoot=$true;runAsUser=10001;runAsGroup=10001;seccompProfile=@{type='RuntimeDefault'}}
                containers=@(@{name='client';image=$Image;imagePullPolicy='IfNotPresent'
                    command=@('python','tests/sample_mcps/cluster_client.py','--url',$url,'--mode',$Mode)
                    securityContext=@{readOnlyRootFilesystem=$true;allowPrivilegeEscalation=$false;capabilities=@{drop=@('ALL')}}
                    resources=@{requests=@{cpu='50m';memory='64Mi'};limits=@{cpu='250m';memory='128Mi'}}
                })
            }
        }}
    }
    $path = Join-Path $EvidenceDir "$Name.job.json"
    $job | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $path
    Kube @('apply','-f',$path) | Out-Null
    try { Kube @('-n',$Namespace,'wait',"job/$Name",'--for=condition=complete','--timeout=95s') | Out-Null }
    finally { Kube @('-n',$Namespace,'logs',"job/$Name") | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir "$Name.json") }
}
try {
    Assert-LocalCluster
    $existing = Kube @('get','namespace',$Namespace,'--ignore-not-found','-o','name')
    if ($existing.Trim()) { throw 'M4 check namespace already exists; inspect ownership and prior cleanup before rerunning.' }
    $BeforeStore = @(Snapshot-Store)
    $BeforeStore | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'store-before.txt')
    Invoke-Native (Join-Path $ProjectRoot '.venv/Scripts/python.exe') @('-m','unittest','discover','-s','tests/sample_mcps','-p','test_*.py','-v') 'host-tests.txt' 180 | Out-Null
    Add-Check 'M4-01' 'Fixture, strict input validation, exact results and invalid startup cases'
    Add-Check 'M4-02' 'Real TCP SDK discovery, exact schemas/annotations, calls and protocol errors'
    Add-Check 'M4-06' 'Controlled real TCP bearer/header authentication and duplicate names; artificial values absent from outputs'
    Add-Check 'M4-07' 'Bounded controlled timeout/transport/protocol/size/cursor failures followed by healthy Inventory'
    if (-not $SkipBuild) {
        Invoke-Native 'docker.exe' @('build','-t',$Image,'-f','services/sample_mcps/Dockerfile','.') 'image-build.txt' 900 | Out-Null
    }
    $imageInfo = Invoke-Native 'docker.exe' @('image','inspect',$Image) 'image-inspect.json.txt' | ConvertFrom-Json
    $identityArchive = Join-Path $ProjectRoot '.tools/m4/image-identity.tar'
    New-Item -ItemType Directory -Force (Split-Path $identityArchive -Parent) | Out-Null
    Invoke-Native 'docker.exe' @('image','save','-o',$identityArchive,$Image) 'image-save.txt' 180 | Out-Null
    Invoke-Native (Join-Path $ProjectRoot '.venv/Scripts/python.exe') @('scripts/m4/image_identity.py',$identityArchive,'--image',$Image,'--output','docs/evidence/m4/image-identity-check.json') 'image-identity-command.txt' | Out-Null
    $identity = Get-Content (Join-Path $EvidenceDir 'image-identity-check.json') -Raw | ConvertFrom-Json
    Invoke-Native 'docker.exe' @('run','--rm',$Image,'python','-m','pip','check') 'linux-pip-check.txt' | Out-Null
    Invoke-Native 'docker.exe' @('run','--rm',$Image,'python','-m','unittest','discover','-s','tests/sample_mcps','-p','test_*.py','-v') 'linux-tests.txt' 180 | Out-Null
    Invoke-Native $K3d @('image','import',$Image,'-c','urumi') 'image-import.txt' 360 | Out-Null
    Invoke-Native $Helm @('lint','deploy/charts/urumi') 'helm-checks.txt' | Out-Null
    foreach ($environment in @('local','prod')) {
        Invoke-Native $Helm @('template','urumi','deploy/charts/urumi','-n','urumi','-f',"deploy/charts/urumi/values-$environment.yaml",'--set','inventoryMcp.enabled=true') "render-$environment.yaml.txt" | Out-Null
    }
    Invoke-Native (Join-Path $ProjectRoot '.venv/Scripts/python.exe') @('scripts/m4/probe.py','--output','docs/evidence/m4/hosted-local.json') 'hosted-local-command.txt' 65 | Out-Null
    Kube @('create','namespace',$Namespace) | Out-Null
    $Created = $true
    Kube @('label','namespace',$Namespace,'urumi-check-owner=m4') | Out-Null
    Invoke-Native $Helm @('--kubeconfig',$KubeConfig,'--kube-context','k3d-urumi','upgrade','--install',$Release,'deploy/charts/urumi','-n',$Namespace,'-f','tests/sample_mcps/values-check.yaml','--wait','--timeout','180s') 'helm-install.txt' 240 | Out-Null
    Kube @('-n',$Namespace,'get','deployments,pods,services,networkpolicies','-o','yaml') 'workload-status.yaml.txt' | Out-Null
    $exposure = Kube @('-n',$Namespace,'get','services,ingresses','-o','json') 'exposure.json.txt' | ConvertFrom-Json
    foreach ($item in @($exposure.items)) {
        if ($item.kind -eq 'Ingress' -or ($item.kind -eq 'Service' -and $item.spec.type -ne 'ClusterIP')) { throw 'Inventory has public exposure.' }
    }
    $podInfo = Kube @('-n',$Namespace,'get','pods','-l','app.kubernetes.io/component=inventory-mcp','-o','json') | ConvertFrom-Json
    foreach ($pod in @($podInfo.items)) {
        if (-not $pod.spec.containers[0].readinessProbe -or -not $pod.spec.containers[0].livenessProbe -or -not $pod.spec.containers[0].resources.requests -or -not $pod.spec.containers[0].resources.limits) { throw 'Missing probes or resource budget.' }
        if ($pod.status.containerStatuses[0].imageID -notlike "*$($identity.config_digest.Replace('sha256:',''))") { throw 'Running image identity does not match exported image configuration.' }
    }
    Add-Check 'M4-03' 'Linux package/tests, same local/production chart, Ready internal workload and matching image'
    Client-Check 'm4-allowed-first' 'allowed'
    Client-Check 'm4-denied' 'denied'
    Client-Check 'm4-allowed-again' 'allowed'
    $badProbe = '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/m4-missing-livez"}]'
    Kube @('-n',$Namespace,'patch','deployment',$McpName,'--type=json','-p',$badProbe) | Out-Null
    Kube @('-n',$Namespace,'rollout','status',"deployment/$McpName",'--timeout=120s') | Out-Null
    $badPods = Kube @('-n',$Namespace,'get','pods','-l','app.kubernetes.io/component=inventory-mcp','-o','json') | ConvertFrom-Json
    $badPod = @($badPods.items | Where-Object { -not $_.metadata.deletionTimestamp })[0]
    $targetUid = $badPod.metadata.uid
    $deadline = [DateTime]::UtcNow.AddSeconds(85)
    $restart = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $observed = Kube @('-n',$Namespace,'get','pod',$badPod.metadata.name,'-o','json') | ConvertFrom-Json
        if ($observed.metadata.uid -ne $targetUid) { throw 'Pod replacement cannot prove a liveness restart.' }
        if ($observed.status.containerStatuses[0].restartCount -gt 0) { $restart=$observed; break }
        Start-Sleep -Seconds 3
    }
    if (-not $restart) { throw 'No actual failing-liveness container restart observed.' }
    $restart | ConvertTo-Json -Depth 30 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'liveness-restart-pod.json')
    Kube @('-n',$Namespace,'get','events','--field-selector',"involvedObject.uid=$targetUid",'--sort-by=.metadata.creationTimestamp') 'probe-events.txt' | Out-Null
    Kube @('-n',$Namespace,'patch','deployment',$McpName,'--type=json','-p','[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/livez"}]') | Out-Null
    Kube @('-n',$Namespace,'rollout','status',"deployment/$McpName",'--timeout=120s') | Out-Null
    Client-Check 'm4-probe-recovered' 'allowed'
    Add-Check 'M4-04' 'Allowed-denied-allowed and same-Pod actual kubelet liveness restart, restored recovery'
    Client-Check 'm4-hosted-cluster' 'hosted'
    Add-Check 'M4-05' 'Fresh real local and cluster hosted discovery/call; meaningful source review required before acceptance'
} catch {
    $Results.status = 'FAIL'
    $_ | Out-String | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'failure.txt')
    throw
} finally {
    if ($Created) {
        $owner = Kube @('get','namespace',$Namespace,'-o','jsonpath={.metadata.labels.urumi-check-owner}')
        if ($owner.Trim() -ne 'm4') { throw 'Refusing namespace cleanup: ownership label changed.' }
        Kube @('delete','namespace',$Namespace,'--wait=true','--timeout=120s') 'cleanup.txt' | Out-Null
        $remaining = Kube @('get','namespace',$Namespace,'--ignore-not-found','-o','name')
        if ($remaining.Trim()) { throw 'M4 check namespace still exists.' }
        $AfterStore = @(Snapshot-Store)
        $AfterStore | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'store-after.txt')
        if (Compare-Object $BeforeStore $AfterStore) { throw 'Existing store resource identities changed.' }
        Add-Check 'M4-08' 'Owned temporary namespace removed; original store resources and PVC identities unchanged'
    }
    if ($Results.status -eq 'RUNNING') { $Results.status='PASS_RUNTIME_REVIEW_PENDING' }
    $Results | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'results.json')
}
