"""Tests for full-res blob detection mapped to preview overlays."""

from __future__ import annotations

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop
from core.pose.preview.preview_blob import (
    detect_blob_for_preview,
    preview_scale_for_frame,
    scale_blob_result,
)


def test_preview_scale_for_frame():
    assert preview_scale_for_frame(1280, 1280, 640) == 0.5
    assert preview_scale_for_frame(480, 640, 640) == 1.0


def test_scale_blob_result_maps_geometry_and_mask():
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
    scaled = scale_blob_result(blob, 0.5, 50, 50)
    assert scaled.found
    assert scaled.mask.shape == (50, 50)
    assert scaled.x0 == 15
    assert scaled.y0 == 15
    assert scaled.side == 20
    assert scaled.x1 == 35
    assert scaled.y1 == 35


def test_detect_blob_for_preview_uses_full_resolution_detection():
    arena = ArenaConfig(shape="circle", center_x=0.5, center_y=0.5, size=0.9)
    params = BlobParams(brightness_min=200, brightness_max=255, crop_padding_px=0)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    frame[50:70, 40:80] = 255

    display, preview_blob = detect_blob_for_preview(frame, arena, params, 64)
    full_blob = detect_blob_square_crop(frame, arena, params)

    assert display.shape[:2] == (64, 64)
    assert preview_blob.found
    assert full_blob.found
    assert preview_blob.side == max(8, int(round(full_blob.side * 0.5)))
    assert preview_blob.x0 == int(round(full_blob.x0 * 0.5))
