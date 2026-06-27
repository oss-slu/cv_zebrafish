"""Probe CUDA availability in the Pose Studio DLC Python environment."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class PoseGpuStatus:
    cuda_available: bool
    torch_version: str = ""
    device_count: int = 0
    device_name: str = ""
    error: str = ""

    @property
    def summary(self) -> str:
        if self.error:
            return f"Could not probe GPU ({self.error})"
        if self.cuda_available:
            name = self.device_name or "CUDA device"
            return f"GPU ready: {name} (PyTorch {self.torch_version})"
        if self.torch_version.endswith("+cpu"):
            return (
                f"CPU-only PyTorch ({self.torch_version}). "
                "Install CUDA PyTorch in cv-zebrafish-pose (see docs/POSE_DLC_ENV.md)."
            )
        return (
            f"No NVIDIA CUDA GPU detected (PyTorch {self.torch_version or 'unknown'}). "
            "Training will use CPU."
        )


_PROBE_CODE = """
import json
try:
    import torch
    info = {
        "cuda_available": bool(torch.cuda.is_available()),
        "torch_version": torch.__version__,
        "device_count": int(torch.cuda.device_count()),
        "device_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
    }
except Exception as exc:
    info = {"cuda_available": False, "error": str(exc)}
print(json.dumps(info))
"""


def probe_pose_gpu(python_exe: str, *, timeout_s: float = 45.0) -> PoseGpuStatus:
    """Run a short subprocess in the DLC env to detect CUDA without loading torch in the GUI."""
    if not python_exe:
        return PoseGpuStatus(cuda_available=False, error="no python path")
    try:
        proc = subprocess.run(
            [python_exe, "-c", _PROBE_CODE],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PoseGpuStatus(cuda_available=False, error=str(exc))

    lines = (proc.stdout or "").strip().splitlines()
    if not lines:
        err = (proc.stderr or "").strip() or f"exit {proc.returncode}"
        return PoseGpuStatus(cuda_available=False, error=err)
    try:
        data = json.loads(lines[-1])
    except json.JSONDecodeError:
        return PoseGpuStatus(cuda_available=False, error="invalid probe output")

    if data.get("error"):
        return PoseGpuStatus(cuda_available=False, error=str(data["error"]))
    return PoseGpuStatus(
        cuda_available=bool(data.get("cuda_available")),
        torch_version=str(data.get("torch_version", "")),
        device_count=int(data.get("device_count", 0) or 0),
        device_name=str(data.get("device_name", "")),
    )
