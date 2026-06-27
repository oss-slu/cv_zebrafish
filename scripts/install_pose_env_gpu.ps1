# Reinstall PyTorch with NVIDIA CUDA in an existing cv-zebrafish-pose env.
# Requires: NVIDIA GPU + up-to-date drivers (nvidia-smi must work).
# Usage: powershell -ExecutionPolicy Bypass -File scripts/install_pose_env_gpu.ps1
#        powershell -ExecutionPolicy Bypass -File scripts/install_pose_env_gpu.ps1 -NonInteractive

param([switch]$NonInteractive)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_conda_common.ps1"

$EnvName = $script:PoseEnvName
$Python = Get-CondaEnvPython -EnvName $EnvName
if (-not $Python) {
    Write-Error "Env '$EnvName' not found. Run scripts/install_pose_env.ps1 first."
}

$nvidiaSmi = Test-NvidiaGpu
if (-not $nvidiaSmi) {
    Write-Warning @"
nvidia-smi was not found. DeepLabCut GPU training needs an NVIDIA GPU and drivers.
Integrated graphics (Intel/AMD) cannot be used with CUDA PyTorch.
"@
    if (-not $NonInteractive) {
        $answer = Read-Host "Continue installing CUDA PyTorch anyway? (y/N)"
        if ($answer -notin @("y", "Y")) { exit 1 }
    }
}

Write-Host "==> Removing CPU-only torch..."
& $Python -m pip uninstall -y torch torchvision torchaudio 2>$null

Write-Host "==> Installing CUDA PyTorch (cu124 wheel)..."
& $Python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "==> Verifying CUDA..."
& $Python -c @"
import torch
print('torch', torch.__version__)
print('cuda_available', torch.cuda.is_available())
if torch.cuda.is_available():
    print('device', torch.cuda.get_device_name(0))
"@
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. In Pose Studio Train tab, enable 'Use GPU (NVIDIA CUDA)' after confirming cuda_available is True."
