"""Sequential-friendly OpenCV frame reader for Pose Studio playback."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.pose.video.video_registry import _open_video_capture, _suppress_ffmpeg_stderr

# Max jump before falling back to a direct seek (forward scrub/play uses sequential read).
_SEQUENTIAL_SEEK_THRESHOLD = 8


class VideoFrameReader:
    """Read frames by index; advances sequentially when possible."""

    def __init__(self, path: Path):
        self._path = path
        with _suppress_ffmpeg_stderr():
            old_log = cv2.getLogLevel()
            cv2.setLogLevel(0)
            try:
                self._cap = _open_video_capture(path)
            finally:
                cv2.setLogLevel(old_log)
        self._last_index = -1
        self._last_frame: np.ndarray | None = None

    @property
    def path(self) -> Path:
        return self._path

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._last_index = -1
        self._last_frame = None

    def _seek_and_read(self, index: int) -> np.ndarray | None:
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self._cap.read()
        if not ok or frame is None:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = self._cap.read()
        if ok and frame is not None:
            self._last_index = index
            self._last_frame = frame
            return frame
        return None

    def read(self, index: int) -> np.ndarray | None:
        if not self.is_opened():
            return None
        index = max(0, int(index))
        if index == self._last_index:
            return None if self._last_frame is None else self._last_frame.copy()
        if index == self._last_index + 1:
            ok, frame = self._cap.read()
        elif index < self._last_index or index - self._last_index > _SEQUENTIAL_SEEK_THRESHOLD:
            return self._seek_and_read(index)
        else:
            frame = None
            ok = False
            while self._last_index < index:
                ok, frame = self._cap.read()
                if not ok or frame is None:
                    self._last_frame = None
                    return None
                self._last_index += 1
            if frame is None:
                return self._seek_and_read(index)
        if ok and frame is not None:
            self._last_index = index
            self._last_frame = frame
            return frame.copy()
        self._last_frame = None
        return None


def downscale_frame(frame: np.ndarray, max_edge: int) -> np.ndarray:
    """Shrink a BGR frame so its longest side is at most ``max_edge``."""
    if max_edge <= 0:
        return frame
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return frame
    scale = max_edge / longest
    return cv2.resize(
        frame,
        (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
