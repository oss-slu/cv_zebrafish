"""Brightness threshold suggestions from arena-masked pixels."""

from __future__ import annotations

import numpy as np

from core.pose.detection.arena import ArenaConfig, arena_mask


def suggest_brightness_range(
    gray: np.ndarray,
    arena: ArenaConfig,
    *,
    low_percentile: float = 85.0,
    high_percentile: float = 99.5,
) -> tuple[int, int]:
    """
    Return (min, max) uchar thresholds for blob detection inside arena.

    Fish are bright on dark dish — use high percentiles of masked pixels.
    """
    if gray.ndim == 3:
        gray = np.mean(gray, axis=2)
    gray = gray.astype(np.float32)
    h, w = gray.shape[:2]
    mask = arena_mask(h, w, arena)
    vals = gray[mask]
    if vals.size < 32:
        return 40, 255
    lo = float(np.percentile(vals, low_percentile))
    hi = float(np.percentile(vals, high_percentile))
    lo_i = int(max(0, min(254, round(lo))))
    hi_i = int(max(lo_i + 1, min(255, round(hi))))
    return lo_i, hi_i
