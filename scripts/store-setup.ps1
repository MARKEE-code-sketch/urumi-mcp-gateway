$ErrorActionPreference='Stop'
. "$PSScriptRoot/m2/common.ps1"
Assert-M2Cluster
$runtime=Get-M2Runtime
function Random-Hex([int]$Count=32) {
    $bytes=New-Object byte[] $Count; $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    -join ($bytes | ForEach-Object { $_.ToString('x2') })
}
function Ensure-Secret([string]$Name,$Data) {
    $present=K @('get','secret',$Name,'--ignore-not-found=true','-o','name') 'secret-metadata.txt'
    if ($present.Trim()) {
        # JSONPath emits key names only; no credential bytes enter logs.
        $keys=K @('get','secret',$Name,'-o','go-template={{range $k,$v := .data}}{{$k}}{{"\n"}}{{end}}') 'secret-metadata.txt'
        foreach ($key in $Data.Keys) { if ($key -notin @($keys -split '\s+')) { throw "Required key missing in Secret $Name; reconcile manually." } }
        return
    }
    $object=@{apiVersion='v1';kind='Secret';metadata=@{name=$Name;namespace='urumi';labels=@{'urumi-m2-owned'='true'}};type='Opaque';stringData=$Data}
    $null=Apply-M2Object $object -Sensitive
}
# If the database already exists, missing REST Secret cannot silently replace its identity.
$existing=K @('get','secret','urumi-woocommerce-rest','--ignore-not-found=true','-o','name') 'secret-metadata.txt'
$storePods=K @('get','pods','-l','app.kubernetes.io/component=wordpress,app.kubernetes.io/instance=urumi','-o','json') 'setup-status.txt' | ConvertFrom-Json
if (!$existing.Trim() -and @($storePods.items).Count) {
    $pod=$storePods.items[0].metadata.name
    $state=K @('exec',$pod,'--','php','-r','if(file_exists("/var/www/html/wp-config.php")){echo "initialized-files";}') 'setup-status.txt'
    if ($state -match 'initialized-files') { throw 'REST Secret absent on an existing website; reconcile manually instead of replacing credentials.' }
}
Ensure-Secret 'urumi-store-db' @{'root-password'=(Random-Hex);'database-password'=(Random-Hex)}
Ensure-Secret 'urumi-store-admin' @{username='urumi-admin';password=(Random-Hex);email='admin@example.invalid'}
$salts=@{}; foreach ($key in 'AUTH_KEY','SECURE_AUTH_KEY','LOGGED_IN_KEY','NONCE_KEY','AUTH_SALT','SECURE_AUTH_SALT','LOGGED_IN_SALT','NONCE_SALT') { $salts[$key]=Random-Hex }
Ensure-Secret 'urumi-store-salts' $salts
Ensure-Secret 'urumi-woocommerce-rest' @{'consumer-key'=('ck_'+(Random-Hex 20));'consumer-secret'=('cs_'+(Random-Hex 20))}
if (!$storePods.items.Count) { Write-Host 'Secrets prepared. Deploy resources, then rerun setup to configure the website.'; return }
$null=K @('rollout','status','statefulset/urumi-mariadb','--timeout=180s') 'setup-status.txt'
$volumes=@(@{name='content';persistentVolumeClaim=@{claimName='urumi-wordpress-content'}})
$mounts=@(@{name='content';mountPath='/var/www/html'})
$volumes+=@{name='store-theme';configMap=@{name='urumi-store-theme'}}
$mounts+=@{name='store-theme';mountPath='/var/www/html/wp-content/themes/urumi-shop';readOnly=$true}
foreach ($group in 'database','admin','salts','rest') {
    $secretName=@{database='urumi-store-db';admin='urumi-store-admin';salts='urumi-store-salts';rest='urumi-woocommerce-rest'}[$group]
    $volume=@{name=$group;secret=@{secretName=$secretName}}
    if ($group -eq 'database') { $volume.secret.items=@(@{key='database-password';path='database-password'}) }
    $volumes+=$volume; $mounts+=@{name=$group;mountPath="/run/urumi/$group";readOnly=$true}
}
$envs=@(@{name='WORDPRESS_DB_PASSWORD_FILE';value='/run/urumi/database/database-password'})
foreach ($key in $salts.Keys) { $envs+=@{name="WORDPRESS_${key}_FILE";value="/run/urumi/salts/$key"} }
$job=@{apiVersion='batch/v1';kind='Job';metadata=@{name=('urumi-m2-setup-'+[guid]::NewGuid().ToString('N').Substring(0,8));labels=@{'urumi-m2-owned'='true'}};spec=@{backoffLimit=0;activeDeadlineSeconds=300;template=@{metadata=@{labels=@{'app.kubernetes.io/instance'='urumi';'urumi-m2-access'='setup'}};spec=@{automountServiceAccountToken=$false;restartPolicy='Never';securityContext=@{runAsUser=33;runAsGroup=33;fsGroup=33};volumes=$volumes;containers=@(@{name='setup';image=$runtime.storeImage;imagePullPolicy='IfNotPresent';workingDir='/var/www/html';envFrom=@(@{configMapRef=@{name='urumi-store'}});env=$envs;volumeMounts=$mounts;resources=@{requests=@{cpu='100m';memory='128Mi'};limits=@{cpu='500m';memory='512Mi'}};command=@('bash','-c','set -e; for n in $(seq 1 60); do test -f wp-config.php && break; sleep 2; done; wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress; wp eval-file /opt/urumi-store/bootstrap.php --skip-wordpress; wp theme activate urumi-shop')})}}}}
$null=Invoke-M2Job $job 'setup-check.txt'
$null=K @('rollout','status','deployment/urumi-wordpress','--timeout=180s') 'setup-status.txt'
Write-Host 'Store configuration complete. Credentials were not printed. Open http://shop.urumi.test.'
