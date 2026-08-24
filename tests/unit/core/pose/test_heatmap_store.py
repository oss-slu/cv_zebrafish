"""Tests for heatmap archive I/O."""

from __future__ import annotations

import numpy as np
import pytest

from core.pose.inference.heatmap_store import (
    archive_is_complete,
    archive_missing_frames,
    estimate_heatmap_archive_bytes,
    list_heatmap_frame_indices,
    load_frame_heatmaps,
    load_frame_peak_locref,
    save_frame_heatmaps,
    upsample_heatmap_to_crop,
)


def test_upsample_and_roundtrip(tmp_path):
    small = np.zeros((9, 9), dtype=np.float32)
    small[4, 4] = 1.0
    big = upsample_heatmap_to_crop(small, 30, 30)
    assert big.shape == (30, 30)
    assert big[15, 15] > 0.5

    maps = {"Head": small, "BF": small * 0.5}
    locref = {
        "Head": np.array([0.1, -0.2], dtype=np.float32),
        "BF": np.array([0.3, 0.4], dtype=np.float32),
    }
    path = save_frame_heatmaps(
        tmp_path, 12, maps, crop_h=30, crop_w=30, peak_locref=locref
    )
    fi, loaded = load_frame_heatmaps(path)
    assert fi == 12
    assert loaded["Head"].shape == (30, 30)
    assert loaded["BF"].shape == (30, 30)
    assert "Head_locref" not in loaded
    peak_lr = load_frame_peak_locref(path)
    assert peak_lr["Head"][0] == pytest.approx(0.1, rel=1e-2)
    assert peak_lr["BF"][1] == pytest.approx(0.4, rel=1e-2)

    with np.load(path) as data:
        assert int(data["crop_h"]) == 30
        assert int(data["crop_w"]) == 30


def test_list_heatmap_archives(tmp_path, monkeypatch):
    from app_platform.paths import ai_labelled_dir
    from core.pose.inference.heatmap_store import list_heatmap_archives, save_frame_heatmaps

    session = "Sess"
    project = "default"
    video = "vid1"

    def _fake_ai(session_name, project_id, video_id):
        return tmp_path / session_name / project_id / video_id

    monkeypatch.setattr(
        "app_platform.paths.ai_labelled_dir",
        _fake_ai,
    )

    out = _fake_ai(session, project, video)
    hm_dir = out / "heatmaps"
    hm_dir.mkdir(parents=True)
    maps = {"Head": np.zeros((10, 10), dtype=np.float32)}
    save_frame_heatmaps(hm_dir, 0, maps, crop_h=10, crop_w=10)
    save_frame_heatmaps(hm_dir, 1, maps, crop_h=10, crop_w=10)

    archives = list_heatmap_archives(session, project, video)
    assert len(archives) == 1
    assert archives[0].frame_count == 2
    assert archives[0].path == hm_dir


def test_estimate_bytes():
    # 10k frames, 11 parts, 300px crop, float16
    est = estimate_heatmap_archive_bytes(10_002, 11, 300, dtype_bytes=2)
    assert est > 1_000_000_000  # ~2 GB order of magnitude


def test_archive_missing_frames(tmp_path):
    maps = {"Head": np.zeros((10, 10), dtype=np.float32)}
    save_frame_heatmaps(tmp_path, 0, maps, crop_h=10, crop_w=10)
    save_frame_heatmaps(tmp_path, 2, maps, crop_h=10, crop_w=10)
    assert list_heatmap_frame_indices(tmp_path) == {0, 2}
    assert archive_missing_frames(tmp_path, 4) == [1, 3]
    assert not archive_is_complete(tmp_path, 4)
    assert not archive_is_complete(tmp_path, 3)
