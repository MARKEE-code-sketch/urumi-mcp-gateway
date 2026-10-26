$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$EvidenceDir = Join-Path $ProjectRoot 'docs/evidence/m2'
$ToolDir = Join-Path $ProjectRoot '.tools/m2'
$KubeConfig = Join-Path $ProjectRoot '.tools/m1/kubeconfig.yaml'
$Helm = Join-Path $ProjectRoot '.tools/m1/helm.exe'
$K3d = Join-Path $ProjectRoot '.tools/m1/k3d.exe'
$Kubectl = (Get-Command kubectl.exe -ErrorAction Stop).Source
$Chart = Join-Path $ProjectRoot 'deploy/charts/urumi'
$KArgs = @('--kubeconfig',$KubeConfig,'--context','k3d-urumi','--namespace','urumi')
$HArgs = @('--kubeconfig',$KubeConfig,'--kube-context','k3d-urumi','--namespace','urumi')
New-Item -ItemType Directory -Force $EvidenceDir,$ToolDir | Out-Null
function Invoke-M2Native {
    param([string]$File,[string[]]$Arguments,[string]$LogName,[string]$InputText,[int]$TimeoutSeconds=60,[switch]$Sensitive)
    $quoted = foreach ($arg in $Arguments) { '"' + (($arg -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"' }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$File; $start.Arguments=$quoted -join ' '; $start.WorkingDirectory=$ProjectRoot
    $start.UseShellExecute=$false; $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true; $start.RedirectStandardInput=$true
    $process=New-Object Diagnostics.Process; $process.StartInfo=$start; $null=$process.Start()
    $stdout=$process.StandardOutput.ReadToEndAsync(); $stderr=$process.StandardError.ReadToEndAsync()
    if ($null -ne $InputText) { $process.StandardInput.Write($InputText) }; $process.StandardInput.Close()
    if (!$process.WaitForExit($TimeoutSeconds*1000)) { $process.Kill(); throw 'M2 command timed out' }
    $out=$stdout.GetAwaiter().GetResult(); $err=$stderr.GetAwaiter().GetResult()
    if ($LogName -and !$Sensitive) { @("UTC: $([DateTime]::UtcNow.ToString('o'))", "Command: $File $($quoted -join ' ')","Exit: $($process.ExitCode)",$out,$err) | Add-Content -Encoding UTF8 (Join-Path $EvidenceDir $LogName) }
    if ($process.ExitCode -ne 0) { throw "M2 command failed ($($process.ExitCode)): $File. Inspect sanitized command log; secret-input output withheld." }
    if (!$Sensitive) { return $out }
}
function K([string[]]$Command,[string]$LogName='kubectl.txt') { Invoke-M2Native $Kubectl ($KArgs+$Command) $LogName }
function Assert-M2Cluster {
    if (!(Test-Path $KubeConfig)) { throw 'Existing M1 kubeconfig is missing; do not recreate cluster.' }
    $config=Invoke-M2Native $Kubectl @('--kubeconfig',$KubeConfig,'--context','k3d-urumi','config','view','--minify','-o','json') | ConvertFrom-Json
    if ($config.clusters[0].cluster.server -notmatch '^https://127\.0\.0\.1:') { throw 'Expected existing loopback project cluster.' }
    $null=K @('get','nodes') 'cluster-status.txt'
}
function Apply-M2Object($Object,[switch]$Sensitive) {
    $json=$Object | ConvertTo-Json -Depth 25 -Compress
    Invoke-M2Native $Kubectl ($KArgs+@('apply','-f','-')) 'apply.txt' $json -Sensitive:$Sensitive
}
function Get-M2Runtime {
    $p=Join-Path $ToolDir 'runtime.json'
    if (!(Test-Path $p)) { throw 'Run deploy-store.ps1 first; resolved runtime missing.' }
    Get-Content $p -Raw | ConvertFrom-Json
}
function Invoke-M2Job($Job,[string]$LogName='jobs.txt') {
    $name=$Job.metadata.name
    if ($name -notmatch '^urumi-m2-[a-z0-9-]+$') { throw 'Invalid owned Job name' }
    $null=Apply-M2Object $Job
    try {
        $deadline=(Get-Date).AddSeconds(330)
        do {
            $state=K @('get','job',$name,'-o','json') $LogName | ConvertFrom-Json
            if ($state.status.succeeded -ge 1) { return (K @('logs',"job/$name") $LogName) }
            if ($state.status.failed -ge 1) { $null=K @('logs',"job/$name") $LogName; throw "Owned Job failed: $name" }
            Start-Sleep -Seconds 2
        } while ((Get-Date) -lt $deadline)
        throw "Owned Job deadline exceeded: $name"
    } finally {
        $current=K @('get','job',$name,'-o','json') $LogName | ConvertFrom-Json
        if ($current.metadata.labels.'urumi-m2-owned' -eq 'true') { $null=K @('delete','job',$name,'--cascade=foreground','--wait=true','--timeout=30s') $LogName }
    }
}
