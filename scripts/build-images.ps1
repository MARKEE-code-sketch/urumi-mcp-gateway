param(
    [Parameter(Mandatory=$true)][ValidateSet('Store','Woo','Inventory','Dashboard','Backend','All')][string]$Module,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9./:_-]*$')][string]$ImagePrefix,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$')][string]$Tag,
    [string]$PythonImage = '',
    [string]$WordPressImage = ''
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ((Get-Location).Path -ne $repo) { throw 'Run from the repository root in PowerShell.' }
$definitions = @{
    Store = @('build/store/Dockerfile', 'store')
    Woo = @('services/woocommerce_mcp/Dockerfile', 'woocommerce-mcp')
    Inventory = @('services/sample_mcps/Dockerfile', 'inventory-mcp')
    Dashboard = @('frontend/Dockerfile', 'dashboard')
    Backend = @('backend/Dockerfile', 'backend')
}
$selected = if ($Module -eq 'All') { @('Store','Woo','Inventory','Dashboard','Backend') } else { @($Module) }
# Validate the whole request before any build. All must not partially build then fail.
if ($selected -contains 'Backend') {
    if (!(Test-Path -LiteralPath 'backend/main.py') -or !(Test-Path -LiteralPath 'backend/orchestrator.py')) {
        throw 'M10_BACKEND_ENTRYPOINT_MISSING: combined backend build is unavailable; no harness substitution.'
    }
}
foreach ($item in $selected) {
    if (!(Test-Path -LiteralPath $definitions[$item][0])) { throw "BUILD_SOURCE_MISSING:$item" }
}
foreach ($item in $selected) {
    $arguments = @('build','--file',$definitions[$item][0],'--tag',"$ImagePrefix/$($definitions[$item][1]):$Tag")
    if ($item -eq 'Backend') { $arguments += @('--target','release') }
    if ($PythonImage -and $item -in @('Woo','Inventory','Backend')) { $arguments += @('--build-arg',"PYTHON_IMAGE=$PythonImage") }
    if ($WordPressImage -and $item -eq 'Store') { $arguments += @('--build-arg',"WORDPRESS_IMAGE=$WordPressImage") }
    $arguments += $(if ($item -eq 'Dashboard') { 'frontend' } else { '.' })
    & docker @arguments
    if ($LASTEXITCODE -ne 0) { throw "BUILD_FAILED:$item exit=$LASTEXITCODE" }
}
