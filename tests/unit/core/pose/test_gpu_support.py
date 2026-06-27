"""Tests for DLC GPU probe helpers."""

from core.pose.training.gpu_support import PoseGpuStatus


def test_pose_gpu_status_summary_cpu_wheel():
    status = PoseGpuStatus(cuda_available=False, torch_version="2.12.1+cpu")
    assert "CPU-only" in status.summary


def test_pose_gpu_status_summary_ready():
    status = PoseGpuStatus(
        cuda_available=True,
        torch_version="2.12.1+cu124",
        device_name="NVIDIA GeForce RTX 3060",
    )
    assert "GPU ready" in status.summary
    assert "RTX 3060" in status.summary
