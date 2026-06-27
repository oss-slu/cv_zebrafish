"""Arena ROI (rectangle or circle) for dish videos — top-down assumption."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import numpy as np

ArenaShape = Literal["square", "circle"]
_MIN_RECT_FRAC = 0.05


@dataclass
class ArenaConfig:
    shape: ArenaShape = "square"
    # Rectangle bounds as fractions of frame width (x, w) and height (y, h).
    rect_x: float = 0.0
    rect_y: float = 0.0
    rect_w: float = 1.0
    rect_h: float = 1.0
    # Circle-only (and legacy square before rect_* was saved).
    center_x: float = 0.5
    center_y: float = 0.5
    size: float = 1.0
    size_unit: str = "fraction_of_frame_min_edge"
    uses_rect: bool = True
    confirmed: bool = False

    def is_rectangle(self) -> bool:
        return self.shape == "square"

    def clone(self) -> "ArenaConfig":
        return replace(self)

    def to_dict(self) -> dict:
        out: dict = {
            "shape": self.shape,
            "confirmed": self.confirmed,
        }
        if self.is_rectangle():
            out.update(
                {
                    "rect_x": self.rect_x,
                    "rect_y": self.rect_y,
                    "rect_w": self.rect_w,
                    "rect_h": self.rect_h,
                }
            )
        else:
            out.update(
                {
                    "center_x": self.center_x,
                    "center_y": self.center_y,
                    "size": self.size,
                    "size_unit": self.size_unit,
                }
            )
        return out

    @classmethod
    def from_dict(cls, raw: dict | None) -> "ArenaConfig":
        if not raw:
            return cls(confirmed=False)
        shape = raw.get("shape", "square")
        if shape not in ("square", "circle"):
            shape = "square"
        confirmed = bool(raw.get("confirmed", True))
        if shape == "circle":
            return cls(
                shape="circle",
                center_x=float(raw.get("center_x", 0.5)),
                center_y=float(raw.get("center_y", 0.5)),
                size=float(raw.get("size", 0.5)),
                size_unit=str(raw.get("size_unit", "fraction_of_frame_min_edge")),
                uses_rect=False,
                confirmed=confirmed,
            )
        if "rect_w" in raw:
            return cls(
                shape="square",
                rect_x=float(raw.get("rect_x", 0.0)),
                rect_y=float(raw.get("rect_y", 0.0)),
                rect_w=float(raw.get("rect_w", 1.0)),
                rect_h=float(raw.get("rect_h", 1.0)),
                uses_rect=True,
                confirmed=confirmed,
            )
        return cls(
            shape="square",
            center_x=float(raw.get("center_x", 0.5)),
            center_y=float(raw.get("center_y", 0.5)),
            size=float(raw.get("size", 1.0)),
            size_unit=str(raw.get("size_unit", "fraction_of_frame_min_edge")),
            uses_rect=False,
            confirmed=confirmed,
        )

    def ensure_explicit_rect(self, frame_w: int, frame_h: int) -> None:
        """Convert legacy center+size square arenas to rect_x/y/w/h once frame size is known."""
        if not self.is_rectangle() or self.uses_rect:
            return
        x0, y0, x1, y1 = _legacy_square_pixels(frame_h, frame_w, self)
        if frame_w <= 0 or frame_h <= 0:
            return
        self.rect_x = x0 / frame_w
        self.rect_y = y0 / frame_h
        self.rect_w = max(_MIN_RECT_FRAC, (x1 - x0) / frame_w)
        self.rect_h = max(_MIN_RECT_FRAC, (y1 - y0) / frame_h)
        self.uses_rect = True

    def clamp_rectangle(self) -> None:
        if not self.is_rectangle():
            return
        self.rect_w = max(_MIN_RECT_FRAC, min(1.0, self.rect_w))
        self.rect_h = max(_MIN_RECT_FRAC, min(1.0, self.rect_h))
        self.rect_x = max(0.0, min(1.0 - self.rect_w, self.rect_x))
        self.rect_y = max(0.0, min(1.0 - self.rect_h, self.rect_y))


def load_arena(path: Path) -> ArenaConfig:
    if not path.is_file():
        return ArenaConfig(confirmed=False)
    return ArenaConfig.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_arena(path: Path, arena: ArenaConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    arena.clamp_rectangle()
    path.write_text(json.dumps(arena.to_dict(), indent=2), encoding="utf-8")


def _legacy_square_pixels(h: int, w: int, arena: ArenaConfig) -> tuple[int, int, int, int]:
    min_edge = min(h, w)
    cx = arena.center_x * w
    cy = arena.center_y * h
    half = arena.size * min_edge / 2.0
    x0 = int(round(cx - half))
    y0 = int(round(cy - half))
    x1 = int(round(cx + half))
    y1 = int(round(cy + half))
    return clip_rect_to_image(x0, y0, x1, y1, w, h)


def _circle_pixels(h: int, w: int, arena: ArenaConfig) -> tuple[int, int, int, int]:
    min_edge = min(h, w)
    cx = arena.center_x * w
    cy = arena.center_y * h
    half = arena.size * min_edge / 2.0
    x0 = int(round(cx - half))
    y0 = int(round(cy - half))
    x1 = int(round(cx + half))
    y1 = int(round(cy + half))
    return clip_rect_to_image(x0, y0, x1, y1, w, h)


def arena_rect_pixels(h: int, w: int, arena: ArenaConfig) -> tuple[int, int, int, int]:
    """Inclusive-exclusive pixel bounds (x0, y0, x1, y1) clipped to the frame."""
    if arena.shape == "circle":
        return _circle_pixels(h, w, arena)
    if arena.uses_rect:
        x0 = int(round(arena.rect_x * w))
        y0 = int(round(arena.rect_y * h))
        x1 = int(round((arena.rect_x + arena.rect_w) * w))
        y1 = int(round((arena.rect_y + arena.rect_h) * h))
        return clip_rect_to_image(x0, y0, x1, y1, w, h)
    return _legacy_square_pixels(h, w, arena)


def arena_mask(h: int, w: int, arena: ArenaConfig) -> np.ndarray:
    """Boolean mask (H, W) True inside arena."""
    yy, xx = np.ogrid[:h, :w]
    if arena.shape == "circle":
        min_edge = min(h, w)
        cx = arena.center_x * w
        cy = arena.center_y * h
        half = arena.size * min_edge / 2.0
        dist_sq = (xx - cx) ** 2 + (yy - cy) ** 2
        return dist_sq <= half**2
    x0, y0, x1, y1 = arena_rect_pixels(h, w, arena)
    return (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)


def clip_rect_to_image(x0: int, y0: int, x1: int, y1: int, w: int, h: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(w, x0))
    y0 = max(0, min(h, y0))
    x1 = max(0, min(w, x1))
    y1 = max(0, min(h, y1))
    if x1 <= x0:
        x1 = min(w, x0 + 1)
    if y1 <= y0:
        y1 = min(h, y0 + 1)
    return x0, y0, x1, y1
