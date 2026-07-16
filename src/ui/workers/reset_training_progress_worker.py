"""Background reset of DLC training checkpoints (stop subprocess + delete trees)."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.training.dlc_subprocess import reset_training_progress


class ResetTrainingProgressWorker(QThread):
    finished_ok = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, work_dir: Path, parent=None):
        super().__init__(parent)
        self._work_dir = Path(work_dir)

    def run(self) -> None:
        try:
            cleared = reset_training_progress(self._work_dir)
        except OSError as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(cleared)
