"""Background worker: precompute blob overlays for smooth playback."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, detect_blob_square_crop
from core.pose.cache.playback_blob_cache import PlaybackBlobEntry
from core.pose.video.video_reader import downscale_frame
from core.pose.video.video_registry import _open_video_capture, _suppress_ffmpeg_stderr


class PlaybackBlobCacheWorker(QThread):
    """Scan the video once and cache compact blob geometry per frame."""

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        video_path: Path,
        frame_count: int,
        arena: ArenaConfig,
        blob_params: BlobParams,
        *,
        preview_max_edge: int,
        parent=None,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._frame_count = max(1, int(frame_count))
        self._arena = arena
        self._blob_params = blob_params
        self._preview_max_edge = int(preview_max_edge)
        self.entries: list[PlaybackBlobEntry] = []

    def run(self) -> None:
        try:
            with _suppress_ffmpeg_stderr():
                cap = _open_video_capture(self._video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video: {self._video_path}")
            self.entries = []
            try:
                idx = 0
                while idx < self._frame_count:
                    if self.isInterruptionRequested():
                        return
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    display = downscale_frame(frame, self._preview_max_edge)
                    blob = detect_blob_square_crop(
                        display, self._arena, self._blob_params
                    )
                    self.entries.append(PlaybackBlobEntry.from_blob(blob))
                    idx += 1
                    if idx == 1 or idx % 30 == 0 or idx == self._frame_count:
                        self.progress.emit(idx, self._frame_count)
            finally:
                cap.release()
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
