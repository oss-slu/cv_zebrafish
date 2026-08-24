"""Background scan for mismatching blob frames."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.cache.playback_blob_cache import PlaybackBlobEntry
from core.pose.detection.blob_qc import (
    FrameBlobQC,
    find_mismatch_frames_from_cache,
    find_mismatch_frames_from_qc,
)


class MismatchDetectWorker(QThread):
    """Build mismatch indices from playback cache or saved blob QC."""

    progress = pyqtSignal(int, int)
    finished_ok = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        *,
        entries: list[PlaybackBlobEntry] | None = None,
        qc_frames: list[FrameBlobQC] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._entries = entries
        self._qc_frames = qc_frames

    def run(self) -> None:
        try:
            if self._entries is not None:
                mismatches = find_mismatch_frames_from_cache(
                    self._entries,
                    progress=lambda cur, tot: self.progress.emit(cur, tot),
                )
            elif self._qc_frames is not None:
                self.progress.emit(0, 1)
                mismatches = find_mismatch_frames_from_qc(self._qc_frames)
                self.progress.emit(1, 1)
            else:
                raise ValueError("No blob cache or QC data available for mismatch detection.")
            self.finished_ok.emit(list(mismatches))
        except Exception as exc:
            self.failed.emit(str(exc))
