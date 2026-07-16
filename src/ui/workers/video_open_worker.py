"""Background worker: warm OpenCV video open so the UI thread stays responsive."""

from __future__ import annotations

from pathlib import Path

import cv2
from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.video.video_registry import _open_video_capture, _suppress_ffmpeg_stderr, resolve_video_source


class VideoOpenWorker(QThread):
    """Probe-open the video on a worker thread (filesystem / codec warm-up)."""

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, video_dir: Path, parent=None):
        super().__init__(parent)
        self._video_dir = Path(video_dir)

    def run(self) -> None:
        try:
            src = resolve_video_source(self._video_dir)
            if src is None:
                raise ValueError(f"No video file found in {self._video_dir}")
            with _suppress_ffmpeg_stderr():
                old_log = cv2.getLogLevel()
                cv2.setLogLevel(0)
                try:
                    cap = _open_video_capture(src)
                    if not cap.isOpened():
                        raise ValueError(f"Could not open video:\n{src}")
                    cap.release()
                finally:
                    cv2.setLogLevel(old_log)
            self.finished_ok.emit(str(self._video_dir))
        except Exception as exc:
            self.failed.emit(str(exc))
