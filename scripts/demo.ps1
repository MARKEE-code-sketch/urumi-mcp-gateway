param(
    [ValidateSet('Guide','Inventory')][string]$Step = 'Guide',
    [string]$Context,
    [string]$Kubeconfig,
    [string]$Namespace,
    [string]$Release,
    [string]$Python = '.tools/m10/venv/Scripts/python.exe'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if ((Get-Location).Path -ne $repo) { throw 'Run from the repository root in PowerShell.' }
if ($Step -eq 'Guide') {
    Get-Content -LiteralPath 'docs/demo-checklist.md'
    return
}
if (!$Context -or !$Kubeconfig -or !$Namespace -or !$Release) {
    throw 'Inventory requires explicit Context, Kubeconfig, Namespace and Release.'
}
if (!(Test-Path -LiteralPath $Python)) { throw 'Prepare the pinned M10 Python environment first.' }
& $Python scripts/m10/check-m10.py --mode inventory --context $Context --kubeconfig $Kubeconfig --namespace $Namespace --release $Release --output docs/evidence/m10/runtime-inventory
if ($LASTEXITCODE -ne 0) { throw 'Read-only inventory failed; no live demo mutations were attempted.' }
