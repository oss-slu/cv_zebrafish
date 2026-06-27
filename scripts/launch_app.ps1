# Launch CV Zebrafish using the conda main app env (no manual activate needed).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/launch_app.ps1

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_conda_common.ps1"

$Root = Get-ProjectRoot -ScriptsDir $PSScriptRoot
$Python = Get-CondaEnvPython -EnvName $script:MainEnvName
if (-not $Python) {
    Write-Error @"
Main env '$($script:MainEnvName)' not found.
Run: powershell -ExecutionPolicy Bypass -File scripts/setup_desktop.ps1
"@
}

Push-Location $Root
try {
    & $Python app.py @args
} finally {
    Pop-Location
}
