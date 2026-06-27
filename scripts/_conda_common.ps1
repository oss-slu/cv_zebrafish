# Shared helpers for cv_zebrafish conda install scripts (dot-source only).

$script:MainEnvName = "cv-zebrafish"
$script:PoseEnvName = "cv-zebrafish-pose"

function Get-ProjectRoot {
    param([string]$ScriptsDir = $PSScriptRoot)
    return (Resolve-Path (Join-Path $ScriptsDir "..")).Path
}

function Get-CondaExe {
    $candidates = @(
        "$env:USERPROFILE\miniconda3\Scripts\conda.exe"
        "$env:USERPROFILE\AppData\Local\miniconda3\Scripts\conda.exe"
        "$env:USERPROFILE\anaconda3\Scripts\conda.exe"
        "$env:USERPROFILE\AppData\Local\anaconda3\Scripts\conda.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

function Get-CondaEnvPython {
    param([string]$EnvName)
    $rel = "envs\$EnvName\python.exe"
    $roots = @(
        "$env:USERPROFILE\miniconda3"
        "$env:USERPROFILE\AppData\Local\miniconda3"
        "$env:USERPROFILE\anaconda3"
        "$env:USERPROFILE\AppData\Local\anaconda3"
    )
    foreach ($root in $roots) {
        $candidate = Join-Path $root $rel
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

function Test-CondaEnvExists {
    param([string]$EnvName)
    return [bool](Get-CondaEnvPython -EnvName $EnvName)
}

function Invoke-Conda {
    param([string[]]$CondaArgs)
    $conda = Get-CondaExe
    if (-not $conda) {
        throw "Miniconda/Anaconda not found. Install from https://docs.conda.io/en/latest/miniconda.html"
    }
    & $conda @CondaArgs
    if ($LASTEXITCODE -ne 0) {
        throw "conda $($CondaArgs -join ' ') failed (exit $LASTEXITCODE)"
    }
}

function Test-NvidiaGpu {
    return [bool](Get-Command nvidia-smi -ErrorAction SilentlyContinue)
}

function Update-UiPreferencesDlcPath {
    param(
        [string]$DlcPython,
        [string]$ProjectRoot
    )
    $prefDir = Join-Path $ProjectRoot "data\local"
    $prefPath = Join-Path $prefDir "ui_preferences.json"
    New-Item -ItemType Directory -Force -Path $prefDir | Out-Null

    $prefs = @{}
    if (Test-Path $prefPath) {
        try {
            $raw = Get-Content $prefPath -Raw -Encoding UTF8 | ConvertFrom-Json
            $raw.PSObject.Properties | ForEach-Object { $prefs[$_.Name] = $_.Value }
        } catch {
            Write-Warning "Could not parse $prefPath - writing fresh DLC path only."
        }
    }
    $prefs["dlc_python_path"] = $DlcPython
    ($prefs | ConvertTo-Json -Depth 10) | Set-Content -Path $prefPath -Encoding UTF8
    Write-Host "  Wrote DLC python path to data\local\ui_preferences.json"
}

function Write-SetupSummary {
    param(
        [string]$ProjectRoot,
        [string]$MainPython,
        [string]$PosePython,
        [bool]$CudaAvailable
    )
    Write-Host ""
    Write-Host "=== Setup summary ==="
    Write-Host "  Main app:  $MainPython"
    Write-Host "  Pose DLC:  $PosePython"
    if ($CudaAvailable) {
        Write-Host "  GPU:       CUDA available - enable Use GPU on the Train tab"
    } else {
        Write-Host "  GPU:       CPU only (run install_pose_env_gpu.ps1 on an NVIDIA machine)"
    }
    Write-Host ""
    Write-Host "Launch:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File scripts\launch_app.ps1"
    Write-Host "Or:"
    Write-Host "  conda activate $script:MainEnvName"
    Write-Host "  python app.py"
}
