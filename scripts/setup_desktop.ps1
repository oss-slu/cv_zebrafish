# One-shot Windows setup: main app env + Pose Studio DLC env + optional NVIDIA GPU.
#
# Usage (from cv_zebrafish repo root or anywhere):
#   powershell -ExecutionPolicy Bypass -File scripts/setup_desktop.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/setup_desktop.ps1 -Gpu
#   powershell -ExecutionPolicy Bypass -File scripts/setup_desktop.ps1 -Launch
#   powershell -ExecutionPolicy Bypass -File scripts/setup_desktop.ps1 -VerifyOnly
#
# Prereqs: Miniconda/Anaconda, NVIDIA drivers (for -Gpu / auto GPU on RTX machines).

[CmdletBinding()]
param(
    [switch]$Gpu,
    [switch]$NoGpu,
    [switch]$SkipMain,
    [switch]$SkipPose,
    [switch]$Recreate,
    [switch]$Launch,
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\_conda_common.ps1"

$Root = Get-ProjectRoot -ScriptsDir $PSScriptRoot
if (-not (Test-Path (Join-Path $Root "environment.yml"))) {
    Write-Error "environment.yml not found under $Root - run this from the cv_zebrafish repo."
}

function Test-PoseCuda {
    param([string]$PythonExe)
    if (-not $PythonExe) { return $false }
    $out = & $PythonExe -c 'import torch; print(1 if torch.cuda.is_available() else 0)' 2>$null
    return ($out -match '1')
}

function Show-VerifyReport {
    $mainPy = Get-CondaEnvPython -EnvName $script:MainEnvName
    $posePy = Get-CondaEnvPython -EnvName $script:PoseEnvName
    $nvidia = Test-NvidiaGpu
    $cuda = Test-PoseCuda -PythonExe $posePy

    Write-Host "=== CV Zebrafish environment check ==="
    Write-Host "  Project:     $Root"
    Write-Host "  Conda:       $(if (Get-CondaExe) { 'found' } else { 'MISSING' })"
    Write-Host "  Main env:    $(if ($mainPy) { $mainPy } else { 'not installed' })"
    Write-Host "  Pose env:    $(if ($posePy) { $posePy } else { 'not installed' })"
    Write-Host "  nvidia-smi:  $(if ($nvidia) { 'found' } else { 'not found' })"
    Write-Host "  CUDA (pose): $(if ($cuda) { 'ready' } else { 'not available' })"
    if ($posePy) {
        & $posePy -c "import deeplabcut; print('DLC version', deeplabcut.__version__)" 2>$null
    }
    $pref = Join-Path $Root "data\local\ui_preferences.json"
    if (Test-Path $pref) {
        try {
            $p = Get-Content $pref -Raw | ConvertFrom-Json
            Write-Host "  DLC pref:    $($p.dlc_python_path)"
        } catch { }
    }
    return [pscustomobject]@{
        MainOk = [bool]$mainPy
        PoseOk = [bool]$posePy
        CudaOk = $cuda
    }
}

if ($VerifyOnly) {
    Show-VerifyReport | Out-Null
    exit 0
}

$wantGpu = $false
if ($NoGpu) {
    $wantGpu = $false
} elseif ($Gpu) {
    $wantGpu = $true
} else {
    $wantGpu = Test-NvidiaGpu
    if ($wantGpu) {
        Write-Host "NVIDIA GPU detected - will install CUDA PyTorch for Pose Studio."
    } else {
        Write-Host "No NVIDIA GPU detected - Pose env will use CPU PyTorch."
    }
}

# --- Main app env ---
if (-not $SkipMain) {
    if ($Recreate -and (Test-CondaEnvExists -EnvName $script:MainEnvName)) {
        Write-Host "==> Removing existing '$($script:MainEnvName)' env..."
        Invoke-Conda env remove -n $script:MainEnvName -y
    }
    if (-not (Test-CondaEnvExists -EnvName $script:MainEnvName)) {
        Write-Host "==> Creating main app env '$($script:MainEnvName)' from environment.yml..."
        Push-Location $Root
        try {
            Invoke-Conda env create -f environment.yml
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "==> Main app env '$($script:MainEnvName)' already exists (use -Recreate to rebuild)."
    }
} else {
    Write-Host "==> Skipping main app env (-SkipMain)."
}

# --- Pose / DLC env ---
if (-not $SkipPose) {
    $poseArgs = @()
    if ($Recreate) { $poseArgs += "-Recreate" }
    & "$PSScriptRoot\install_pose_env.ps1" @poseArgs
} else {
    Write-Host "==> Skipping pose env (-SkipPose)."
}

# --- GPU PyTorch ---
if ($wantGpu) {
    if (-not (Test-NvidiaGpu)) {
        Write-Warning "GPU install requested but nvidia-smi not found. Install NVIDIA drivers first."
    } else {
        & "$PSScriptRoot\install_pose_env_gpu.ps1" -NonInteractive
    }
} else {
    Write-Host "==> Skipping CUDA PyTorch install."
}

$mainPython = Get-CondaEnvPython -EnvName $script:MainEnvName
$posePython = Get-CondaEnvPython -EnvName $script:PoseEnvName
if (-not $mainPython) { Write-Error "Main env python not found after setup." }
if (-not $posePython) { Write-Error "Pose env python not found after setup." }

Write-Host ""
Write-Host "==> Wiring DLC python into app preferences..."
Update-UiPreferencesDlcPath -DlcPython $posePython -ProjectRoot $Root

Write-Host ""
Write-Host "==> Quick import check (main app)..."
& $mainPython -c "import PyQt5; import cv2; print('main app imports OK')"

$cudaOk = Test-PoseCuda -PythonExe $posePython
Write-SetupSummary -ProjectRoot $Root -MainPython $mainPython -PosePython $posePython -CudaAvailable $cudaOk

if ($Launch) {
    Write-Host ""
    Write-Host "==> Launching app..."
    & $mainPython (Join-Path $Root "app.py")
}
