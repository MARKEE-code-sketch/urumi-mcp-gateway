param([switch]$ExistingCluster)
. "$PSScriptRoot/common.ps1"
$result = [ordered]@{timestamp=[DateTime]::UtcNow.ToString('o');status='BLOCKED';docker=$null;kubectl=$null;memory=$null;port=$null;error=$null}
try {
    $dockerCommand = (Get-Command docker.exe).Source
    $docker = Invoke-Native $dockerCommand @('info','--format','{"ServerVersion":"{{.ServerVersion}}","NCPU":{{.NCPU}},"MemTotal":{{.MemTotal}},"OSType":"{{.OSType}}"}') -TimeoutSeconds 20 | ConvertFrom-Json
    $result.docker = @{serverVersion=$docker.ServerVersion;cpus=$docker.NCPU;memoryBytes=$docker.MemTotal;os=$docker.OSType}
    $result.docker | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'docker-info.txt')
    if ($docker.OSType -ne 'linux') { throw 'Docker Desktop must use Linux containers.' }
    $result.kubectl = (Invoke-Native $Kubectl @('version','--client','-o','json') 'kubectl-version.txt' 20 | ConvertFrom-Json).clientVersion.gitVersion
    if ($ExistingCluster) {
        $runtimePath = Join-Path $ToolDir 'runtime.json'
        if (Test-Path $runtimePath) {
            $result.port = (Get-Content $runtimePath -Raw | ConvertFrom-Json).port
        } else {
            $resolved = Get-Content (Join-Path $ToolDir 'k3d-resolved.yaml') -Raw
            if ($resolved -notmatch '127\.0\.0\.1:(80|8080):80') { throw 'Saved cluster web mapping is missing.' }
            $result.port = [int]$Matches[1]
        }
        if ($result.port -notin 80,8080) { throw 'Invalid saved local web port.' }
    } else {
    foreach ($port in 80,8080) {
        $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback,$port)
        try { $listener.Start(); $result.port=$port; break } catch { } finally { $listener.Stop() }
    }
    if (-not $result.port) { throw 'Neither loopback port 80 nor 8080 can be bound. No existing application was stopped.' }
    }
    $result.memory = 'Docker allocation recorded; full stack capacity needs later measurements.'
    $result.status = 'PASS'
} catch { $result.error=$_.Exception.Message }
$result | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'preflight.json')
$result | ConvertTo-Json -Depth 6
if ($result.status -ne 'PASS') { throw $result.error }
