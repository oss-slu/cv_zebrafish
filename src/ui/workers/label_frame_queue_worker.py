"""Background scan for pose-diversity frame queue."""

from __future__ import annotations

from pathlib import Path

import cv2
from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams
from core.pose.labeling.frame_sampler import (
    build_diverse_label_frame_queue,
    gap_from_frames_to_analyze,
    scan_shape_fingerprints_adaptive_sequential,
)
from core.pose.labeling.pose_scan_cache import load_pose_scan_cache, save_pose_scan_cache
from core.pose.labeling.scan_progress import UnifiedScanProgress
from core.pose.video.video_registry import _open_video_capture, _suppress_ffmpeg_stderr


class LabelFrameQueueWorker(QThread):
    """Scan video blob shapes and build a diverse labeling queue."""

    unified_progress = pyqtSignal(int, int, str)
    queue_preview = pyqtSignal(list)
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        video_dir: Path,
        video_path: Path,
        frame_count: int,
        frames_to_analyze: int,
        arena: ArenaConfig,
        blob_params: BlobParams,
        *,
        build_from_disk_cache: bool = False,
        save_fingerprints: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._video_dir = video_dir
        self._video_path = video_path
        self._frame_count = frame_count
        self._frames_to_analyze = frames_to_analyze
        self._arena = arena
        self._blob_params = blob_params
        self._build_from_disk_cache = build_from_disk_cache
        self._save_fingerprints = save_fingerprints

    def run(self) -> None:
        try:
            gap = gap_from_frames_to_analyze(self._frame_count, self._frames_to_analyze)
            progress = UnifiedScanProgress(
                emit=lambda value, total, label: self.unified_progress.emit(
                    value, total, label
                )
            )

            if self._build_from_disk_cache:
                progress.begin_build_from_cache("Building diverse frame queue from cache…")
                cache = load_pose_scan_cache(
                    self._video_dir,
                    frame_count=self._frame_count,
                    video_path=self._video_path,
                    arena=self._arena,
                    blob_params=self._blob_params,
                    load_fingerprints=True,
                )
                if cache is None or not cache.fingerprints_loaded:
                    raise ValueError("Pose scan cache is missing or invalid.")
                fingerprints = cache.fingerprints
                coarse_stride = cache.coarse_stride
            else:
                with _suppress_ffmpeg_stderr():
                    old_log = cv2.getLogLevel()
                    cv2.setLogLevel(0)
                    cap = _open_video_capture(self._video_path)
                    if not cap.isOpened():
                        cv2.setLogLevel(old_log)
                        raise ValueError(f"Could not open video: {self._video_path}")
                    try:
                        fingerprints, coarse_stride = scan_shape_fingerprints_adaptive_sequential(
                            cap,
                            self._frame_count,
                            gap,
                            self._arena,
                            self._blob_params,
                            progress_coarse=lambda cur, tot: progress.coarse(
                                cur,
                                tot,
                                f"Scanning video for distinct poses… {cur}/{tot}",
                            ),
                            progress_refine=lambda cur, tot: progress.refine(
                                cur,
                                tot,
                                f"Refining distinct poses… {cur}/{tot}",
                            ),
                            should_stop=self.isInterruptionRequested,
                            status=self._emit_status_only,
                        )
                    finally:
                        cap.release()
                        cv2.setLogLevel(old_log)
                if self.isInterruptionRequested():
                    return

            def _on_pick(picks: list[int]) -> None:
                self.queue_preview.emit(list(picks))

            def _on_build(cur: int, tot: int) -> None:
                if self._build_from_disk_cache:
                    progress.build_from_cache(cur, tot, "Building diverse frame queue")
                else:
                    progress.build(cur, tot, "Building diverse frame queue")

            queue_ranks: dict[int, int] = {}
            queue = build_diverse_label_frame_queue(
                self._frame_count,
                gap,
                fingerprints,
                target=self._frames_to_analyze,
                on_pick=_on_pick,
                on_build_progress=_on_build,
                ranks=queue_ranks,
            )
            progress.save("Saving pose scan cache…")
            if self._save_fingerprints or not self._build_from_disk_cache:
                save_pose_scan_cache(
                    self._video_dir,
                    frame_count=self._frame_count,
                    video_path=self._video_path,
                    arena=self._arena,
                    blob_params=self._blob_params,
                    fingerprints=fingerprints,
                    coarse_stride=coarse_stride,
                    queue=queue,
                    gap=gap,
                    frames_to_analyze=self._frames_to_analyze,
                    queue_ranks=queue_ranks,
                )
            else:
                save_pose_scan_cache(
                    self._video_dir,
                    frame_count=self._frame_count,
                    video_path=self._video_path,
                    arena=self._arena,
                    blob_params=self._blob_params,
                    fingerprints=[],
                    coarse_stride=coarse_stride,
                    queue=queue,
                    gap=gap,
                    frames_to_analyze=self._frames_to_analyze,
                    fingerprints_unchanged=True,
                    queue_ranks=queue_ranks,
                )
            progress.done()
            self.finished_ok.emit(queue)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _emit_status_only(self, label: str) -> None:
        self.unified_progress.emit(0, 0, label)
