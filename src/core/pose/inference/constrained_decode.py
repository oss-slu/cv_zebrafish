"""Blob-masked, temporally windowed heatmap peak search."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from core.pose.labeling.schema import normalize_edge


@dataclass
class ConstrainedDecodeParams:
    """Tunable constrained-decode settings."""

    min_likelihood: float = 0.6
    bone_stretch_ratio: float = 2.0
    default_search_radius_px: float = 45.0


@dataclass
class DecodeFrameResult:
    """Per-bodypart decode output in crop pixel space."""

    positions: dict[str, tuple[float, float] | None] = field(default_factory=dict)
    likelihoods: dict[str, float] = field(default_factory=dict)
    flags: dict[str, list[str]] = field(default_factory=dict)


def _resize_mask(mask: np.ndarray, height: int, width: int) -> np.ndarray:
    if mask.shape[0] == height and mask.shape[1] == width:
        return mask.astype(bool)
    try:
        import cv2

        resized = cv2.resize(
            mask.astype(np.uint8),
            (width, height),
            interpolation=cv2.INTER_NEAREST,
        )
        return resized.astype(bool)
    except Exception:
        return np.ones((height, width), dtype=bool)


def circular_mask(
    height: int,
    width: int,
    center_x: float,
    center_y: float,
    radius_px: float,
) -> np.ndarray:
    """Boolean mask: True inside a circle (crop coordinates)."""
    if radius_px <= 0:
        return np.zeros((height, width), dtype=bool)
    yy, xx = np.ogrid[:height, :width]
    dist_sq = (xx - center_x) ** 2 + (yy - center_y) ** 2
    return dist_sq <= radius_px * radius_px


def build_search_mask(
    heatmap_h: int,
    heatmap_w: int,
    fish_mask: np.ndarray,
    prev_xy: tuple[float, float] | None,
    radius_px: float,
) -> np.ndarray:
    """
    Intersection of fish blob mask and temporal search disk.

    When ``prev_xy`` is None the temporal disk is omitted (seed frame).
    """
    blob = _resize_mask(fish_mask, heatmap_h, heatmap_w)
    if prev_xy is None:
        return blob
    temporal = circular_mask(heatmap_h, heatmap_w, prev_xy[0], prev_xy[1], radius_px)
    return blob & temporal


def peak_from_masked_heatmap(
    heatmap: np.ndarray,
    mask: np.ndarray,
) -> tuple[float, float, float] | None:
    """Argmax of heatmap inside mask; returns crop-space (x, y, score)."""
    if heatmap.size == 0 or not mask.any():
        return None
    if heatmap.shape != mask.shape:
        mask = _resize_mask(mask, heatmap.shape[0], heatmap.shape[1])
    masked = np.where(mask, heatmap, -np.inf)
    if not np.isfinite(masked).any():
        return None
    flat_idx = int(np.nanargmax(masked))
    y_idx, x_idx = np.unravel_index(flat_idx, heatmap.shape)
    score = float(heatmap[y_idx, x_idx])
    if not math.isfinite(score):
        return None
    return float(x_idx), float(y_idx), score


def heatmap_to_crop_coords(
    x_hm: float,
    y_hm: float,
    heatmap_h: int,
    heatmap_w: int,
    crop_h: int,
    crop_w: int,
) -> tuple[float, float]:
    """Scale heatmap indices to square-crop pixel coordinates."""
    if heatmap_w <= 0 or heatmap_h <= 0:
        return x_hm, y_hm
    return x_hm * crop_w / heatmap_w, y_hm * crop_h / heatmap_h


def decode_frame_constrained(
    heatmaps: dict[str, np.ndarray],
    fish_mask: np.ndarray,
    *,
    bodyparts: list[str],
    prev_positions_crop: dict[str, tuple[float, float] | None],
    search_radii: dict[str, float],
    params: ConstrainedDecodeParams,
    crop_side: int,
) -> DecodeFrameResult:
    """
    Pick heatmap peaks inside blob ∩ temporal disk for each bodypart.

    ``prev_positions_crop`` and outputs are in square-crop pixel space.
    """
    result = DecodeFrameResult()
    crop_h = crop_w = max(1, int(crop_side))
    for bp in bodyparts:
        hm = heatmaps.get(bp)
        if hm is None:
            result.positions[bp] = None
            result.flags[bp] = ["missing_heatmap"]
            continue
        hm = np.asarray(hm, dtype=np.float64)
        hm_h, hm_w = hm.shape[:2]
        radius = float(search_radii.get(bp, params.default_search_radius_px))
        # Scale radius from crop space to heatmap resolution.
        radius_hm = radius * hm_w / crop_w if crop_w > 0 else radius
        prev = prev_positions_crop.get(bp)
        mask = build_search_mask(hm_h, hm_w, fish_mask, prev, radius_hm)
        peak = peak_from_masked_heatmap(hm, mask)
        flags: list[str] = []
        if peak is None:
            result.positions[bp] = None
            result.flags[bp] = ["no_peak_in_mask"]
            continue
        x_hm, y_hm, score = peak
        x_crop, y_crop = heatmap_to_crop_coords(x_hm, y_hm, hm_h, hm_w, crop_h, crop_w)
        if score < params.min_likelihood:
            result.positions[bp] = None
            flags.append("below_likelihood")
        else:
            result.positions[bp] = (x_crop, y_crop)
        result.likelihoods[bp] = score
        if flags:
            result.flags[bp] = flags
    return result


def bone_stretch_violations(
    positions: dict[str, tuple[float, float] | None],
    bodyparts: list[str],
    edges: list[tuple[int, int]],
    reference_lengths: dict[tuple[str, str], float],
    *,
    max_ratio: float,
) -> list[str]:
    """Return human-readable violations when a bone exceeds ``max_ratio ×`` reference."""
    violations: list[str] = []
    for i, j in edges:
        edge = normalize_edge(i, j)
        if edge is None:
            continue
        a, b = bodyparts[edge[0]], bodyparts[edge[1]]
        ref = reference_lengths.get((a, b)) or reference_lengths.get((b, a))
        if ref is None or ref <= 0:
            continue
        pa, pb = positions.get(a), positions.get(b)
        if pa is None or pb is None:
            continue
        length = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        if length > ref * max_ratio:
            violations.append(f"{a}-{b} stretch {length:.0f}px > {max_ratio:.1f}×{ref:.0f}px")
    return violations
