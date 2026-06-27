# Fast Pose Studio DLC env install (avoids slow conda dependency solving).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/install_pose_env.ps1
#        powershell -ExecutionPolicy Bypass -File scripts/install_pose_env.ps1 -Recreate

param([switch]$Recreate)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_conda_common.ps1"

$Root = Get-ProjectRoot -ScriptsDir $PSScriptRoot
if (-not (Test-Path "$Root\requirements-pose.txt")) {
    Write-Error "requirements-pose.txt not found under $Root"
}

$EnvName = $script:PoseEnvName

if ($Recreate -and (Test-CondaEnvExists -EnvName $EnvName)) {
    Write-Host "==> Removing existing '$EnvName' env..."
    Invoke-Conda env remove -n $EnvName -y
}

if (-not (Test-CondaEnvExists -EnvName $EnvName)) {
    Write-Host "==> Creating minimal conda env '$EnvName' (python 3.10 + pip only)..."
    Invoke-Conda create -n $EnvName python=3.10 pip -y
} else {
    Write-Host "==> Env '$EnvName' already exists — refreshing pip packages..."
}

$Python = Get-CondaEnvPython -EnvName $EnvName
if (-not $Python) {
    Write-Error "Could not find python.exe for env '$EnvName' after create."
}

Write-Host "==> Installing PyTorch (CPU) + DeepLabCut via pip (may take several minutes)..."
& $Python -m pip install -r "$Root\requirements-pose.txt"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "==> Verifying..."
& $Python -c "import torch; import deeplabcut; print('torch', torch.__version__); print('deeplabcut', deeplabcut.__version__); print('cuda', torch.cuda.is_available())"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. DLC python:"
Write-Host "  $Python"
