"""Background worker: precompute blob overlays for smooth playback."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import (
    BlobDetectionContext,
    BlobParams,
    detect_blob_square_crop_ctx,
)
from core.pose.cache.playback_blob_cache import (
    PlaybackBlobEntry,
    PlaybackCacheBuffers,
    save_playback_overlay_buffers,
)
from core.pose.preview.preview_blob import preview_dimensions, scale_blob_result
from core.pose.video.video_registry import _open_video_capture, _suppress_ffmpeg_stderr


class PlaybackBlobCacheWorker(QThread):
    """Scan the video once and cache compact blob geometry per frame."""

    progress = pyqtSignal(str, int, int)
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
        save_dir: Path | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._video_path = video_path
        self._frame_count = max(1, int(frame_count))
        self._arena = arena
        self._blob_params = blob_params
        self._preview_max_edge = int(preview_max_edge)
        self._save_dir = save_dir
        self.buffers: PlaybackCacheBuffers | None = None
        self.entries: list[PlaybackBlobEntry] = []

    def run(self) -> None:
        try:
            with _suppress_ffmpeg_stderr():
                cap = _open_video_capture(self._video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video: {self._video_path}")
            detection_ctx: BlobDetectionContext | None = None
            preview_h = preview_w = 0
            preview_scale = 1.0
            self.buffers = None
            try:
                idx = 0
                while idx < self._frame_count:
                    if self.isInterruptionRequested():
                        return
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        break
                    frame_h, frame_w = frame.shape[:2]
                    if detection_ctx is None:
                        detection_ctx = BlobDetectionContext.for_frame(
                            frame_h,
                            frame_w,
                            self._arena,
                            self._blob_params,
                        )
                        preview_h, preview_w, preview_scale = preview_dimensions(
                            frame_h, frame_w, self._preview_max_edge
                        )
                        self.buffers = PlaybackCacheBuffers.allocate(
                            self._frame_count, preview_h, preview_w
                        )

                    full_blob = detect_blob_square_crop_ctx(
                        frame, self._blob_params, detection_ctx
                    )
                    if preview_scale != 1.0:
                        blob = scale_blob_result(
                            full_blob, preview_scale, preview_h, preview_w
                        )
                    else:
                        blob = full_blob
                    assert self.buffers is not None
                    self.buffers.write_blob(idx, blob)
                    idx += 1
                    if idx == 1 or idx % 30 == 0 or idx == self._frame_count:
                        self.progress.emit("scan", idx, self._frame_count)
            finally:
                cap.release()

            if self.buffers is not None and self._save_dir is not None:
                self.progress.emit("save", 0, 0)
                save_playback_overlay_buffers(
                    self._save_dir,
                    self.buffers,
                    frame_count=self._frame_count,
                    video_path=self._video_path,
                    arena=self._arena,
                    blob_params=self._blob_params,
                    preview_max_edge=self._preview_max_edge,
                )

            if self.buffers is not None:
                self.entries = self.buffers.to_entries()
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
