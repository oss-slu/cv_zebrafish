"""Run Pose Studio DLC steps in an isolated subprocess."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.training.dlc_subprocess import (
    clear_stop_flag,
    iter_progress_lines,
    request_stop_after_epoch,
    run_dlc_script_path,
    stop_flag_path,
)


class PoseSubprocessWorker(QThread):
    """Launch ``scripts/run_dlc_step.py`` and stream JSON-line progress."""

    progress = pyqtSignal(dict)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        python_exe: str,
        job_path: Path,
        step: str = "pipeline",
        epochs: int = 50,
        use_gpu: bool = False,
        work_dir: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._python = python_exe or sys.executable
        self._job_path = Path(job_path)
        self._step = step
        self._epochs = epochs
        self._use_gpu = use_gpu
        self._work_dir = work_dir
        self._proc: subprocess.Popen | None = None
        self._stop_requested = False

    def request_stop_after_epoch(self) -> None:
        self._stop_requested = True
        if self._work_dir is not None:
            request_stop_after_epoch(self._work_dir)

    def run(self) -> None:
        script = run_dlc_script_path()
        if not script.is_file():
            self.failed.emit(f"DLC runner script not found: {script}")
            return
        if self._work_dir is not None:
            clear_stop_flag(self._work_dir)

        cmd = [
            self._python,
            str(script),
            "--job",
            str(self._job_path),
            "--step",
            self._step,
            "--epochs",
            str(self._epochs),
        ]
        if self._use_gpu:
            cmd.append("--gpu")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            assert self._proc.stdout is not None
            for obj in iter_progress_lines(self._proc.stdout):
                self.progress.emit(obj)
                if obj.get("type") == "error":
                    err_tail = ""
                    if self._proc.stderr is not None:
                        err_tail = self._proc.stderr.read() or ""
                    self.failed.emit(obj.get("message", "DLC subprocess error.") + err_tail)
                    self._terminate_proc()
                    return
            code = self._proc.wait()
            if code != 0:
                err = ""
                if self._proc.stderr is not None:
                    err = self._proc.stderr.read() or ""
                self.failed.emit(f"DLC subprocess exited with code {code}. {err}".strip())
                return
            self.finished_ok.emit(str(self._job_path.parent))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._proc = None

    def _terminate_proc(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass
