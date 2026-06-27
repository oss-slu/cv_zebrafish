"""Tests for persisted pose scan cache."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams
from core.pose.labeling.frame_sampler import build_diverse_label_frame_queue
from core.pose.labeling.pose_scan_cache import (
    load_pose_scan_cache,
    save_pose_scan_cache,
    scan_settings_hash,
)


def _unit_vec(i: int, dim: int = 32 * 32) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[i % dim] = 1.0
    return v


def test_pose_scan_cache_roundtrip(tmp_path: Path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    video_path = video_dir / "source.mp4"
    video_path.write_bytes(b"fake-video")

    arena = ArenaConfig()
    blob = BlobParams(brightness_min=50, crop_padding_px=10)
    n = 120
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, n, 15):
        fps[i] = _unit_vec(i // 15)
    queue = build_diverse_label_frame_queue(n, 12, fps, target=12)

    save_pose_scan_cache(
        video_dir,
        frame_count=n,
        video_path=video_path,
        arena=arena,
        blob_params=blob,
        fingerprints=fps,
        coarse_stride=12,
        queue=queue,
        gap=12,
        frames_to_analyze=12,
    )

    loaded = load_pose_scan_cache(
        video_dir,
        frame_count=n,
        video_path=video_path,
        arena=arena,
        blob_params=blob,
    )
    assert loaded is not None
    assert loaded.coarse_stride == 12
    assert loaded.queues_by_target[12] == queue
    assert loaded.last_frames_to_analyze == 12
    assert loaded.last_queue == queue
    assert loaded.fingerprints[0] is not None
    assert loaded.fingerprints[1] is None


def test_pose_scan_cache_invalidates_on_settings_change(tmp_path: Path):
    video_dir = tmp_path / "video"
    video_dir.mkdir()
    video_path = video_dir / "source.mp4"
    video_path.write_bytes(b"fake-video")
    arena = ArenaConfig()
    blob = BlobParams()
    fps = [_unit_vec(0)] + [None] * 9
    save_pose_scan_cache(
        video_dir,
        frame_count=10,
        video_path=video_path,
        arena=arena,
        blob_params=blob,
        fingerprints=fps,
        coarse_stride=5,
    )
    other_blob = BlobParams(brightness_min=99)
    assert scan_settings_hash(arena, blob) != scan_settings_hash(arena, other_blob)
    assert (
        load_pose_scan_cache(
            video_dir,
            frame_count=10,
            video_path=video_path,
            arena=arena,
            blob_params=other_blob,
        )
        is None
    )
