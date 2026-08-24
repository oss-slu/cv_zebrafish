"""Fish blob detection and square crop inside arena."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from core.pose.detection.arena import ArenaConfig, effective_arena_mask


@dataclass
class BlobParams:
    brightness_min: int = 40
    brightness_max: int = 255
    morph_open_size: int = 3
    morph_close_size: int = 5
    blob_padding_px: int = 0
    crop_padding_px: int = 8

    def to_dict(self) -> dict:
        return {
            "brightness_min": self.brightness_min,
            "brightness_max": self.brightness_max,
            "morph_open_size": self.morph_open_size,
            "morph_close_size": self.morph_close_size,
            "blob_padding_px": self.blob_padding_px,
            "crop_padding_px": self.crop_padding_px,
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "BlobParams":
        if not raw:
            return cls()
        legacy_pad = raw.get("padding_px")
        default_crop = int(legacy_pad) if legacy_pad is not None else 8
        return cls(
            brightness_min=int(raw.get("brightness_min", 40)),
            brightness_max=int(raw.get("brightness_max", 255)),
            morph_open_size=int(raw.get("morph_open_size", 3)),
            morph_close_size=int(raw.get("morph_close_size", 5)),
            blob_padding_px=int(raw.get("blob_padding_px", 0)),
            crop_padding_px=int(raw.get("crop_padding_px", default_crop)),
        )


def load_blob_params(path: Path) -> BlobParams:
    if not path.is_file():
        return BlobParams()
    return BlobParams.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_blob_params(path: Path, params: BlobParams) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(params.to_dict(), indent=2), encoding="utf-8")


@dataclass
class BlobResult:
    mask: np.ndarray
    center_x: float
    center_y: float
    side: int
    x0: int
    y0: int
    x1: int
    y1: int
    found: bool


def mask_bbox_stats(mask: np.ndarray) -> tuple[int, int, int]:
    """Return (volume_px, length_px, width_px) from a boolean fish mask."""
    if mask.size == 0 or not mask.any():
        return 0, 0, 0
    ys, xs = np.where(mask)
    fw = int(xs.max() - xs.min() + 1)
    fh = int(ys.max() - ys.min() + 1)
    return int(mask.sum()), max(fw, fh), min(fw, fh)


def _largest_component(mask: np.ndarray) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    if n <= 1:
        return np.zeros_like(mask, dtype=bool)
    areas = stats[1:, cv2.CC_STAT_AREA]
    best = 1 + int(np.argmax(areas))
    return labels == best


def _dilate_mask(mask: np.ndarray, padding_px: int, clip_mask: np.ndarray | None = None) -> np.ndarray:
    pad = int(padding_px)
    if pad <= 0:
        return mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1, 2 * pad + 1))
    dilated = cv2.dilate(mask.astype(np.uint8), k, iterations=1) > 0
    if clip_mask is not None:
        dilated &= clip_mask
    return dilated


def _morph_kernel(size: int) -> np.ndarray | None:
    if size <= 1:
        return None
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


@dataclass
class BlobDetectionContext:
    """Reusable arena mask and morphology kernels for a fixed frame size."""

    arena_mask: np.ndarray
    open_kernel: np.ndarray | None
    close_kernel: np.ndarray | None

    @classmethod
    def for_frame(
        cls,
        frame_h: int,
        frame_w: int,
        arena: ArenaConfig,
        params: BlobParams,
    ) -> "BlobDetectionContext":
        return cls(
            arena_mask=effective_arena_mask(frame_h, frame_w, arena),
            open_kernel=_morph_kernel(params.morph_open_size),
            close_kernel=_morph_kernel(params.morph_close_size),
        )


def _blob_from_fish_mask(
    fish: np.ndarray,
    *,
    h: int,
    w: int,
    params: BlobParams,
    clip_mask: np.ndarray,
) -> BlobResult:
    if not fish.any():
        return BlobResult(
            mask=fish,
            center_x=w / 2,
            center_y=h / 2,
            side=min(h, w) // 4,
            x0=0,
            y0=0,
            x1=w,
            y1=h,
            found=False,
        )
    fish = _dilate_mask(fish, params.blob_padding_px, clip_mask)
    ys, xs = np.where(fish)
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    crop_pad = int(params.crop_padding_px)
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    side = max(x1 - x0, y1 - y0) + 2 * crop_pad
    side = int(max(8, min(side, max(h, w))))
    half = side / 2.0
    sx0 = int(round(cx - half))
    sy0 = int(round(cy - half))
    sx1 = sx0 + side
    sy1 = sy0 + side
    return BlobResult(
        mask=fish,
        center_x=cx,
        center_y=cy,
        side=side,
        x0=sx0,
        y0=sy0,
        x1=sx1,
        y1=sy1,
        found=True,
    )


def detect_blob_square_crop(
    frame_bgr: np.ndarray,
    arena: ArenaConfig,
    params: BlobParams,
) -> BlobResult:
    h, w = frame_bgr.shape[:2]
    ctx = BlobDetectionContext.for_frame(h, w, arena, params)
    return detect_blob_square_crop_ctx(frame_bgr, params, ctx)


def detect_blob_square_crop_ctx(
    frame_bgr: np.ndarray,
    params: BlobParams,
    ctx: BlobDetectionContext,
) -> BlobResult:
    h, w = frame_bgr.shape[:2]
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY) if frame_bgr.ndim == 3 else frame_bgr
    thresh = cv2.inRange(
        gray,
        int(params.brightness_min),
        int(params.brightness_max),
    )
    binary = (thresh > 0) & ctx.arena_mask
    if ctx.open_kernel is not None:
        binary = cv2.morphologyEx(binary.astype(np.uint8), cv2.MORPH_OPEN, ctx.open_kernel) > 0
    if ctx.close_kernel is not None:
        binary = cv2.morphologyEx(binary.astype(np.uint8), cv2.MORPH_CLOSE, ctx.close_kernel) > 0
    fish = _largest_component(binary)
    return _blob_from_fish_mask(fish, h=h, w=w, params=params, clip_mask=ctx.arena_mask)
