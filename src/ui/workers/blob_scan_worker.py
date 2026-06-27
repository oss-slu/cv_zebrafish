"""Batch blob QC scan for timeline jump flags."""

from __future__ import annotations

from pathlib import Path

import cv2
from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.detection.arena import ArenaConfig, load_arena
from core.pose.detection.blob import BlobParams, load_blob_params
from core.pose.detection.blob_qc import save_blob_qc, scan_video_blob_centers
from core.pose.video.video_registry import resolve_video_source


class BlobScanWorker(QThread):
    progress = pyqtSignal(int, int)  # current, total
    finished_ok = pyqtSignal(str)  # qc json path
    failed = pyqtSignal(str)

    def __init__(
        self,
        video_dir: Path,
        *,
        jump_threshold_px: float = 80.0,
        parent=None,
    ):
        super().__init__(parent)
        self._video_dir = video_dir
        self._jump_threshold = jump_threshold_px

    def run(self) -> None:
        try:
            src = resolve_video_source(self._video_dir)
            if src is None:
                raise ValueError("No video source found for blob scan.")
            arena = load_arena(self._video_dir / "arena.json")
            params = load_blob_params(self._video_dir / "blob_params.json")
            cap = cv2.VideoCapture(str(src))
            if not cap.isOpened():
                raise ValueError(f"Could not open video: {src}")
            try:
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                frames = scan_video_blob_centers(
                    cap,
                    arena,
                    params,
                    jump_threshold_px=self._jump_threshold,
                    progress=lambda cur, tot: self.progress.emit(cur, tot),
                )
            finally:
                cap.release()
            out = self._video_dir / "blob_qc.json"
            save_blob_qc(out, frames, jump_threshold_px=self._jump_threshold)
            self.progress.emit(total or len(frames), total or len(frames))
            self.finished_ok.emit(str(out))
        except Exception as exc:
            self.failed.emit(str(exc))
