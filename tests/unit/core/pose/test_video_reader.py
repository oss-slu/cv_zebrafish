"""Tests for sequential video frame reader."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from core.pose.video.video_reader import VideoFrameReader


def _write_test_video(path: Path, n: int = 6) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (32, 32),
    )
    assert writer.isOpened()
    try:
        for i in range(n):
            frame = np.full((32, 32, 3), i * 30, dtype=np.uint8)
            writer.write(frame)
    finally:
        writer.release()


def test_read_same_index_returns_cached_frame(tmp_path: Path):
    path = tmp_path / "clip.avi"
    _write_test_video(path)
    reader = VideoFrameReader(path)
    try:
        first = reader.read(3)
        again = reader.read(3)
        assert first is not None
        assert again is not None
        assert np.array_equal(first, again)
    finally:
        reader.release()


def test_read_forward_small_jump(tmp_path: Path):
    path = tmp_path / "clip.avi"
    _write_test_video(path)
    reader = VideoFrameReader(path)
    try:
        reader.read(1)
        frame = reader.read(4)
        assert frame is not None
        assert int(frame[0, 0, 0]) == 4 * 30
    finally:
        reader.release()
