"""Map full-resolution blob detection onto preview-resolution overlays."""

from __future__ import annotations

import cv2
import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop
from core.pose.video.video_reader import downscale_frame


def preview_scale_for_frame(frame_h: int, frame_w: int, max_edge: int) -> float:
    """Return the uniform scale applied by ``downscale_frame``."""
    if max_edge <= 0 or frame_w <= 0 or frame_h <= 0:
        return 1.0
    longest = max(frame_h, frame_w)
    if longest <= max_edge:
        return 1.0
    return max_edge / longest


def preview_dimensions(frame_h: int, frame_w: int, max_edge: int) -> tuple[int, int, float]:
    """Return preview height, width, and scale for a source frame."""
    scale = preview_scale_for_frame(frame_h, frame_w, max_edge)
    preview_w = max(1, int(round(frame_w * scale)))
    preview_h = max(1, int(round(frame_h * scale)))
    if frame_w > 0:
        scale = preview_w / frame_w
    return preview_h, preview_w, scale


def scale_blob_result(
    blob: BlobResult,
    scale: float,
    preview_h: int,
    preview_w: int,
) -> BlobResult:
    """Scale blob geometry and mask from full-frame coords to preview coords."""
    if scale == 1.0 and blob.mask.shape[:2] == (preview_h, preview_w):
        return blob

    def _scaled_int(value: float) -> int:
        return int(round(value * scale))

    if not blob.found:
        empty_mask = (
            np.zeros((preview_h, preview_w), dtype=bool)
            if preview_h > 0 and preview_w > 0
            else blob.mask
        )
        side = max(8, _scaled_int(blob.side))
        x0 = _scaled_int(blob.x0)
        y0 = _scaled_int(blob.y0)
        return BlobResult(
            mask=empty_mask,
            center_x=blob.center_x * scale,
            center_y=blob.center_y * scale,
            side=side,
            x0=x0,
            y0=y0,
            x1=x0 + side,
            y1=y0 + side,
            found=False,
        )

    if blob.mask.size > 0:
        mask = (
            cv2.resize(
                blob.mask.astype(np.uint8),
                (preview_w, preview_h),
                interpolation=cv2.INTER_NEAREST,
            )
            > 0
        )
    else:
        mask = np.zeros((preview_h, preview_w), dtype=bool)

    side = max(8, _scaled_int(blob.side))
    x0 = _scaled_int(blob.x0)
    y0 = _scaled_int(blob.y0)
    return BlobResult(
        mask=mask,
        center_x=blob.center_x * scale,
        center_y=blob.center_y * scale,
        side=side,
        x0=x0,
        y0=y0,
        x1=x0 + side,
        y1=y0 + side,
        found=True,
    )


def detect_blob_for_preview(
    frame_bgr: np.ndarray,
    arena: ArenaConfig,
    params: BlobParams,
    preview_max_edge: int,
) -> tuple[np.ndarray, BlobResult]:
    """
    Detect on the full-resolution frame, then return the downscaled display
    frame and blob overlays mapped into preview pixel coordinates.
    """
    full_blob = detect_blob_square_crop(frame_bgr, arena, params)
    preview_h, preview_w, scale = preview_dimensions(
        frame_bgr.shape[0], frame_bgr.shape[1], preview_max_edge
    )
    display = downscale_frame(frame_bgr, preview_max_edge)
    if scale != 1.0:
        preview_blob = scale_blob_result(full_blob, scale, preview_h, preview_w)
    else:
        preview_blob = full_blob
    return display, preview_blob
