"""Tests for blob mismatch detection and cycling."""

from __future__ import annotations

import numpy as np

from core.pose.cache.playback_blob_cache import PlaybackBlobEntry
from core.pose.detection.blob_qc import (
    BlobAverageStats,
    BlobFrameStats,
    find_mismatch_frames,
    next_mismatch_frame,
    stats_from_playback_entries,
)


def _stat(
    frame_index: int,
    *,
    found: bool = True,
    center_x: float = 50.0,
    center_y: float = 50.0,
    volume_px: int = 100,
    length_px: int = 20,
    width_px: int = 10,
    crop_side: int = 40,
) -> BlobFrameStats:
    return BlobFrameStats(
        frame_index,
        found,
        center_x,
        center_y,
        volume_px,
        length_px,
        width_px,
        crop_side,
    )


def test_find_mismatch_frames_volume_outlier():
    stats = [
        _stat(0, volume_px=100),
        _stat(1, volume_px=100),
        _stat(2, volume_px=300),
        _stat(3, volume_px=100),
    ]
    assert find_mismatch_frames(stats) == [2]


def test_find_mismatch_frames_length_outlier():
    avg = BlobAverageStats(volume_px=100, length_px=20, width_px=10, crop_side=40)
    stats = [
        _stat(0, length_px=20, width_px=10),
        _stat(1, length_px=20, width_px=10),
        _stat(2, length_px=45, width_px=10),
    ]
    assert find_mismatch_frames(stats, averages=avg) == [2]


def test_find_mismatch_frames_width_outlier():
    avg = BlobAverageStats(volume_px=100, length_px=20, width_px=10, crop_side=40)
    stats = [
        _stat(0, length_px=20, width_px=10),
        _stat(1, length_px=20, width_px=10),
        _stat(2, length_px=20, width_px=25),
    ]
    assert find_mismatch_frames(stats, averages=avg) == [2]


def test_find_mismatch_frames_center_jump():
    avg = BlobAverageStats(volume_px=100, length_px=20, width_px=10, crop_side=40)
    stats = [
        _stat(0, center_x=50, center_y=50),
        _stat(1, center_x=62, center_y=50),
    ]
    assert find_mismatch_frames(stats, averages=avg) == [1]


def test_find_mismatch_frames_not_found():
    stats = [
        _stat(0),
        _stat(1, found=False),
        _stat(2),
    ]
    assert find_mismatch_frames(stats) == [1]


def test_next_mismatch_frame_cycles_and_wraps():
    mismatches = [5, 20, 30]
    assert next_mismatch_frame(mismatches, 0) == 5
    assert next_mismatch_frame(mismatches, 5) == 20
    assert next_mismatch_frame(mismatches, 12) == 20
    assert next_mismatch_frame(mismatches, 20) == 30
    assert next_mismatch_frame(mismatches, 30) == 5
    assert next_mismatch_frame(mismatches, 999) == 5
    assert next_mismatch_frame([], 0) is None


def test_stats_from_playback_entries():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:50, 30:50] = True
    entry = PlaybackBlobEntry(
        True,
        fish_x0=30,
        fish_y0=40,
        fish_x1=50,
        fish_y1=50,
        crop_x0=20,
        crop_y0=30,
        crop_side=40,
        mask=mask,
    )
    stats = stats_from_playback_entries([entry])
    assert len(stats) == 1
    assert stats[0].found
    assert stats[0].volume_px == int(mask.sum())
    assert stats[0].length_px == 20
    assert stats[0].width_px == 10
    assert stats[0].crop_side == 40
