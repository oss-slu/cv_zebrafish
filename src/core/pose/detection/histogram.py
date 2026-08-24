"""Brightness threshold suggestions from arena-masked pixels."""

from __future__ import annotations

from collections.abc import Callable

import cv2
import numpy as np

from core.pose.detection.arena import ArenaConfig, effective_arena_mask

# Largest acceptable fish blob as a fraction of the full frame area.
# Fish on a dark dish should be well below this; values near 1.0 indicate
# background leakage or a mis-sized arena mask.
BLOB_MAX_FRAME_FRACTION = 0.35

_MIN_BLOB_AREA_PX = 32
_CANCEL_CHECK_INTERVAL = 16


def _largest_component_area(binary: np.ndarray) -> int:
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8), connectivity=8)
    if n <= 1:
        return 0
    return int(stats[1:, cv2.CC_STAT_AREA].max())


def suggest_blob_selection_values(
    gray: np.ndarray,
    arena: ArenaConfig,
    *,
    max_frame_fraction: float = BLOB_MAX_FRAME_FRACTION,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[int, int]:
    """
    Suggest (min, max) uchar thresholds for blob detection inside the arena.

    Estimates background from the lower histogram tail, then searches for the
    largest bright blob that contrasts with background while occupying at most
    ``max_frame_fraction`` of the full frame. Cooperative ``cancel_check`` is
    polled periodically so UI callers can abort long searches.
    """
    if gray.ndim == 3:
        gray = np.mean(gray, axis=2)
    gray_u8 = gray.astype(np.uint8)
    h, w = gray_u8.shape[:2]
    mask = effective_arena_mask(h, w, arena)
    vals = gray_u8[mask]
    if vals.size < _MIN_BLOB_AREA_PX:
        return 40, 255

    frame_area = h * w
    max_blob_area = max(_MIN_BLOB_AREA_PX, int(round(max_frame_fraction * frame_area)))
    bg_level = float(np.percentile(vals, 20.0))

    best_thresh = None
    best_area = 0
    for step, thresh in enumerate(range(int(max(1, round(bg_level))), 256)):
        if cancel_check is not None and step % _CANCEL_CHECK_INTERVAL == 0 and cancel_check():
            break
        binary = (gray_u8 >= thresh) & mask
        area = _largest_component_area(binary)
        if area < _MIN_BLOB_AREA_PX:
            continue
        if area > max_blob_area:
            break
        if area > best_area:
            best_area = area
            best_thresh = thresh

    if best_thresh is None:
        return suggest_brightness_range(gray_u8, arena)

    blob_mask = (gray_u8 >= best_thresh) & mask
    blob_mask = _largest_component_mask(blob_mask)
    if not blob_mask.any():
        return suggest_brightness_range(gray_u8, arena)

    blob_vals = gray_u8[blob_mask]
    lo = int(max(0, min(254, round(float(np.percentile(blob_vals, 5.0))))))
    hi = int(max(lo + 1, min(255, round(float(np.percentile(blob_vals, 99.0))))))
    return lo, hi


def _largest_component_mask(mask: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros_like(mask, dtype=bool)
    best = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return labels == best


def suggest_brightness_range(
    gray: np.ndarray,
    arena: ArenaConfig,
    *,
    low_percentile: float = 85.0,
    high_percentile: float = 99.5,
    max_frame_fraction: float = BLOB_MAX_FRAME_FRACTION,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[int, int]:
    """
    Return (min, max) uchar thresholds for blob detection inside arena.

    When ``cancel_check`` is omitted, uses percentile fallback only. When a
    cancellable path is desired (UI Suggest values), pass ``cancel_check`` to
    enable histogram blob search capped by ``max_frame_fraction``.
    """
    if cancel_check is not None:
        return suggest_blob_selection_values(
            gray,
            arena,
            max_frame_fraction=max_frame_fraction,
            cancel_check=cancel_check,
        )
    if gray.ndim == 3:
        gray = np.mean(gray, axis=2)
    gray = gray.astype(np.float32)
    h, w = gray.shape[:2]
    mask = effective_arena_mask(h, w, arena)
    vals = gray[mask]
    if vals.size < 32:
        return 40, 255
    lo = float(np.percentile(vals, low_percentile))
    hi = float(np.percentile(vals, high_percentile))
    lo_i = int(max(0, min(254, round(lo))))
    hi_i = int(max(lo_i + 1, min(255, round(hi))))
    return lo_i, hi_i
