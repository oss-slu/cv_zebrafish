"""Tests for histogram-based blob threshold suggestions."""

from __future__ import annotations

import cv2
import numpy as np

from core.pose.detection.arena import ArenaConfig, arena_mask
from core.pose.detection.histogram import (
    BLOB_MAX_FRAME_FRACTION,
    suggest_blob_selection_values,
    suggest_brightness_range,
)


def _largest_component_area(binary: np.ndarray) -> int:
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary.astype(np.uint8), connectivity=8)
    if n <= 1:
        return 0
    return int(stats[1:, cv2.CC_STAT_AREA].max())


def _frame_with_fish_and_glare() -> np.ndarray:
    gray = np.full((200, 200), 30, dtype=np.uint8)
    gray[80:95, 90:130] = 200
    gray[0:120, 0:120] = 220
    return gray


def test_suggest_blob_selection_values_prefers_fish_under_cap():
    gray = _frame_with_fish_and_glare()
    arena = ArenaConfig(
        rect_x=0.05,
        rect_y=0.05,
        rect_w=0.9,
        rect_h=0.9,
        confirmed=True,
    )
    lo, hi = suggest_blob_selection_values(gray, arena, max_frame_fraction=BLOB_MAX_FRAME_FRACTION)
    assert 0 <= lo < hi <= 255
    mask = arena_mask(*gray.shape[:2], arena)
    blob_area = _largest_component_area((gray >= lo) & mask)
    max_area = int(BLOB_MAX_FRAME_FRACTION * gray.size)
    assert blob_area <= max_area
    assert blob_area >= 32


def test_suggest_brightness_range_cancel_check_uses_blob_search():
    gray = _frame_with_fish_and_glare()
    arena = ArenaConfig(
        rect_x=0.05,
        rect_y=0.05,
        rect_w=0.9,
        rect_h=0.9,
        confirmed=True,
    )
    cancelled = {"hit": False}

    def cancel_check() -> bool:
        cancelled["hit"] = True
        return True

    lo, hi = suggest_brightness_range(gray, arena, cancel_check=cancel_check)
    assert cancelled["hit"]
    assert 0 <= lo < hi <= 255
