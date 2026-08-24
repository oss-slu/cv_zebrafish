"""Tests for playback blob cache helpers."""

from __future__ import annotations

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult
from core.pose.cache.playback_blob_cache import (
    PlaybackBlobEntry,
    PlaybackCacheBuffers,
    playback_blob_cache_key,
    save_playback_overlay_buffers,
)


def _sample_blob() -> BlobResult:
    mask = np.zeros((100, 100), dtype=bool)
    mask[40:60, 30:70] = True
    return BlobResult(
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


def test_playback_blob_entry_from_blob():
    blob = _sample_blob()
    entry = PlaybackBlobEntry.from_blob(blob)
    assert entry.found
    assert entry.mask.shape == (100, 100)
    assert entry.mask[40:60, 30:70].all()
    assert entry.fish_x0 == 30
    assert entry.fish_y0 == 40
    assert entry.crop_x0 == 30
    assert entry.crop_side == 40


def test_buffer_write_matches_from_blob():
    blob = _sample_blob()
    expected = PlaybackBlobEntry.from_blob(blob)
    buffers = PlaybackCacheBuffers.allocate(1, 100, 100)
    buffers.write_blob(0, blob)
    actual = buffers.to_entries()[0]
    assert actual.found == expected.found
    assert actual.fish_x0 == expected.fish_x0
    assert actual.fish_y0 == expected.fish_y0
    assert actual.fish_x1 == expected.fish_x1
    assert actual.fish_y1 == expected.fish_y1
    assert actual.crop_x0 == expected.crop_x0
    assert actual.crop_y0 == expected.crop_y0
    assert actual.crop_side == expected.crop_side
    assert np.array_equal(actual.mask, expected.mask)


def test_playback_blob_cache_key_stable():
    arena = ArenaConfig()
    params = BlobParams()
    assert playback_blob_cache_key(arena, params) == playback_blob_cache_key(arena, params)


def test_playback_overlay_cache_roundtrip(tmp_path):
    from core.pose.cache.playback_blob_cache import load_playback_overlay_cache

    blob = _sample_blob()
    buffers = PlaybackCacheBuffers.allocate(2, 100, 100)
    buffers.write_blob(0, blob)
    video = tmp_path / "source.mp4"
    video.write_bytes(b"fake")
    arena = ArenaConfig()
    params = BlobParams()
    save_playback_overlay_buffers(
        tmp_path,
        buffers,
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
    assert loaded[0].mask.shape == (100, 100)
    assert loaded[0].mask[40:60, 30:70].all()
    assert not loaded[1].found
