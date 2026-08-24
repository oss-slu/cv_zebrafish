"""Tests for blob detection context parity."""

from __future__ import annotations

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import (
    BlobDetectionContext,
    BlobParams,
    detect_blob_square_crop,
    detect_blob_square_crop_ctx,
)


def test_detect_blob_ctx_matches_square_crop():
    arena = ArenaConfig(shape="circle", center_x=0.5, center_y=0.5, size=0.9)
    params = BlobParams(brightness_min=200, brightness_max=255, crop_padding_px=0)
    frame = np.zeros((128, 128, 3), dtype=np.uint8)
    frame[50:70, 40:80] = 255

    direct = detect_blob_square_crop(frame, arena, params)
    ctx = BlobDetectionContext.for_frame(128, 128, arena, params)
    via_ctx = detect_blob_square_crop_ctx(frame, params, ctx)

    assert direct.found == via_ctx.found
    assert np.array_equal(direct.mask, via_ctx.mask)
    assert direct.x0 == via_ctx.x0
    assert direct.y0 == via_ctx.y0
    assert direct.side == via_ctx.side
