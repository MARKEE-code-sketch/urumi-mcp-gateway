$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$EvidenceDir = Join-Path $ProjectRoot 'docs/evidence/m1'
$ToolDir = Join-Path $ProjectRoot '.tools/m1'
$Helm = Join-Path $ToolDir 'helm.exe'
$K3d = Join-Path $ToolDir 'k3d.exe'
$Kubectl = (Get-Command kubectl.exe -ErrorAction Stop).Source
$KubeConfig = Join-Path $ToolDir 'kubeconfig.yaml'
New-Item -ItemType Directory -Force $EvidenceDir,$ToolDir | Out-Null
function Invoke-Native {
    param([string]$File, [string[]]$Arguments, [string]$LogName, [int]$TimeoutSeconds = 360)
    # Windows argv quoting: embedded quotes and trailing backslashes.
    $quoted = foreach ($argument in $Arguments) {
        '"' + (($argument -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
    }
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $File
    $start.Arguments = $quoted -join ' '
    $start.WorkingDirectory = $ProjectRoot
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    $null = $process.Start()
    $stdout = $process.StandardOutput.ReadToEndAsync()
    $stderr = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { $process.Kill(); throw "Command timed out: $File" }
    $out = $stdout.GetAwaiter().GetResult()
    $err = $stderr.GetAwaiter().GetResult()
    if ($LogName) {
        @("UTC: $([DateTime]::UtcNow.ToString('o'))", "Command: $File $($quoted -join ' ')", "Exit: $($process.ExitCode)", $out, $err) |
            Add-Content -Encoding UTF8 (Join-Path $EvidenceDir $LogName)
    }
    if ($process.ExitCode -ne 0) { throw "Command failed ($($process.ExitCode)): $File $($Arguments -join ' ') $err $out" }
    if ($err) { Write-Verbose $err }
    return $out
}
function Assert-LocalCluster {
    if (-not (Test-Path -LiteralPath $KubeConfig)) { throw 'Run setup-cluster.ps1 first; project kubeconfig is missing.' }
    $config = Invoke-Native $Kubectl @('--kubeconfig',$KubeConfig,'config','view','--minify','--context','k3d-urumi','-o','json')
    $server = ($config | ConvertFrom-Json).clusters[0].cluster.server
    if ($server -notmatch '^https://127\.0\.0\.1:') { throw 'Expected a loopback-only project cluster API.' }
}
