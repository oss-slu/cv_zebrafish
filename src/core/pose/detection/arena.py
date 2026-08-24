"""Arena ROI (rectangle or circle) for dish videos — top-down assumption."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

import numpy as np

ArenaShape = Literal["square", "circle"]
_MIN_RECT_FRAC = 0.05
MAIN_ARENA_ID = "main"
ARENA_FRAC_SLIDER_SCALE = 10_000
ARENA_SIZE_SLIDER_MIN_FRAC = 0.1


@dataclass
class ArenaRegion:
    """Named sub-region (exclusion) with the same geometry fields as the main arena."""

    id: str
    name: str
    shape: ArenaShape = "circle"
    rect_x: float = 0.35
    rect_y: float = 0.35
    rect_w: float = 0.15
    rect_h: float = 0.15
    center_x: float = 0.5
    center_y: float = 0.5
    size: float = 0.15
    uses_rect: bool = False

    def clone(self) -> "ArenaRegion":
        return replace(self)

    def to_dict(self) -> dict:
        out: dict = {"id": self.id, "name": self.name, "shape": self.shape}
        if self.shape == "circle":
            out.update(
                {
                    "center_x": self.center_x,
                    "center_y": self.center_y,
                    "size": self.size,
                    "size_unit": "fraction_of_frame_min_edge",
                }
            )
        else:
            out.update(
                {
                    "rect_x": self.rect_x,
                    "rect_y": self.rect_y,
                    "rect_w": self.rect_w,
                    "rect_h": self.rect_h,
                }
            )
        return out

    @classmethod
    def from_dict(cls, raw: dict) -> "ArenaRegion":
        shape = raw.get("shape", "circle")
        if shape not in ("square", "circle"):
            shape = "circle"
        rid = str(raw.get("id") or uuid.uuid4().hex[:8])
        name = str(raw.get("name") or "Exclusion")
        if shape == "circle":
            return cls(
                id=rid,
                name=name,
                shape="circle",
                center_x=float(raw.get("center_x", 0.5)),
                center_y=float(raw.get("center_y", 0.5)),
                size=float(raw.get("size", 0.15)),
                uses_rect=False,
            )
        return cls(
            id=rid,
            name=name,
            shape="square",
            rect_x=float(raw.get("rect_x", 0.35)),
            rect_y=float(raw.get("rect_y", 0.35)),
            rect_w=float(raw.get("rect_w", 0.15)),
            rect_h=float(raw.get("rect_h", 0.15)),
            uses_rect=True,
        )

    def to_arena_config(self) -> "ArenaConfig":
        return ArenaConfig(
            shape=self.shape,
            rect_x=self.rect_x,
            rect_y=self.rect_y,
            rect_w=self.rect_w,
            rect_h=self.rect_h,
            center_x=self.center_x,
            center_y=self.center_y,
            size=self.size,
            uses_rect=self.uses_rect if self.shape == "square" else False,
            confirmed=True,
        )

    def apply_from_arena_config(self, cfg: "ArenaConfig") -> None:
        self.shape = cfg.shape
        if cfg.shape == "circle":
            self.center_x = cfg.center_x
            self.center_y = cfg.center_y
            self.size = cfg.size
            self.uses_rect = False
        else:
            self.rect_x = cfg.rect_x
            self.rect_y = cfg.rect_y
            self.rect_w = cfg.rect_w
            self.rect_h = cfg.rect_h
            self.uses_rect = True

    def clamp_rectangle(self) -> None:
        if self.shape != "square":
            return
        self.rect_w = max(_MIN_RECT_FRAC, min(1.0, self.rect_w))
        self.rect_h = max(_MIN_RECT_FRAC, min(1.0, self.rect_h))
        self.rect_x = max(0.0, min(1.0 - self.rect_w, self.rect_x))
        self.rect_y = max(0.0, min(1.0 - self.rect_h, self.rect_y))


def new_exclusion_name(existing: list[ArenaRegion]) -> str:
    used = {ex.name for ex in existing}
    n = len(existing) + 1
    while True:
        candidate = f"Exclusion {n}"
        if candidate not in used:
            return candidate
        n += 1


def make_default_exclusion(existing: list[ArenaRegion]) -> ArenaRegion:
    return ArenaRegion(
        id=uuid.uuid4().hex[:8],
        name=new_exclusion_name(existing),
        shape="circle",
        center_x=0.5,
        center_y=0.5,
        size=0.15,
        uses_rect=False,
    )


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
    exclude_mode: bool = False
    exclusions: list[ArenaRegion] = field(default_factory=list)

    def is_rectangle(self) -> bool:
        return self.shape == "square"

    def clone(self) -> "ArenaConfig":
        return replace(self)

    def to_dict(self) -> dict:
        out: dict = {
            "shape": self.shape,
            "confirmed": self.confirmed,
            "exclude_mode": self.exclude_mode,
        }
        if self.exclusions:
            out["exclusions"] = [ex.to_dict() for ex in self.exclusions]
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
        exclude_mode = bool(raw.get("exclude_mode", False))
        exclusions = [
            ArenaRegion.from_dict(item)
            for item in (raw.get("exclusions") or [])
            if isinstance(item, dict)
        ]
        if shape == "circle":
            return cls(
                shape="circle",
                center_x=float(raw.get("center_x", 0.5)),
                center_y=float(raw.get("center_y", 0.5)),
                size=float(raw.get("size", 0.5)),
                size_unit=str(raw.get("size_unit", "fraction_of_frame_min_edge")),
                uses_rect=False,
                confirmed=confirmed,
                exclude_mode=exclude_mode,
                exclusions=exclusions,
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
                exclude_mode=exclude_mode,
                exclusions=exclusions,
            )
        return cls(
            shape="square",
            center_x=float(raw.get("center_x", 0.5)),
            center_y=float(raw.get("center_y", 0.5)),
            size=float(raw.get("size", 1.0)),
            size_unit=str(raw.get("size_unit", "fraction_of_frame_min_edge")),
            uses_rect=False,
            confirmed=confirmed,
            exclude_mode=exclude_mode,
            exclusions=exclusions,
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


def circle_geometry_pixels(
    h: int, w: int, arena: ArenaConfig
) -> tuple[float, float, float]:
    """Circle center (cx, cy) and radius in pixels; not clipped to the frame."""
    min_edge = min(h, w)
    cx = arena.center_x * w
    cy = arena.center_y * h
    radius = arena.size * min_edge / 2.0
    return cx, cy, radius


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


def circle_center_bounds(
    size: float,
    frame_w: int = 0,
    frame_h: int = 0,
) -> tuple[float, float, float, float]:
    """Normalized bounds allowing half the circle diameter past each frame edge."""
    half_frac = max(0.05, float(size) / 2.0)
    if frame_w <= 0 or frame_h <= 0:
        return -half_frac, 1.0 + half_frac, -half_frac, 1.0 + half_frac
    min_edge = min(frame_h, frame_w)
    half_px = float(size) * min_edge / 2.0
    return (
        -half_px / frame_w,
        1.0 + half_px / frame_w,
        -half_px / frame_h,
        1.0 + half_px / frame_h,
    )


def clamp_circle_center(
    center_x: float,
    center_y: float,
    size: float,
    frame_w: int = 0,
    frame_h: int = 0,
) -> tuple[float, float]:
    min_x, max_x, min_y, max_y = circle_center_bounds(size, frame_w, frame_h)
    return (
        max(min_x, min(max_x, center_x)),
        max(min_y, min(max_y, center_y)),
    )


def _use_pixel_arena_sliders(frame_w: int, frame_h: int) -> bool:
    return frame_w > 0 and frame_h > 0


def arena_pos_to_slider(value: float, span: int) -> int:
    """Map a 0–1 (or off-screen) fraction to a slider value; span is frame width or height."""
    if span > 0:
        return int(round(value * span))
    return int(round(value * ARENA_FRAC_SLIDER_SCALE))


def arena_pos_from_slider(value: int, span: int) -> float:
    if span > 0:
        return value / span
    return value / ARENA_FRAC_SLIDER_SCALE


def arena_pos_slider_range(
    min_frac: float, max_frac: float, span: int
) -> tuple[int, int]:
    if span > 0:
        return int(round(min_frac * span)), int(round(max_frac * span))
    return (
        int(round(min_frac * ARENA_FRAC_SLIDER_SCALE)),
        int(round(max_frac * ARENA_FRAC_SLIDER_SCALE)),
    )


def rect_pos_slider_ranges(
    frame_w: int, frame_h: int
) -> tuple[tuple[int, int], tuple[int, int]]:
    if _use_pixel_arena_sliders(frame_w, frame_h):
        return (0, frame_w), (0, frame_h)
    span = ARENA_FRAC_SLIDER_SCALE
    return (0, span), (0, span)


def circle_size_to_slider(size: float, frame_w: int, frame_h: int) -> int:
    if _use_pixel_arena_sliders(frame_w, frame_h):
        return int(round(size * min(frame_h, frame_w)))
    return int(round(size * ARENA_FRAC_SLIDER_SCALE))


def circle_size_from_slider(value: int, frame_w: int, frame_h: int) -> float:
    if _use_pixel_arena_sliders(frame_w, frame_h):
        min_edge = min(frame_h, frame_w)
        return max(ARENA_SIZE_SLIDER_MIN_FRAC, value / min_edge)
    return max(ARENA_SIZE_SLIDER_MIN_FRAC, value / ARENA_FRAC_SLIDER_SCALE)


def circle_size_slider_range(frame_w: int, frame_h: int) -> tuple[int, int]:
    if _use_pixel_arena_sliders(frame_w, frame_h):
        min_edge = min(frame_h, frame_w)
        lo = max(1, int(round(ARENA_SIZE_SLIDER_MIN_FRAC * min_edge)))
        return lo, int(round(min_edge))
    lo = int(round(ARENA_SIZE_SLIDER_MIN_FRAC * ARENA_FRAC_SLIDER_SCALE))
    return lo, ARENA_FRAC_SLIDER_SCALE


def effective_arena_mask(h: int, w: int, arena: ArenaConfig) -> np.ndarray:
    """Main arena minus exclusion regions (for blob detection)."""
    mask = arena_mask(h, w, arena)
    if not arena.exclude_mode or not arena.exclusions:
        return mask
    for exclusion in arena.exclusions:
        mask &= ~arena_mask(h, w, exclusion.to_arena_config())
    return mask


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
