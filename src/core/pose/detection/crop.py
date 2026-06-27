"""Map coordinates between full frame and square fish crop."""

from __future__ import annotations

import numpy as np

from core.pose.detection.blob import BlobResult


def extract_square_crop(frame_bgr: np.ndarray, blob: BlobResult) -> np.ndarray:
    """
    Return a ``side × side`` BGR crop aligned with ``blob.x0`` / ``blob.y0``.

    Regions outside the frame are filled with black so labeling matches the
    yellow crop box drawn on the Arena/Blob preview (which is not clamped).
    """
    side = max(1, int(blob.side))
    out = np.zeros((side, side, 3), dtype=np.uint8)
    if frame_bgr is None or frame_bgr.size == 0:
        return out
    h, w = frame_bgr.shape[:2]
    x0, y0 = int(blob.x0), int(blob.y0)
    src_x0 = max(0, x0)
    src_y0 = max(0, y0)
    src_x1 = min(w, x0 + side)
    src_y1 = min(h, y0 + side)
    if src_x1 <= src_x0 or src_y1 <= src_y0:
        return out
    dst_x0 = src_x0 - x0
    dst_y0 = src_y0 - y0
    out[dst_y0 : dst_y0 + (src_y1 - src_y0), dst_x0 : dst_x0 + (src_x1 - src_x0)] = frame_bgr[
        src_y0:src_y1, src_x0:src_x1
    ]
    return out


def fish_mask_in_crop(blob: BlobResult) -> np.ndarray:
    """Fish binary mask in square-crop coordinates (matches Arena/Blob outline)."""
    side = max(1, int(blob.side))
    out = np.zeros((side, side), dtype=np.uint8)
    if not blob.found:
        return out
    h, w = blob.mask.shape[:2]
    x0, y0 = int(blob.x0), int(blob.y0)
    src_x0 = max(0, x0)
    src_y0 = max(0, y0)
    src_x1 = min(w, x0 + side)
    src_y1 = min(h, y0 + side)
    if src_x1 <= src_x0 or src_y1 <= src_y0:
        return out
    dst_x0 = src_x0 - x0
    dst_y0 = src_y0 - y0
    region = blob.mask[src_y0:src_y1, src_x0:src_x1]
    out[dst_y0 : dst_y0 + region.shape[0], dst_x0 : dst_x0 + region.shape[1]] = (
        region.astype(np.uint8)
    )
    return out


def crop_to_full_frame(x_crop: float, y_crop: float, blob: BlobResult) -> tuple[float, float]:
    return x_crop + blob.x0, y_crop + blob.y0


def full_frame_to_crop(x_full: float, y_full: float, blob: BlobResult) -> tuple[float, float]:
    return x_full - blob.x0, y_full - blob.y0


def clamp_crop_point(x: float, y: float, blob: BlobResult) -> tuple[float, float]:
    side = max(1, blob.side)
    return max(0.0, min(float(side - 1), x)), max(0.0, min(float(side - 1), y))
