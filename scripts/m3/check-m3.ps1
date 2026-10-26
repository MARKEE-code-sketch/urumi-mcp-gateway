param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '../m1/common.ps1')
$EvidenceDir = Join-Path $ProjectRoot 'docs/evidence/m3'
New-Item -ItemType Directory -Force $EvidenceDir | Out-Null
$Namespace = 'urumi-m3-check'
$Release = 'urumi-m3-check'
$McpName = 'urumi-m3-check-woocommerce-mcp'
$Created = $false
$Results = [ordered]@{module='M3'; fixture_only=$true; status='RUNNING'; checks=@()}
function Kube {
    param([string[]]$KArgs, [string]$Log='cluster-commands.txt')
    Invoke-Native $Kubectl (@('--kubeconfig',$KubeConfig,'--context','k3d-urumi') + $KArgs) $Log 180
}
function Add-Check {
    param([string]$Name)
    $Results.checks += [ordered]@{name=$Name;status='PASS'}
    $Results | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'results.json')
}
function Snapshot-Store {
    $raw = Kube @('-n','urumi','get','deployments,statefulsets,services,pvc','-o','json')
    $items = @((($raw | ConvertFrom-Json).items) | ForEach-Object {
        "$($_.kind)/$($_.metadata.name)/$($_.metadata.uid)"
    } | Sort-Object)
    return $items
}
function Client-Check {
    param([string]$Name, [string]$Mode)
    $component = if ($Mode -eq 'allowed') {'gateway'} else {'unrelated'}
    $job = @{
        apiVersion='batch/v1'; kind='Job'; metadata=@{name=$Name;namespace=$Namespace}
        spec=@{backoffLimit=0;activeDeadlineSeconds=90;template=@{
            metadata=@{labels=@{'app.kubernetes.io/name'='urumi';'app.kubernetes.io/instance'=$Release;'app.kubernetes.io/component'=$component}}
            spec=@{restartPolicy='Never';automountServiceAccountToken=$false
                securityContext=@{runAsNonRoot=$true;runAsUser=10001;runAsGroup=10001;seccompProfile=@{type='RuntimeDefault'}}
                containers=@(@{name='client';image='urumi/woocommerce-mcp:m3';imagePullPolicy='IfNotPresent'
                    command=@('python','tests/woocommerce_mcp/cluster_client.py','--url',"http://${McpName}.${Namespace}.svc.cluster.local:8000/mcp",'--mode',$Mode)
                    securityContext=@{readOnlyRootFilesystem=$true;allowPrivilegeEscalation=$false;capabilities=@{drop=@('ALL')}}
                    resources=@{requests=@{cpu='50m';memory='64Mi'};limits=@{cpu='250m';memory='128Mi'}}
                })
            }
        }}
    }
    $jobPath = Join-Path $EvidenceDir "$Name.job.json"
    $job | ConvertTo-Json -Depth 20 | Set-Content -Encoding UTF8 $jobPath
    Kube @('apply','-f',$jobPath) | Out-Null
    try { Kube @('-n',$Namespace,'wait',"job/$Name",'--for=condition=complete','--timeout=95s') | Out-Null }
    finally {
        try { Kube @('-n',$Namespace,'logs',"job/$Name") | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir "$Name.json") }
        catch { $_ | Out-String | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir "$Name-log-error.txt") }
    }
}
try {
    Assert-LocalCluster
    Kube @('get','nodes','-o','wide') 'preflight.txt' | Out-Null
    Kube @('get','nodes','-o','json') 'capacity.json.txt' | Out-Null
    Kube @('describe','nodes') 'capacity.txt' | Out-Null
    $existing = Kube @('get','namespace',$Namespace,'--ignore-not-found','-o','name')
    if ($existing.Trim()) { throw 'Dedicated M3 check namespace already exists; inspect its ownership and prior cleanup before rerunning.' }
    $BeforeStore = @(Snapshot-Store)
    $BeforeStore | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'store-before.txt')
    $runtime = Get-Content (Join-Path $ToolDir 'runtime.json') -Raw | ConvertFrom-Json
    if ($runtime.image -notmatch '^python@sha256:[a-f0-9]{64}$') { throw 'M1 immutable Python base image is missing.' }
    if (-not $SkipBuild) {
        Invoke-Native 'docker.exe' @('build','--build-arg',"PYTHON_IMAGE=$($runtime.image)",'-t','urumi/woocommerce-mcp:m3','-f','services/woocommerce_mcp/Dockerfile','.') 'image-build.txt' 900 | Out-Null
    }
    Invoke-Native 'docker.exe' @('image','inspect','urumi/woocommerce-mcp:m3') 'image-inspect.json.txt' | Out-Null
    Invoke-Native 'docker.exe' @('run','--rm','urumi/woocommerce-mcp:m3','python','-m','pip','check') 'linux-pip-check.txt' | Out-Null
    Invoke-Native $K3d @('image','import','urumi/woocommerce-mcp:m3','-c','urumi') 'image-import.txt' 360 | Out-Null
    Invoke-Native $Helm @('lint','deploy/charts/urumi') 'helm-checks.txt' | Out-Null
    foreach ($environment in @('local','prod')) {
        Invoke-Native $Helm @('template','urumi','deploy/charts/urumi','-n','urumi','-f',"deploy/charts/urumi/values-$environment.yaml",'--set','woocommerceMcp.enabled=true') "render-$environment.yaml.txt" | Out-Null
    }
    Add-Check 'Linux image and shared local/production chart render'
    Kube @('create','namespace',$Namespace) | Out-Null
    $Created = $true
    Kube @('label','namespace',$Namespace,'urumi-check-owner=m3') | Out-Null
    Kube @('apply','-f','tests/woocommerce_mcp/harness.yaml') | Out-Null
    Invoke-Native $Helm @('--kubeconfig',$KubeConfig,'--kube-context','k3d-urumi','upgrade','--install',$Release,'deploy/charts/urumi','-n',$Namespace,'-f','tests/woocommerce_mcp/values-check.yaml','--wait','--timeout','180s') 'helm-install.txt' 240 | Out-Null
    Kube @('-n',$Namespace,'rollout','status','deployment/m3-fake-shop','--timeout=120s') | Out-Null
    Kube @('-n',$Namespace,'get','deployments,pods,services,networkpolicies','-o','yaml') 'workload-status.yaml.txt' | Out-Null
    Client-Check 'm3-allowed-first' 'allowed'
    Client-Check 'm3-denied' 'denied'
    Client-Check 'm3-allowed-again' 'allowed'
    Add-Check 'Real MCP five tools, allowed-denied-allowed NetworkPolicy'
    $exposure = Kube @('-n',$Namespace,'get','services,ingresses','-o','json') 'exposure.json.txt' | ConvertFrom-Json
    foreach ($resource in @($exposure.items)) {
        if ($resource.kind -eq 'Ingress' -or ($resource.kind -eq 'Service' -and $resource.spec.type -ne 'ClusterIP')) { throw 'M3 harness has public exposure.' }
    }
    Add-Check 'Internal-only exposure'
    # A deliberately invalid liveness path creates an observable kubelet restart.
    $badProbe = '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/m3-deliberate-missing-livez"}]'
    Kube @('-n',$Namespace,'patch','deployment',$McpName,'--type=json','-p',$badProbe) | Out-Null
    Kube @('-n',$Namespace,'rollout','status',"deployment/$McpName",'--timeout=120s') | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(85)
    $restarted = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $pods = Kube @('-n',$Namespace,'get','pods','-l','app.kubernetes.io/component=woocommerce-mcp','-o','json') | ConvertFrom-Json
        foreach ($pod in @($pods.items)) {
            foreach ($container in @($pod.status.containerStatuses)) { if ($container.restartCount -gt 0) { $restarted = $true } }
        }
        if ($restarted) { break }
        Start-Sleep -Seconds 3
    }
    Kube @('-n',$Namespace,'get','events','--sort-by=.metadata.creationTimestamp') 'probe-events.txt' | Out-Null
    Kube @('-n',$Namespace,'get','pods','-o','json') 'probe-restart.json.txt' | Out-Null
    if (-not $restarted) { throw 'No liveness-triggered restart observed.' }
    $goodProbe = '[{"op":"replace","path":"/spec/template/spec/containers/0/livenessProbe/httpGet/path","value":"/livez"}]'
    Kube @('-n',$Namespace,'patch','deployment',$McpName,'--type=json','-p',$goodProbe) | Out-Null
    Kube @('-n',$Namespace,'rollout','status',"deployment/$McpName",'--timeout=120s') | Out-Null
    Client-Check 'm3-after-probe' 'allowed'
    Add-Check 'Observed liveness restart and restored Ready service'
    $logs = Kube @('-n',$Namespace,'logs',"deployment/$McpName")
    $logs | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'translator-logs.txt')
    if ($logs -match 'cs_m3_public_fixture|SENTINEL-CONTACT|oauth_signature|oauth_consumer_key') { throw 'Sensitive fixture values appeared in translator logs.' }
    Add-Check 'Log sentinel redaction'
    $Results.status = 'PASS'
} catch {
    $Results.status = 'FAIL'
    $Results.error = $_.Exception.Message
    if ($Created) {
        try { Kube @('-n',$Namespace,'get','pods,events','-o','yaml') 'failure-state.yaml.txt' | Out-Null } catch {}
    }
    throw
} finally {
    if ($Created) {
        try {
            $owned = Kube @('get','namespace',$Namespace,'-o','json') | ConvertFrom-Json
            if ($owned.metadata.labels.'urumi-check-owner' -ne 'm3') { throw 'Namespace ownership check failed; cleanup refused.' }
            Invoke-Native $Helm @('--kubeconfig',$KubeConfig,'--kube-context','k3d-urumi','uninstall',$Release,'-n',$Namespace,'--ignore-not-found','--wait','--timeout','120s') 'cleanup.txt' 180 | Out-Null
            Kube @('delete','namespace',$Namespace,'--wait=true','--timeout=120s') 'cleanup.txt' | Out-Null
            $remaining = Kube @('get','namespace',$Namespace,'--ignore-not-found','-o','name') 'cleanup.txt'
            if ($remaining.Trim()) { throw 'M3 namespace remains.' }
            $after = @(Snapshot-Store)
            $after | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'store-after.txt')
            if (Compare-Object $BeforeStore $after) { throw 'M2 resource identities changed during the isolated check.' }
            Add-Check 'Temporary namespace removed; M2 resource UIDs unchanged'
        } catch {
            $Results.status = 'FAIL'
            $Results.cleanup_error = $_.Exception.Message
            Write-Error $_ -ErrorAction Continue
        }
    }
    $Results | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'results.json')
}
if ($Results.status -ne 'PASS') { throw 'M3 checks or cleanup failed; inspect docs/evidence/m3/results.json.' }
