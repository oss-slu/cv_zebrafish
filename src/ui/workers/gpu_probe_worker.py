"""Probe DLC CUDA availability without blocking the UI thread."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.training.gpu_support import PoseGpuStatus, probe_pose_gpu


class GpuProbeWorker(QThread):
    finished_ok = pyqtSignal(object)

    def __init__(self, python_exe: str, parent=None):
        super().__init__(parent)
        self._python_exe = python_exe

    def run(self) -> None:
        status: PoseGpuStatus = probe_pose_gpu(self._python_exe)
        self.finished_ok.emit(status)
