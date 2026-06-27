# Pose Studio DLC environment

The main PyQt app stays lightweight. Training and prediction run in a **separate** conda env so torch/DLC never load inside the GUI process.

## Automated setup (Windows)

From the repo root, one command installs the main app env, the pose env, CUDA PyTorch when an NVIDIA GPU is present, and writes the DLC python path into app preferences:

```powershell
cd cv_zebrafish
powershell -ExecutionPolicy Bypass -File scripts/setup_desktop.ps1
```

| Flag | Effect |
|------|--------|
| `-Launch` | Start the app when setup finishes |
| `-Gpu` | Force CUDA PyTorch install (fails softly if no NVIDIA driver) |
| `-NoGpu` | Skip CUDA even on NVIDIA hardware (e.g. laptop CPU-only) |
| `-Recreate` | Remove and rebuild both conda envs |
| `-SkipMain` / `-SkipPose` | Only refresh one env |
| `-VerifyOnly` | Print env/GPU status without installing |

Launch without activating conda manually:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_app.ps1
```

## Why the first install looked frozen

`conda env create -f environment-pose.yml` with many scientific packages across **conda-forge + pytorch + defaults** can sit on **Solving environment** for a long time (or appear stuck). That is normal for mixed-channel solves.

**Use the fast path instead** (Python via conda, everything else via pip):

```powershell
cd cv_zebrafish
powershell -ExecutionPolicy Bypass -File scripts/install_pose_env.ps1
```

Typical timing:

| Step | Duration |
|------|----------|
| `conda create … python=3.10 pip` | ~30–60 s |
| `pip install` torch + deeplabcut | ~5–15 min (download size) |

## Wire into the app

`setup_desktop.ps1` sets this automatically in `data/local/ui_preferences.json`. Otherwise:

1. Open **Settings → Pose Studio (DLC)**.
2. Set **Python path** to:

   ```
   %USERPROFILE%\miniconda3\envs\cv-zebrafish-pose\python.exe
   ```

3. Train tab will call `scripts/run_dlc_step.py` with that interpreter instead of simulated mode.

## GPU (optional)

**Requires an NVIDIA GPU.** Intel or AMD integrated graphics cannot run CUDA PyTorch (the checkbox will stay disabled).

1. Install NVIDIA drivers and confirm `nvidia-smi` works in a terminal.
2. Install CUDA PyTorch into the pose env:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install_pose_env_gpu.ps1
```

Or manually:

```powershell
conda activate cv-zebrafish-pose
pip uninstall torch torchvision -y
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
python -c "import torch; print(torch.cuda.is_available())"
```

Must print `True` before enabling **Use GPU (NVIDIA CUDA)** on the Train tab.

Pick the CUDA build that matches your driver: https://pytorch.org/get-started/locally/

## Verify install

```powershell
%USERPROFILE%\miniconda3\envs\cv-zebrafish-pose\python.exe -c "import deeplabcut; print(deeplabcut.__version__)"
```

## Remove / recreate

```powershell
conda env remove -n cv-zebrafish-pose -y
powershell -ExecutionPolicy Bypass -File scripts/install_pose_env.ps1
```
