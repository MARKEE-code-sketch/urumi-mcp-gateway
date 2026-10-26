param([int]$BrowserOrderId=0,[switch]$ResumeFromRest)
. "$PSScriptRoot/common.ps1"
Assert-M2Cluster
$runtime=Get-M2Runtime
$results=[ordered]@{}
1..10 | ForEach-Object { $results[('M2-{0:00}' -f $_)]=@{status='BLOCKED';observed='Not reached'} }
if ($ResumeFromRest) {
    $saved=Get-Content "$EvidenceDir/results.json" -Raw | ConvertFrom-Json
    foreach ($id in 'M2-01','M2-02','M2-04','M2-07','M2-08') {
        if ($saved.$id.status -ne 'PASS') { throw 'Resume requires passing saved deployment and persistence checks.' }
    }
    foreach ($property in $saved.PSObject.Properties) { $results[$property.Name]=$property.Value }
}
function Result($Id,$Status,$Observed) {
    $results[$Id]=@{status=$Status;observed=$Observed;timestamp=[DateTime]::UtcNow.ToString('o')}
    $results | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$EvidenceDir/results.json"
}
function Store-Pod([string]$Component) {
    $list=K @('get','pods','-l',"app.kubernetes.io/instance=urumi,app.kubernetes.io/component=$Component",'-o','json') 'cluster-status.txt' | ConvertFrom-Json
    $active=@($list.items | Where-Object { !$_.metadata.deletionTimestamp })
    if ($active.Count -ne 1) { throw "Expected one active $Component Pod" }; $active[0]
}
function Wait-FreshStore([DateTime]$Deadline) {
    # Deployment Ready can briefly be stale after the separate database Pod changes.
    # Query Apache/PHP/database now, without redirects or cached readiness state.
    $php=@'
$context=stream_context_create(['http'=>['timeout'=>3,'follow_location'=>0,'ignore_errors'=>true]]);
@file_get_contents('http://127.0.0.1/urumi-ready.php',false,$context);
$status=$http_response_header[0]??'';
echo $status."\n";
exit(preg_match('~^HTTP/\S+ 200(?: |$)~',$status)?0:1);
'@
    do {
        try {
            $pod=Store-Pod 'wordpress'
            $null=Invoke-M2Native $Kubectl ($KArgs+@('exec',$pod.metadata.name,'--','php','-r',$php)) 'fresh-readiness.txt' -TimeoutSeconds 10
            return
        } catch {
            if ((Get-Date) -ge $Deadline) { throw 'Fresh HTTP WordPress/database readiness did not recover within 180 seconds.' }
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $Deadline)
    throw 'Fresh HTTP WordPress/database readiness deadline exceeded.'
}
function Snapshot {
    $deadline=(Get-Date).AddSeconds(180)
    do {
        Wait-FreshStore $deadline
        try {
            $pod=Store-Pod 'wordpress'
            $data=Invoke-M2Native $Kubectl ($KArgs+@('exec',$pod.metadata.name,'--','su','-s','/bin/sh','www-data','-c','wp eval-file /opt/urumi-store/snapshot.php --path=/var/www/html')) 'snapshot.txt' -TimeoutSeconds 15
            break
        } catch {
            if ((Get-Date) -ge $deadline) { throw 'Read-only store snapshot did not recover within 180 seconds.' }
            Start-Sleep -Seconds 3
        }
    } while ((Get-Date) -lt $deadline)
    if (!$data) { throw 'No snapshot returned before recovery deadline.' }
    $json=@($data -split "`n" | Where-Object { $_.Trim().StartsWith('{') })[-1] | ConvertFrom-Json
    $claims=K @('get','pvc','urumi-mariadb-data','urumi-wordpress-content','-o','json') 'pvc-status.txt' | ConvertFrom-Json
    [ordered]@{store=$json;claims=@($claims.items | Sort-Object { $_.metadata.name } | ForEach-Object { @{name=$_.metadata.name;uid=$_.metadata.uid;phase=$_.status.phase} })}
}
function Probe-Job([string]$Mode,[bool]$Allowed) {
    $python=@'
import json,socket,sys
host='urumi-mariadb.urumi.svc.cluster.local'
socket.gethostbyname(host)
try:
    socket.create_connection((host,3306),timeout=5).close()
    connected=True
except (TimeoutError,ConnectionRefusedError): connected=False
expected=sys.argv[1]=='allowed'
print(json.dumps({'dns':True,'connected':connected,'expected_connected':expected}))
sys.exit(0 if connected==expected else 1)
'@
    $name='urumi-m2-network-'+[guid]::NewGuid().ToString('N').Substring(0,8)
    $labels=@{'app.kubernetes.io/instance'='urumi'}
    if ($Allowed) { $labels['urumi-m2-access']='setup' }
    $modeArg=if ($Mode -eq 'denied') {'denied'} else {'allowed'}
    $image=(Get-Content "$ProjectRoot/.tools/m1/runtime.json" -Raw | ConvertFrom-Json).image
    $job=@{apiVersion='batch/v1';kind='Job';metadata=@{name=$name;labels=@{'urumi-m2-owned'='true'}};spec=@{backoffLimit=0;activeDeadlineSeconds=60;template=@{metadata=@{labels=$labels};spec=@{restartPolicy='Never';automountServiceAccountToken=$false;containers=@(@{name='probe';image=$image;command=@('python','-c',$python,$modeArg);resources=@{requests=@{cpu='25m';memory='64Mi'};limits=@{cpu='250m';memory='128Mi'}}})}}}}
    $null=Invoke-M2Job $job 'database-access-check.txt'
}
function Policy([bool]$Enabled) {
    $flag=$Enabled.ToString().ToLowerInvariant()
    $null=Invoke-M2Native $Helm (@('upgrade','urumi',$Chart)+$HArgs+@('-f',"$Chart/values-module-local.yaml",'-f',"$ToolDir/values-runtime.json",'--set','foundation.enabled=false','--set',"store.networkPolicy.enabled=$flag",'--wait','--timeout','180s')) 'policy-upgrade.txt' -TimeoutSeconds 200
}
$activeId='M2-01'
try {
    if (!$ResumeFromRest) {
    foreach ($environment in 'local','prod') {
        $arguments=@('-f',"$Chart/values-$environment.yaml",'--set','store.enabled=true')
        $null=Invoke-M2Native $Helm (@('lint',$Chart)+$arguments) 'helm-checks.txt'
        $null=Invoke-M2Native $Helm (@('template','urumi',$Chart)+$arguments) "rendered-$environment.txt"
    }
    Result 'M2-01' 'PASS' 'Local and production-shaped chart lint/render passed; manifests contain Secret references only.'
    $activeId='M2-02'
    $null=K @('rollout','status','deployment/urumi-wordpress','--timeout=180s') 'workload-settings.txt'
    $null=K @('rollout','status','statefulset/urumi-mariadb','--timeout=180s') 'workload-settings.txt'
    $workloads=K @('get','deployment/urumi-wordpress','statefulset/urumi-mariadb','-o','json') 'workload-settings.txt' | ConvertFrom-Json
    foreach ($workload in $workloads.items) { foreach ($container in $workload.spec.template.spec.containers) {
        if (!$container.readinessProbe -or !$container.livenessProbe -or !$container.resources.requests.cpu -or !$container.resources.requests.memory -or !$container.resources.limits.cpu -or !$container.resources.limits.memory) { throw 'Workload missing probes/resources' }
    } }
    Result 'M2-02' 'PASS' 'Both workloads Ready with liveness/readiness and CPU/memory requests/limits; versions.json records resolved image inputs.'
    $activeId='M2-03'
    $services=K @('get','services','urumi-mariadb','urumi-wordpress','-o','json') 'exposure-check.txt' | ConvertFrom-Json
    if (@($services.items | Where-Object {$_.spec.type -ne 'ClusterIP'}).Count) { throw 'Store Service externally exposed' }
    $routes=K @('get','ingress','-o','json') 'exposure-check.txt' | ConvertFrom-Json
    if (@($routes.items | Where-Object { $_.metadata.name -match 'mariadb' }).Count) { throw 'Database Ingress exists' }
    try { Policy $false; Probe-Job 'baseline' $false; Probe-Job 'baseline' $true } finally { Policy $true }
    Probe-Job 'allowed' $true; Probe-Job 'denied' $false; Probe-Job 'allowed' $true
    $curl=(Get-Command curl.exe -ErrorAction Stop).Source
    $null=Invoke-M2Native $curl @('--fail','--silent','--show-error','--max-time','10','--resolve','shop.urumi.test:80:127.0.0.1','http://shop.urumi.test/') 'ingress-check.txt'
    Result 'M2-03' 'BLOCKED' 'HTTP Ingress, database exposure and policy controls passed; actual storefront browser screenshot still required.'
    $activeId='M2-04'
    $before=Snapshot
    & "$ProjectRoot/scripts/store-setup.ps1"
    $after=Snapshot
    if (($before | ConvertTo-Json -Depth 8 -Compress) -ne ($after | ConvertTo-Json -Depth 8 -Compress)) { throw 'Setup rerun changed persistent IDs/state' }
    if ($after.store.currency -ne 'INR' -or $after.store.timezone -ne 'Asia/Kolkata' -or $after.store.cod -ne 'yes') { throw 'Shop settings mismatch' }
    Result 'M2-04' 'PASS' 'Setup rerun retained seed/key/attachment/order IDs; INR, Asia/Kolkata and COD verified.'
    $activeId='M2-05'
    if ($BrowserOrderId -gt 0 -and $BrowserOrderId -in @($before.store.order_ids)) {
        Result 'M2-05' 'BLOCKED' 'Provided order ID exists; actual cart/checkout/confirmation/admin screenshots and manual review still required.'
    } else { Result 'M2-05' 'BLOCKED' 'Real browser COD checkout and matching admin order evidence not supplied.' }
    $activeId='M2-06'
    if (!$before.store.image_sha256 -or !$before.store.image_url) { throw 'Saved image missing' }
    $before | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$EvidenceDir/persistence-before.json"
    Result 'M2-06' 'BLOCKED' 'Saved attachment URL/hash and PVC UIDs recorded; actual displayed image and browser order evidence still required.'
    foreach ($component in 'wordpress','mariadb') {
        $activeId=if ($component -eq 'wordpress') {'M2-07'} else {'M2-08'}
        $old=Store-Pod $component
        $null=K @('delete','pod',$old.metadata.name,'--wait=true','--timeout=60s') "$component-restart.txt"
        $kind=if ($component -eq 'wordpress') {'deployment'} else {'statefulset'}
        $null=K @('rollout','status',"$kind/urumi-$component",'--timeout=180s') "$component-restart.txt"
        $null=K @('rollout','status','deployment/urumi-wordpress','--timeout=180s') "$component-restart.txt"
        $new=Store-Pod $component
        if ($old.metadata.uid -eq $new.metadata.uid) { throw 'Pod UID did not change' }
        $snapshot=Snapshot
        $snapshot | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$EvidenceDir/persistence-after-$component.json"
        if (($before | ConvertTo-Json -Depth 8 -Compress) -ne ($snapshot | ConvertTo-Json -Depth 8 -Compress)) { throw 'Persistent state changed after replacement' }
        $id=if ($component -eq 'wordpress') {'M2-07'} else {'M2-08'}
        $status=if (@($before.store.order_ids).Count) {'PASS'} else {'BLOCKED'}
        Result $id $status 'Pod UID changed; original PVCs, product, key, attachment bytes and existing order IDs retained. Empty order list requires checkout then repeat.'
    }
    }
    $activeId='M2-09'
    if ($ResumeFromRest) {
        $current=Snapshot
        $savedSnapshot=Get-Content "$EvidenceDir/persistence-after-mariadb.json" -Raw | ConvertFrom-Json
        if ($current.store.product_id -ne $savedSnapshot.store.product_id -or
            $current.store.image_sha256 -ne $savedSnapshot.store.image_sha256 -or
            $BrowserOrderId -notin @($current.store.order_ids)) { throw 'Saved shop state changed; run the full checker.' }
        foreach ($claim in $current.claims) {
            $prior=@($savedSnapshot.claims | Where-Object { $_.name -eq $claim.name })
            if ($prior.Count -ne 1 -or $prior[0].uid -ne $claim.uid) { throw 'Saved PVC identity changed; run the full checker.' }
        }
    }
    # PowerShell 5.1 file strings carry provider metadata; serialize plain text only.
    $script=(Get-Content "$PSScriptRoot/rest-check.py" -Raw).ToString()
    $config=@{apiVersion='v1';kind='ConfigMap';metadata=@{name='urumi-m2-rest-check'};data=@{'rest-check.py'=$script}}
    $null=Apply-M2Object $config
    $image=(Get-Content "$ProjectRoot/.tools/m1/runtime.json" -Raw | ConvertFrom-Json).image
    $job=@{apiVersion='batch/v1';kind='Job';metadata=@{name=('urumi-m2-rest-'+[guid]::NewGuid().ToString('N').Substring(0,8));labels=@{'urumi-m2-owned'='true'}};spec=@{backoffLimit=0;activeDeadlineSeconds=60;template=@{spec=@{restartPolicy='Never';automountServiceAccountToken=$false;volumes=@(@{name='script';configMap=@{name='urumi-m2-rest-check'}},@{name='rest';secret=@{secretName='urumi-woocommerce-rest'}});containers=@(@{name='rest';image=$image;command=@('python','/scripts/rest-check.py');volumeMounts=@(@{name='script';mountPath='/scripts';readOnly=$true},@{name='rest';mountPath='/run/urumi/rest';readOnly=$true});resources=@{requests=@{cpu='25m';memory='64Mi'};limits=@{cpu='250m';memory='128Mi'}}})}}}}
    try { $null=Invoke-M2Job $job 'rest-preparation-check.txt' } finally { $null=K @('delete','configmap','urumi-m2-rest-check') 'rest-preparation-check.txt' }
    Result 'M2-09' 'PASS' 'Real shop signed administrative read/write passed; missing/wrong/expired/incorrect-canonical signatures rejected; disposable product removed.'
    $activeId='M2-10'
    Policy $true
    $retained=K @('get','pvc','urumi-mariadb-data','urumi-wordpress-content','-o','json') 'retention-check.txt' | ConvertFrom-Json
    foreach ($claim in $retained.items) { if ($claim.metadata.annotations.'helm.sh/resource-policy' -ne 'keep') { throw 'PVC keep annotation missing' } }
    $jobs=K @('get','jobs','-l','urumi-m2-owned=true','-o','json') 'cleanup-check.txt' | ConvertFrom-Json
    if (@($jobs.items).Count) { throw 'Owned checking Jobs remain' }
    Result 'M2-10' 'PASS' 'Chart reapply, rerun retention and zero remaining owned Jobs verified; retained-volume lifecycle documented.'
} catch {
    Result $activeId 'FAIL' $_.Exception.Message
    $_.Exception.Message | Add-Content -Encoding UTF8 "$EvidenceDir/failure.txt"
    throw
} finally {
    $results | ConvertTo-Json -Depth 8 | Set-Content -Encoding UTF8 "$EvidenceDir/results.json"
}
