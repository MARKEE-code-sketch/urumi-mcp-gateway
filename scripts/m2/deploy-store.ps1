param([switch]$SkipBuild,[switch]$UsePulledImages)
. "$PSScriptRoot/common.ps1"
Assert-M2Cluster
$docker=(Get-Command docker.exe -ErrorAction Stop).Source
$null=Invoke-M2Native $docker @('info','--format','{{json .ServerVersion}}') 'docker-info.txt'
$resolved=@{}
foreach ($tag in @('wordpress:7.1.3-php8.3-apache','wordpress:cli-2.12.0-php8.3','mariadb:11.4.13-noble')) {
    if (!$UsePulledImages) { $null=Invoke-M2Native $docker @('pull',$tag) 'image-pull.txt' -TimeoutSeconds 300 }
    $digests=Invoke-M2Native $docker @('image','inspect',$tag,'--format','{{json .RepoDigests}}') 'image-digests.txt' | ConvertFrom-Json
    $reference=@($digests | Where-Object { $_ -match '@sha256:[a-f0-9]{64}$' })[0]
    if (!$reference) { throw 'Immutable image digest unavailable' }; $resolved[$tag]=$reference
}
if (!$SkipBuild) {
    $null=Invoke-M2Native $docker @('build','-f','build/store/Dockerfile','--build-arg',"WORDPRESS_IMAGE=$($resolved['wordpress:7.1.3-php8.3-apache'])",'--build-arg',"CLI_IMAGE=$($resolved['wordpress:cli-2.12.0-php8.3'])",'-t','urumi-store:m2','.') 'image-build.txt' -TimeoutSeconds 600
}
$imageId=(Invoke-M2Native $docker @('image','inspect','urumi-store:m2','--format','{{.Id}}') 'image-digests.txt').Trim()
foreach ($phpFile in 'bootstrap.php','live.php','ready.php','snapshot.php','verify-package.php') {
    $null=Invoke-M2Native $docker @('run','--rm','--entrypoint','php','urumi-store:m2','-l',"/opt/urumi-store/$phpFile") 'php-syntax.txt'
}
if ($imageId -notmatch '^sha256:[a-f0-9]{64}$') { throw 'Invalid built image ID' }
$imageTag='m2-'+$imageId.Substring(7,12)
$null=Invoke-M2Native $docker @('tag','urumi-store:m2',"urumi-store:$imageTag") 'image-build.txt'
$null=Invoke-M2Native $K3d @('image','import',"urumi-store:$imageTag",'--cluster','urumi') 'image-import.txt' -TimeoutSeconds 300
$runtime=@{storeImage="urumi-store:$imageTag";storeImageId=$imageId;databaseImage=$resolved['mariadb:11.4.13-noble'];inputs=$resolved}
$runtime | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "$ToolDir/runtime.json"
$runtime | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 "$EvidenceDir/versions.json"
# These are non-secret runtime overrides only.
@{store=@{enabled=$true;image=@{repository='urumi-store';tag=$imageTag;pullPolicy='IfNotPresent'};databaseImage=$runtime.databaseImage}} | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 "$ToolDir/values-runtime.json"
$values=@('-f',"$Chart/values-module-local.yaml",'-f',"$ToolDir/values-runtime.json",'--set','foundation.enabled=false')
foreach ($environment in 'local','prod') {
    $renderArgs=@('-f',"$Chart/values-$environment.yaml",'--set','store.enabled=true')
    $null=Invoke-M2Native $Helm (@('lint',$Chart)+$renderArgs) 'helm-checks.txt'
    $null=Invoke-M2Native $Helm (@('template','urumi',$Chart)+$renderArgs) "rendered-$environment.txt"
}
$releases=Invoke-M2Native $Helm (@('list','--all','--all-namespaces','-o','json')+$HArgs) 'existing-releases.txt' | ConvertFrom-Json
if (@($releases | Where-Object { $_.name -eq 'urumi' -and $_.namespace -ne 'urumi' }).Count) { throw 'Conflicting urumi release namespace' }
# Secret preparation precedes resources; setup returns if no WordPress Pod exists.
& "$ProjectRoot/scripts/store-setup.ps1"
$null=Invoke-M2Native $Helm (@('upgrade','--install','urumi',$Chart,'--create-namespace')+$HArgs+$values) 'store-install.txt' -TimeoutSeconds 120
$null=K @('rollout','status','statefulset/urumi-mariadb','--timeout=180s') 'workload-settings.txt'
$null=K @('wait','pod','-l','app.kubernetes.io/component=wordpress,app.kubernetes.io/instance=urumi','--for=jsonpath={.status.phase}=Running','--timeout=180s') 'workload-settings.txt'
& "$ProjectRoot/scripts/store-setup.ps1"
$null=K @('get','deployments,statefulsets,services,ingresses,pvc','-o','json') 'workload-settings.txt'
Write-Host 'M2 installed. Next run scripts/m2/check-store.ps1 and complete the browser checkout evidence.'
