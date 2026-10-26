. "$PSScriptRoot/common.ps1"
$ProgressPreference = 'SilentlyContinue'
$k3dVersion = 'v5.9.0'
$helmVersion = 'v3.21.3'
$downloads = Join-Path $ToolDir 'downloads'
New-Item -ItemType Directory -Force $downloads | Out-Null
function Get-Download([string]$Url, [string]$Path) {
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path -TimeoutSec 60
}
function Confirm-Hash([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $Expected.ToLowerInvariant()) { throw "SHA256 mismatch: $Path" }
    return $actual
}
$k3dAsset = 'k3d-windows-amd64.exe'
$k3dDownload = Join-Path $downloads $k3dAsset
$k3dSums = Join-Path $downloads 'k3d-checksums.txt'
Get-Download "https://github.com/k3d-io/k3d/releases/download/$k3dVersion/checksums.txt" $k3dSums
Get-Download "https://github.com/k3d-io/k3d/releases/download/$k3dVersion/$k3dAsset" $k3dDownload
$line = @(Get-Content -LiteralPath $k3dSums | Where-Object { $_ -match "\s+\*?(?:_dist/)?$([regex]::Escape($k3dAsset))$" })
if ($line.Count -ne 1) { throw 'Cannot identify exact k3d checksum entry.' }
$k3dHash = Confirm-Hash $k3dDownload (($line[0] -split '\s+')[0])
Copy-Item -LiteralPath $k3dDownload -Destination $K3d -Force
$helmAsset = "helm-$helmVersion-windows-amd64.zip"
$helmDownload = Join-Path $downloads $helmAsset
$helmSum = Join-Path $downloads 'helm.sha256'
Get-Download "https://get.helm.sh/$helmAsset.sha256sum" $helmSum
Get-Download "https://get.helm.sh/$helmAsset" $helmDownload
$helmHash = Confirm-Hash $helmDownload (((Get-Content -LiteralPath $helmSum -Raw).Trim() -split '\s+')[0])
$extract = Join-Path $downloads 'helm-extracted'
Expand-Archive -LiteralPath $helmDownload -DestinationPath $extract -Force
Copy-Item -LiteralPath (Join-Path $extract 'windows-amd64/helm.exe') -Destination $Helm -Force
$k3dOutput = Invoke-Native $K3d @('version') 'k3d-version.txt'
$helmOutput = Invoke-Native $Helm @('version','--short') 'helm-version.txt'
if ($k3dOutput -notmatch [regex]::Escape($k3dVersion)) { throw 'Unexpected k3d version.' }
if ($helmOutput -notmatch [regex]::Escape($helmVersion)) { throw 'Unexpected Helm version.' }
@{k3d=@{version=$k3dVersion;sha256=$k3dHash};helm=@{version=$helmVersion;sha256=$helmHash}} |
    ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'tool-install.json')
Write-Host 'Verified portable k3d and Helm are ready in .tools/m1.'
