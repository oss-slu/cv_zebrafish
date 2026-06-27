"""Background worker: migrate legacy playback files to H.264 MP4."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.video.video_transcode import migrate_legacy_playback


class PlaybackMigrateWorker(QThread):
    progress = pyqtSignal(str, int, int)
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, video_dir: Path, parent=None):
        super().__init__(parent)
        self._video_dir = video_dir

    def run(self) -> None:
        try:
            path = migrate_legacy_playback(
                self._video_dir,
                progress=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
            )
            if path is None:
                raise ValueError("No video file found to prepare for playback.")
            self.finished_ok.emit(str(path))
        except Exception as exc:
            self.failed.emit(str(exc))
