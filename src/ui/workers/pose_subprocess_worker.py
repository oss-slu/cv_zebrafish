"""Run Pose Studio DLC steps in an isolated subprocess."""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.training.dlc_subprocess import (
    clear_stop_flag,
    clear_subprocess_pid,
    iter_progress_lines,
    request_stop_after_epoch,
    run_dlc_script_path,
    stop_flag_path,
    write_subprocess_pid,
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
        skip_create_dataset: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._python = python_exe or sys.executable
        self._job_path = Path(job_path)
        self._step = step
        self._epochs = epochs
        self._use_gpu = use_gpu
        self._work_dir = work_dir
        self._skip_create_dataset = skip_create_dataset
        self._proc: subprocess.Popen | None = None
        self._stop_requested = False

    def request_stop_after_epoch(self) -> None:
        self._stop_requested = True
        if self._work_dir is not None:
            request_stop_after_epoch(self._work_dir)

    def terminate_process(self) -> None:
        """Force-stop the DLC subprocess (e.g. when the dialog closes)."""
        self._terminate_proc()

    def _stderr_log_text(self, stderr_target) -> str:
        if self._work_dir is not None:
            log_path = self._work_dir / "dlc_stderr.log"
            if log_path.is_file():
                return log_path.read_text(encoding="utf-8", errors="replace")
        if self._proc is not None and self._proc.stderr is not None:
            return self._proc.stderr.read() or ""
        return ""

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
        if self._skip_create_dataset and self._step == "train":
            cmd.append("--skip-create-dataset")

        stderr_target = None
        stderr_thread: threading.Thread | None = None
        try:
            if self._work_dir is not None:
                self._work_dir.mkdir(parents=True, exist_ok=True)
                stderr_target = open(
                    self._work_dir / "dlc_stderr.log",
                    "w",
                    encoding="utf-8",
                    errors="replace",
                )
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=stderr_target or subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            if self._work_dir is not None and self._proc.pid:
                write_subprocess_pid(self._work_dir, self._proc.pid)
            if stderr_target is None and self._proc.stderr is not None:

                def _drain_stderr() -> None:
                    assert self._proc is not None and self._proc.stderr is not None
                    try:
                        for _line in self._proc.stderr:
                            pass
                    except OSError:
                        pass

                stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
                stderr_thread.start()

            analyze_thread: threading.Thread | None = None
            analyze_stop = threading.Event()
            if self._step == "analyze" and self._work_dir is not None:
                analyze_thread = threading.Thread(
                    target=self._poll_analyze_stderr,
                    args=(self._work_dir / "dlc_stderr.log", analyze_stop),
                    daemon=True,
                )
                analyze_thread.start()
            assert self._proc.stdout is not None
            for obj in iter_progress_lines(self._proc.stdout):
                self.progress.emit(obj)
                if obj.get("type") == "error":
                    err_tail = self._stderr_log_text(stderr_target)
                    self.failed.emit(obj.get("message", "DLC subprocess error.") + err_tail)
                    self._terminate_proc()
                    return
            code = self._proc.wait()
            analyze_stop.set()
            if analyze_thread is not None:
                analyze_thread.join(timeout=2.0)
            if stderr_thread is not None:
                stderr_thread.join(timeout=2.0)
            if code != 0:
                err = self._stderr_log_text(stderr_target)
                self.failed.emit(f"DLC subprocess exited with code {code}. {err}".strip())
                return
            self.finished_ok.emit(str(self._job_path.parent))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if stderr_target is not None:
                stderr_target.close()
            if self._work_dir is not None:
                clear_subprocess_pid(self._work_dir)
            self._proc = None

    def _poll_analyze_stderr(self, log_path: Path, stop: threading.Event) -> None:
        import re

        pattern = re.compile(r"(\d+)\s*/\s*(\d+)")
        last_frame = 0
        pos = 0
        while not stop.is_set():
            if log_path.is_file():
                try:
                    with log_path.open(encoding="utf-8", errors="replace") as handle:
                        handle.seek(pos)
                        chunk = handle.read()
                        pos = handle.tell()
                except OSError:
                    chunk = ""
                for match in pattern.finditer(chunk):
                    cur = int(match.group(1))
                    tot = int(match.group(2))
                    if tot >= 50 and cur > last_frame:
                        last_frame = cur
                        self.progress.emit(
                            {
                                "type": "frame",
                                "frame": cur,
                                "total_frames": tot,
                                "phase": "analyze",
                            }
                        )
            time.sleep(0.4)

    def _terminate_proc(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except OSError:
                pass
