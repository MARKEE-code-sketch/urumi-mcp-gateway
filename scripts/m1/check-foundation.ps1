param([switch]$Cleanup)
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/common.ps1"
Assert-LocalCluster
$Chart = Join-Path $ProjectRoot 'deploy/charts/urumi'
$Runtime = Get-Content (Join-Path $ProjectRoot '.tools/m1/runtime.json') -Raw | ConvertFrom-Json
if ($Runtime.digest -notmatch '^sha256:[0-9a-f]{64}$') { throw 'Run setup first: immutable image digest is missing.' }
$KArgs = @('--kubeconfig', $KubeConfig, '--context', 'k3d-urumi', '--namespace', 'urumi')
$HArgs = @('--kubeconfig', $KubeConfig, '--kube-context', 'k3d-urumi', '--namespace', 'urumi')
$Values = @('-f', "$Chart/values-module-local.yaml", '-f', "$Chart/values-m1.yaml", '--set-string', "foundation.image.digest=$($Runtime.digest)")
$Selector = 'app.kubernetes.io/instance=urumi,app.kubernetes.io/component=foundation'
$ResultsPath = Join-Path $EvidenceDir 'results.json'
$Results = [ordered]@{}
1..9 | ForEach-Object { $Results[('M1-{0:00}' -f $_)] = @{ status='BLOCKED'; observed='Not reached'; timestamp=(Get-Date).ToUniversalTime().ToString('o'); evidence=@() } }
$Jobs = [System.Collections.Generic.List[string]]::new()
$JobsPath = Join-Path $EvidenceDir 'check-jobs.json'
if (Test-Path $JobsPath) {
    $recordedJobs = Get-Content $JobsPath -Raw | ConvertFrom-Json
    foreach ($jobName in $recordedJobs) {
        if ($jobName -notmatch '^m1-check-[a-z0-9-]+$') { throw 'Invalid recorded M1 Job name; inspect before cleanup.' }
        $Jobs.Add([string]$jobName)
    }
}
function Save-Results {
    $Results | ConvertTo-Json -Depth 8 | Set-Content $ResultsPath -Encoding UTF8
    ConvertTo-Json -InputObject @($Jobs.ToArray()) | Set-Content $JobsPath -Encoding UTF8
}
function Set-Result($Id, $Status, $Observed, [string[]]$Evidence) {
    $Results[$Id] = @{ status=$Status; observed=$Observed; timestamp=(Get-Date).ToUniversalTime().ToString('o'); evidence=$Evidence }
    Save-Results
}
function K([string[]]$Command, [string]$LogName = 'kubectl.txt') {
    Invoke-Native -File $Kubectl -Arguments ($KArgs + $Command) -LogName $LogName
}
function Upgrade([bool]$Policy, [bool]$Enabled = $true) {
    $p = $Policy.ToString().ToLowerInvariant(); $e = $Enabled.ToString().ToLowerInvariant()
    Invoke-Native -File $Helm -Arguments (@('upgrade','--install','urumi',$Chart,'--create-namespace') + $HArgs + $Values +
        @('--set', "foundation.networkPolicy.enabled=$p", '--set', "foundation.enabled=$e", '--wait','--timeout','120s')) -LogName 'helm-checks.txt'
}
function Get-PagePod {
    $list = K @('get','pods','-l',$Selector,'-o','json') 'storage-check.txt' | ConvertFrom-Json
    $pods = @($list.items | Where-Object { -not $_.metadata.deletionTimestamp })
    if ($pods.Count -ne 1) { throw "Expected one active foundation Pod; got $($pods.Count)." }
    $pod = $pods[0]
    $rsName = @($pod.metadata.ownerReferences | Where-Object { $_.kind -eq 'ReplicaSet' -and $_.controller })[0].name
    if (-not $rsName) { throw 'Page Pod has no controlling ReplicaSet.' }
    $rs = K @('get','replicaset',$rsName,'-o','json') 'storage-check.txt' | ConvertFrom-Json
    if (-not @($rs.metadata.ownerReferences | Where-Object { $_.kind -eq 'Deployment' -and $_.name -eq 'urumi-foundation' -and $_.controller }).Count) { throw 'Page Pod is not owned by the foundation Deployment.' }
    return $pod
}
function Invoke-Caller([string]$Access, [bool]$ExpectDenied = $false) {
    $name = 'm1-check-' + $Access + '-' + ([guid]::NewGuid().ToString('N').Substring(0,10))
    $Jobs.Add($name); Save-Results
    # Exit 42 means DNS worked but TCP was rejected/timed out; HTTP/DNS errors never pass denial.
    $python = @'
import socket, urllib.request, urllib.error, time, sys
host = "urumi-foundation.urumi.svc.cluster.local"
print("DNS", socket.gethostbyname(host), flush=True)
denied = sys.argv[1] == "denied"
deadline = time.monotonic() + 25
while True:
    try:
        with urllib.request.urlopen("http://" + host + "/", timeout=3) as response:
            text = response.read().decode()
        if "Kubernetes is serving this page" not in text:
            raise RuntimeError("Unexpected page body")
        if not denied:
            print("HTTP_MARKER_OK", flush=True)
            break
        if time.monotonic() >= deadline:
            print("DENIAL_NOT_ENFORCED", flush=True)
            sys.exit(2)
        time.sleep(1)
    except urllib.error.HTTPError:
        raise
    except (TimeoutError, urllib.error.URLError) as error:
        reason = getattr(error, "reason", error)
        if denied and isinstance(reason, (TimeoutError, socket.timeout, ConnectionRefusedError)):
            print("TCP_REJECTED_AFTER_DNS" if isinstance(reason, ConnectionRefusedError) else "TCP_TIMEOUT_AFTER_DNS", flush=True)
            sys.exit(42)
        raise
'@
    $mode = if ($ExpectDenied) { 'denied' } else { 'allowed' }
    $manifest = @{
        apiVersion='batch/v1'; kind='Job'
        metadata=@{name=$name; namespace='urumi'; labels=@{'m1-check'='true'; 'm1-access'=$Access; 'app.kubernetes.io/instance'='urumi'}}
        spec=@{backoffLimit=0; activeDeadlineSeconds=30; template=@{
            metadata=@{labels=@{'m1-access'=$Access; 'm1-check'='true'; 'app.kubernetes.io/instance'='urumi'}}
            spec=@{restartPolicy='Never'; automountServiceAccountToken=$false
                securityContext=@{runAsNonRoot=$true; runAsUser=1000; runAsGroup=1000; seccompProfile=@{type='RuntimeDefault'}}
                containers=@(@{name='caller'; image=$Runtime.image; command=@('python','-u','-c',$python,$mode)
                    securityContext=@{allowPrivilegeEscalation=$false; capabilities=@{drop=@('ALL')}}
                    resources=@{requests=@{cpu='25m'; memory='32Mi'}; limits=@{cpu='100m'; memory='64Mi'}}})
            }
        }}
    }
    $path = Join-Path $EvidenceDir "$name.json"
    $manifest | ConvertTo-Json -Depth 15 | Set-Content $path -Encoding UTF8
    $null = K @('create','-f',$path) 'network-policy-check.txt'
    $end = (Get-Date).AddSeconds(45)
    do {
        $job = K @('get','job',$name,'-o','json') 'network-policy-check.txt' | ConvertFrom-Json
        if ($job.status.succeeded -or $job.status.failed) { break }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $end)
    $pods = K @('get','pods','-l',"job-name=$name",'-o','json') 'network-policy-check.txt' | ConvertFrom-Json
    $output = K @('logs',"job/$name",'--all-containers=true') 'network-policy-check.txt'
    $exitCode = $null
    foreach ($pod in $pods.items) { foreach ($container in $pod.status.containerStatuses) { if ($container.state.terminated) { $exitCode = $container.state.terminated.exitCode } } }
    return @{name=$name; exitCode=$exitCode; output=$output}
}
function Assert-Caller($Run, [bool]$Denied = $false) {
    if ($Denied) {
        if ($Run.exitCode -ne 42 -or $Run.output -notmatch 'TCP_(TIMEOUT|REJECTED)_AFTER_DNS' -or $Run.output -notmatch 'DNS ') { throw "Caller did not prove TCP rejection/timeout after DNS: $($Run | ConvertTo-Json -Compress)" }
    } elseif ($Run.exitCode -ne 0 -or $Run.output -notmatch 'HTTP_MARKER_OK') { throw "Caller failed: $($Run | ConvertTo-Json -Compress)" }
}
function Check-Http {
    $url = "http://foundation.urumi.test:$($Runtime.port)/"
    $body = Invoke-Native -File 'curl.exe' -Arguments @('--noproxy','*','--fail','--silent','--show-error','--max-time','10','--resolve',"foundation.urumi.test:$($Runtime.port):127.0.0.1",$url) -LogName 'ingress-check.txt'
    if ($body -notmatch 'Kubernetes is serving this page') { throw 'Ingress returned unexpected page.' }
    return $url
}
$Current = 'M1-01'
try {
    if ($Cleanup) {
        if (Test-Path $ResultsPath) {
            $old = Get-Content $ResultsPath -Raw | ConvertFrom-Json
            foreach ($property in $old.PSObject.Properties) { $Results[$property.Name] = $property.Value }
        }
        $Current = 'M1-09'
        $pvc = K @('get','pvc','urumi-foundation-data','-o','json') 'cleanup-check.txt' | ConvertFrom-Json
        $null = Upgrade $true $false
        foreach ($job in $Jobs) {
            $owned = K @('get','job',$job,'--ignore-not-found=true','-o','json') 'cleanup-check.txt'
            if ($owned.Trim()) {
                $record = $owned | ConvertFrom-Json
                if ($record.metadata.labels.'m1-check' -ne 'true' -or $record.metadata.labels.'app.kubernetes.io/instance' -ne 'urumi') { throw "Job $job is not an owned M1 test resource." }
                $null = K @('delete','job',$job,'--cascade=foreground','--wait=true','--timeout=30s') 'cleanup-check.txt'
            }
        }
        $testResources = K @('get','jobs,pods','-l','m1-check=true,app.kubernetes.io/instance=urumi','-o','json') 'cleanup-check.txt' | ConvertFrom-Json
        if (@($testResources.items).Count) { throw 'M1 test Jobs or Pods remain after cleanup.' }
        $remaining = K @('get','deployment,service,ingress,configmap,networkpolicy','-l',$Selector,'-o','json') 'cleanup-check.txt' | ConvertFrom-Json
        $retained = K @('get','pvc','urumi-foundation-data','-o','json') 'cleanup-check.txt' | ConvertFrom-Json
        if (@($remaining.items).Count -or $retained.metadata.uid -ne $pvc.metadata.uid) { throw 'Cleanup left resources or did not retain original PVC.' }
        @('Foundation disabled using the same release/chart.','Only explicitly recorded M1 Jobs deleted. PVC retained with original UID. Cluster not deleted.','Restore: rerun check-foundation.ps1 to enable the page in the same existing release. Recreating a release may require retained PVC adoption review.') | Set-Content (Join-Path $EvidenceDir 'cleanup-notes.md') -Encoding UTF8
        Set-Result 'M1-09' 'PASS' 'Foundation disabled, recorded checking Jobs removed, original PVC retained.' @('cleanup-check.txt','cleanup-notes.md')
        return
    }
    $nodes = K @('get','nodes','-o','json') 'cluster-status.txt' | ConvertFrom-Json
    if (-not @($nodes.items).Count -or @($nodes.items | Where-Object { -not @($_.status.conditions | Where-Object { $_.type -eq 'Ready' -and $_.status -eq 'True' }).Count }).Count) { throw 'Cluster nodes are not all Ready.' }
    $preflight = Get-Content (Join-Path $EvidenceDir 'preflight.json') -Raw | ConvertFrom-Json
    $tools = Get-Content (Join-Path $EvidenceDir 'tool-install.json') -Raw | ConvertFrom-Json
    if ($preflight.status -ne 'PASS' -or $preflight.docker.cpus -lt 1 -or $preflight.docker.memoryBytes -le 0 -or $tools.k3d.version -ne 'v5.9.0' -or $tools.helm.version -ne 'v3.21.3') { throw 'Preflight or verified tool installation evidence is incomplete.' }
    $null = Invoke-Native $K3d @('version') 'k3d-version.txt' 20
    Set-Result 'M1-01' 'PASS' 'Nodes Ready; Docker allocation, selected port, kubectl, and checksum-verified portable tool versions recorded.' @('cluster-status.txt','preflight.json','tool-install.json','k3d-version.txt')
    $Current = 'M1-02'
    foreach ($files in @(@('values-module-local.yaml','values-m1.yaml'), @('values-module-prod.yaml'))) {
        $flags = @(); foreach ($file in $files) { $flags += @('-f',"$Chart/$file") }
        $null = Invoke-Native -File $Helm -Arguments (@('lint',$Chart) + $flags + @('--set-string',"foundation.image.digest=$($Runtime.digest)")) -LogName 'helm-checks.txt'
        $render = Invoke-Native -File $Helm -Arguments (@('template','urumi',$Chart,'--namespace','urumi') + $flags + @('--set-string',"foundation.image.digest=$($Runtime.digest)")) -LogName 'helm-checks.txt'
        $render | Set-Content (Join-Path $EvidenceDir ("rendered-" + $files[0] + '.txt')) -Encoding UTF8
        if ($files[0] -eq 'values-module-prod.yaml' -and $render -match '(?m)^kind:') { throw 'Production render includes temporary workload.' }
    }
    Set-Result 'M1-02' 'PASS' 'Local+M1 and production-shaped values linted/rendered; production excludes temporary resources.' @('helm-checks.txt','rendered-values-module-local.yaml.txt','rendered-values-module-prod.yaml.txt')
    $Current = 'M1-04'
    $null = Upgrade $false
    Assert-Caller (Invoke-Caller 'allowed')
    Assert-Caller (Invoke-Caller 'denied')
    Set-Result 'M1-04' 'PASS' 'Both baseline callers resolved Service DNS and received expected page.' @('network-policy-check.txt')
    $Current = 'M1-06'
    $null = Upgrade $true
    Assert-Caller (Invoke-Caller 'allowed')
    Assert-Caller (Invoke-Caller 'denied' $true) $true
    Assert-Caller (Invoke-Caller 'allowed')
    $url = Check-Http
    Set-Result 'M1-06' 'PASS' 'Baseline worked; policy allowed one caller, rejected/timed out TCP after successful DNS for other; fresh allowed call and Ingress worked.' @('network-policy-check.txt','ingress-check.txt')
    Set-Result 'M1-03' 'BLOCKED' "Ingress HTTP proved at $url via curl --resolve. Actual browser/hostname setup and screenshot remain manual." @('ingress-check.txt')
    $Current = 'M1-05'
    $oldPod = Get-PagePod
    $marker = 'm1-' + [guid]::NewGuid().ToString('N')
    $null = K @('exec',$oldPod.metadata.name,'--','python','-c','import pathlib,sys; pathlib.Path("/data/persistence-marker.txt").write_text(sys.argv[1])',$marker) 'storage-check.txt'
    $read = K @('exec',$oldPod.metadata.name,'--','python','-c','import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/persistence-marker.txt",timeout=5).read().decode())') 'storage-check.txt'
    if ($read.Trim() -ne $marker) { throw 'Initial HTTP marker mismatch.' }
    $null = K @('delete','pod',$oldPod.metadata.name,'--wait=true','--timeout=60s') 'storage-check.txt'
    $null = K @('rollout','status','deployment/urumi-foundation','--timeout=120s') 'storage-check.txt'
    $newPod = Get-PagePod
    if ($newPod.metadata.uid -eq $oldPod.metadata.uid) { throw 'Pod UID did not change.' }
    $read = K @('exec',$newPod.metadata.name,'--','python','-c','import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/persistence-marker.txt",timeout=5).read().decode())') 'storage-check.txt'
    if ($read.Trim() -ne $marker) { throw 'Marker did not survive replacement.' }
    @{oldUid=$oldPod.metadata.uid; newUid=$newPod.metadata.uid; marker=$marker} | ConvertTo-Json | Set-Content (Join-Path $EvidenceDir 'storage-result.json') -Encoding UTF8
    Set-Result 'M1-05' 'PASS' 'HTTP-readable marker survived replacement with a different Pod UID.' @('storage-check.txt','storage-result.json')
    $Current = 'M1-07'
    $deployment = K @('get','deployment','urumi-foundation','-o','json') 'workload-settings.txt' | ConvertFrom-Json
    foreach ($container in $deployment.spec.template.spec.containers) {
        if (-not $container.readinessProbe.httpGet -or -not $container.livenessProbe.httpGet -or -not $container.resources.requests.cpu -or -not $container.resources.requests.memory -or -not $container.resources.limits.cpu -or -not $container.resources.limits.memory) { throw 'Missing probes/resources.' }
    }
    if ($deployment.status.readyReplicas -ne 1) { throw 'Page is not Ready.' }
    $null = K @('get','deployments','-n','kube-system','-o','json') 'infrastructure-settings.txt'
    Set-Result 'M1-07' 'PASS' 'Probes/resources present; replica Ready after automatic replacement; infrastructure recorded separately.' @('workload-settings.txt','infrastructure-settings.txt','storage-result.json')
    $Current = 'M1-08'
    $services = K @('get','services','-o','json') 'exposure-check.txt' | ConvertFrom-Json
    foreach ($service in $services.items) { if ($service.spec.type -in @('NodePort','LoadBalancer')) { throw "Unexpected exposed application Service: $($service.metadata.name)" } }
    $ingresses = K @('get','ingress','-o','json') 'exposure-check.txt' | ConvertFrom-Json
    if (@($ingresses.items).Count -ne 1 -or $ingresses.items[0].metadata.name -ne 'urumi-foundation') { throw 'Unexpected application Ingress list.' }
    $null = K @('get','services','-n','kube-system','-o','wide') 'exposure-check.txt'
    Set-Result 'M1-08' 'PASS' "Only foundation Ingress public via loopback port $($Runtime.port); application Services internal; infrastructure recorded separately." @('exposure-check.txt')
    Set-Result 'M1-09' 'BLOCKED' 'Save browser screenshot first, then run -Cleanup. PVC will be retained.' @()
} catch {
    Set-Result $Current 'FAIL' $_.Exception.Message @('helm-checks.txt','network-policy-check.txt','storage-check.txt')
    throw
} finally { Save-Results }
Write-Host "Evidence saved to $EvidenceDir. Browser screenshot and explicit -Cleanup remain separate."
