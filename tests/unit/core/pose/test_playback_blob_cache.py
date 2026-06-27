"""Tests for playback blob cache helpers."""

from __future__ import annotations

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult
from core.pose.cache.playback_blob_cache import PlaybackBlobEntry, playback_blob_cache_key


def test_playback_blob_entry_from_blob():
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 30:70] = True
    blob = BlobResult(
        mask=mask,
        center_x=50.0,
        center_y=50.0,
        side=40,
        x0=30,
        y0=30,
        x1=70,
        y1=70,
        found=True,
    )
    entry = PlaybackBlobEntry.from_blob(blob)
    assert entry.found
    assert entry.mask.shape == (100, 100)
    assert entry.mask[40:60, 30:70].all()
    assert entry.fish_x0 == 30
    assert entry.fish_y0 == 40
    assert entry.crop_x0 == 30
    assert entry.crop_side == 40


def test_playback_blob_cache_key_stable():
    arena = ArenaConfig()
    params = BlobParams()
    assert playback_blob_cache_key(arena, params) == playback_blob_cache_key(arena, params)


def test_playback_overlay_cache_roundtrip(tmp_path):
    from core.pose.cache.playback_blob_cache import (
        load_playback_overlay_cache,
        save_playback_overlay_cache,
    )

    mask = np.zeros((48, 64), dtype=bool)
    mask[10:30, 20:50] = True
    blob = BlobResult(
        mask=mask,
        center_x=35.0,
        center_y=20.0,
        side=32,
        x0=19,
        y0=4,
        x1=51,
        y1=36,
        found=True,
    )
    entries = [PlaybackBlobEntry.from_blob(blob), PlaybackBlobEntry.empty()]
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fake")
    arena = ArenaConfig()
    params = BlobParams()
    save_playback_overlay_cache(
        tmp_path,
        entries,
        frame_count=2,
        video_path=video,
        arena=arena,
        blob_params=params,
        preview_max_edge=640,
    )
    loaded = load_playback_overlay_cache(
        tmp_path,
        frame_count=2,
        video_path=video,
        arena=arena,
        blob_params=params,
        preview_max_edge=640,
    )
    assert loaded is not None
    assert len(loaded) == 2
    assert loaded[0].found
    assert loaded[0].mask.shape == (48, 64)
    assert not loaded[1].found
