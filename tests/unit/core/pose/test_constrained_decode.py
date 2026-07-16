"""Tests for constrained heatmap decode."""

from __future__ import annotations

import numpy as np

from core.pose.inference.constrained_decode import (
    ConstrainedDecodeParams,
    build_search_mask,
    decode_frame_constrained,
    peak_from_masked_heatmap,
)


def test_peak_inside_blob_mask_only():
    hm = np.zeros((20, 20), dtype=np.float64)
    hm[5, 5] = 0.2
    hm[15, 15] = 0.9
    mask = np.zeros((20, 20), dtype=bool)
    mask[4:8, 4:8] = True
    peak = peak_from_masked_heatmap(hm, mask)
    assert peak is not None
    x, y, score = peak
    assert score == 0.2
    assert (x, y) == (5.0, 5.0)


def test_temporal_window_blocks_distant_peak():
    hm = np.zeros((40, 40), dtype=np.float64)
    hm[5, 5] = 0.95
    hm[35, 35] = 0.99
    fish = np.ones((40, 40), dtype=bool)
    mask = build_search_mask(40, 40, fish, prev_xy=(5.0, 5.0), radius_px=8.0)
    peak = peak_from_masked_heatmap(hm, mask)
    assert peak is not None
    assert peak[2] == 0.95


def test_decode_omits_low_likelihood():
    heatmaps = {
        "A": np.zeros((10, 10), dtype=np.float64),
        "B": np.zeros((10, 10), dtype=np.float64),
    }
    heatmaps["A"][3, 3] = 0.3
    heatmaps["B"][7, 7] = 0.9
    fish = np.ones((10, 10), dtype=bool)
    params = ConstrainedDecodeParams(min_likelihood=0.6)
    out = decode_frame_constrained(
        heatmaps,
        fish,
        bodyparts=["A", "B"],
        prev_positions_crop={"A": (3.0, 3.0), "B": (7.0, 7.0)},
        search_radii={"A": 20.0, "B": 20.0},
        params=params,
        crop_side=10,
    )
    assert out.positions["A"] is None
    assert out.positions["B"] is not None
