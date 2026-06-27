"""
Low-resolution kinematic summaries: path length, speed, and active/rest bouts.

Active/rest detection uses per-frame displacement relative to the mean step size,
with absolute minimums so slow drift does not count as movement. Short rest gaps
can be merged into a single active bout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass
class ActiveRestParams:
    min_total_movement_m: float = 0.002
    min_frame_displacement_m: float = 0.00008
    movement_fraction_of_mean: float = 0.5
    min_rest_frames_to_split_bout: int = 12

    @classmethod
    def from_config(cls, cfg: Optional[Dict[str, Any]]) -> "ActiveRestParams":
        cfg = cfg or {}
        return cls(
            min_total_movement_m=float(cfg.get("min_total_movement_m", 0.002)),
            min_frame_displacement_m=float(cfg.get("min_frame_displacement_m", 0.00008)),
            movement_fraction_of_mean=float(cfg.get("movement_fraction_of_mean", 0.5)),
            min_rest_frames_to_split_bout=int(cfg.get("min_rest_frames_to_split_bout", 12)),
        )


@dataclass
class LowResSummary:
    track_point_distance_speed: str = ""
    track_point_active_rest: str = ""
    distance_covered_m: float = 0.0
    mean_speed_m_s: float = 0.0
    peak_speed_m_s: float = 0.0
    duration_s: float = 0.0
    active_bout_count: int = 0
    active_frames: int = 0
    rest_frames: int = 0
    active_time_s: float = 0.0
    rest_time_s: float = 0.0
    active_bouts: List[List[int]] = field(default_factory=list)
    active_rest_states: Optional[np.ndarray] = None
    time_axis: Optional[np.ndarray] = None
    instantaneous_speed_m_s: Optional[np.ndarray] = None


def list_trackable_point_labels(config: Dict[str, Any]) -> List[str]:
    """Return ordered unique bodypart labels assigned in the config points block."""
    pts = (config or {}).get("points") or {}
    labels: List[str] = []
    seen: set[str] = set()

    def _add(val: str) -> None:
        v = str(val or "").strip()
        if v and v not in seen:
            seen.add(v)
            labels.append(v)

    for p in pts.get("spine") or []:
        _add(p)
    for p in pts.get("tail") or []:
        _add(p)
    for p in pts.get("right_fin") or []:
        _add(p)
    for p in pts.get("left_fin") or []:
        _add(p)
    head = pts.get("head") or {}
    if isinstance(head, dict):
        _add(head.get("pt1", ""))
        _add(head.get("pt2", ""))
    return labels


def resolve_point_coords(
    parsed_points: Dict[str, Any],
    config: Dict[str, Any],
    label: str,
) -> Optional[Dict[str, np.ndarray]]:
    """Map a DLC bodypart label to parsed x/y/conf arrays."""
    label = str(label or "").strip()
    if not label or not parsed_points:
        return None

    pts = (config or {}).get("points") or {}

    spine_labels = [str(p) for p in (pts.get("spine") or [])]
    for i, lbl in enumerate(spine_labels):
        if lbl == label:
            spine = parsed_points.get("spine") or []
            if i < len(spine):
                return spine[i]

    tail_labels = [str(p) for p in (pts.get("tail") or [])]
    for i, lbl in enumerate(tail_labels):
        if lbl == label:
            tail = parsed_points.get("tail") or []
            if i < len(tail):
                return tail[i]

    for fin_key, fin_labels in (
        ("right_fin", pts.get("right_fin") or []),
        ("left_fin", pts.get("left_fin") or []),
    ):
        fin_pts = parsed_points.get(fin_key) or []
        for i, lbl in enumerate([str(p) for p in fin_labels]):
            if lbl == label and i < len(fin_pts):
                return fin_pts[i]

    head = pts.get("head") or {}
    if isinstance(head, dict):
        if label == str(head.get("pt1", "")):
            return parsed_points.get("clp1")
        if label == str(head.get("pt2", "")):
            return parsed_points.get("clp2")

    if label == spine_labels[0] if spine_labels else False:
        return parsed_points.get("head")
    if spine_labels and label == spine_labels[-1]:
        return parsed_points.get("tp")

    return None


def scale_factor_from_config(config: Dict[str, Any]) -> float:
    vp = (config or {}).get("video_parameters") or {}
    return float(vp.get("pixel_scale_factor", 1.0)) * float(vp.get("dish_diameter_m", 1.0)) / max(
        float(vp.get("pixel_diameter", 1.0)), 1e-9
    )


def framerate_from_config(config: Dict[str, Any]) -> float:
    vp = (config or {}).get("video_parameters") or {}
    return max(float(vp.get("recorded_framerate", 1.0)), 1e-9)


def per_frame_displacement_m(
    x: Sequence[float],
    y: Sequence[float],
    scale_factor: float,
) -> np.ndarray:
    """Frame-to-frame Euclidean step in metres; index 0 is always 0."""
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    n = len(x_arr)
    steps = np.zeros(n, dtype=float)
    if n < 2:
        return steps
    dx = np.diff(x_arr) * scale_factor
    dy = np.diff(y_arr) * scale_factor
    steps[1:] = np.sqrt(dx * dx + dy * dy)
    return steps


def total_path_length_m(steps: np.ndarray) -> float:
    return float(np.nansum(steps[1:]))


def speed_stats_from_steps(steps: np.ndarray, framerate: float) -> Tuple[float, float]:
    """Return (mean_speed_m_s, peak_instantaneous_speed_m_s)."""
    inst = steps[1:] * framerate
    if inst.size == 0:
        return 0.0, 0.0
    valid = inst[np.isfinite(inst)]
    if valid.size == 0:
        return 0.0, 0.0
    mean_speed = float(np.nanmean(valid))
    peak_speed = float(np.nanmax(valid))
    return mean_speed, peak_speed


def classify_active_rest_frames(
    steps: np.ndarray,
    params: ActiveRestParams,
) -> Tuple[np.ndarray, List[List[int]]]:
    """
    Label each frame active (1) or rest (0) and return contiguous active bout ranges.

    A frame counts as moving when its displacement exceeds both an absolute floor and
    a fraction of the mean step size. Total path length must exceed min_total_movement_m
    or every frame is labelled rest.
    """
    n = len(steps)
    states = np.zeros(n, dtype=int)
    if n < 2:
        return states, []

    total_dist = total_path_length_m(steps)
    if total_dist < params.min_total_movement_m:
        return states, []

    mean_step = total_dist / max(1, n - 1)
    threshold = max(
        params.min_frame_displacement_m,
        params.movement_fraction_of_mean * mean_step,
    )

    raw_active = steps >= threshold
    raw_active[0] = False

    merged = _merge_short_rest_gaps(raw_active, params.min_rest_frames_to_split_bout)
    states = merged.astype(int)
    return states, _contiguous_ranges(states, active_value=1)


def _merge_short_rest_gaps(active: np.ndarray, min_rest_frames: int) -> np.ndarray:
    if min_rest_frames <= 0:
        return active.copy()
    out = active.copy()
    n = len(out)
    i = 0
    while i < n:
        if out[i]:
            i += 1
            continue
        gap_start = i
        while i < n and not out[i]:
            i += 1
        gap_len = i - gap_start
        if gap_start > 0 and i < n and gap_len < min_rest_frames:
            out[gap_start:i] = True
    return out


def _contiguous_ranges(states: np.ndarray, active_value: int = 1) -> List[List[int]]:
    ranges: List[List[int]] = []
    in_range = False
    start = 0
    for i, val in enumerate(states):
        if val == active_value and not in_range:
            start = i
            in_range = True
        elif val != active_value and in_range:
            ranges.append([start, i - 1])
            in_range = False
    if in_range:
        ranges.append([start, len(states) - 1])
    return ranges


def compute_low_res_summary(
    parsed_points: Dict[str, Any],
    config: Dict[str, Any],
    *,
    active_rest_params: Optional[ActiveRestParams] = None,
    n_frames: Optional[int] = None,
) -> LowResSummary:
    """Compute distance, speed, and active/rest bout metrics for the configured track points."""
    lr_cfg = (config or {}).get("low_res_analysis") or {}
    scale = scale_factor_from_config(config)
    fps = framerate_from_config(config)

    dist_label = str(lr_cfg.get("track_point_distance_speed") or "").strip()
    ar_cfg = lr_cfg.get("active_rest") or {}
    ar_label = str(ar_cfg.get("track_point") or dist_label).strip()
    params = active_rest_params or ActiveRestParams.from_config(ar_cfg)

    summary = LowResSummary(
        track_point_distance_speed=dist_label,
        track_point_active_rest=ar_label,
    )

    if n_frames is None:
        spine = parsed_points.get("spine") or []
        n_frames = len(spine[0]["x"]) if spine else 0
    summary.duration_s = n_frames / fps
    summary.time_axis = np.arange(n_frames, dtype=float) / fps

    dist_pt = resolve_point_coords(parsed_points, config, dist_label) if dist_label else None
    if dist_pt is not None:
        steps = per_frame_displacement_m(dist_pt["x"], dist_pt["y"], scale)
        summary.distance_covered_m = total_path_length_m(steps)
        summary.mean_speed_m_s, summary.peak_speed_m_s = speed_stats_from_steps(steps, fps)
        summary.instantaneous_speed_m_s = steps * fps

    ar_pt = resolve_point_coords(parsed_points, config, ar_label) if ar_label else None
    if ar_pt is not None:
        ar_steps = per_frame_displacement_m(ar_pt["x"], ar_pt["y"], scale)
        states, bouts = classify_active_rest_frames(ar_steps, params)
        summary.active_rest_states = states
        summary.active_bouts = bouts
        summary.active_bout_count = len(bouts)
        summary.active_frames = int(np.sum(states))
        summary.rest_frames = int(n_frames - summary.active_frames)
        summary.active_time_s = summary.active_frames / fps
        summary.rest_time_s = summary.rest_frames / fps

    return summary


def enrich_results_dataframe(
    parsed_points: Dict[str, Any],
    result_df: pd.DataFrame,
    config: Dict[str, Any],
) -> pd.DataFrame:
    """Append low-res columns and attach a summary object on the DataFrame attrs."""
    lr_cfg = (config or {}).get("low_res_analysis") or {}
    if not lr_cfg:
        return result_df
    if not lr_cfg.get("enabled", True):
        return result_df
    dist_label = str(lr_cfg.get("track_point_distance_speed") or "").strip()
    ar_label = str((lr_cfg.get("active_rest") or {}).get("track_point") or dist_label).strip()
    if not dist_label and not ar_label:
        return result_df

    summary = compute_low_res_summary(parsed_points, config)
    out = result_df.copy()

    if summary.active_rest_states is not None and len(summary.active_rest_states) == len(out):
        out["ActiveRest_State"] = summary.active_rest_states

    if summary.instantaneous_speed_m_s is not None and len(summary.instantaneous_speed_m_s) == len(out):
        out["LowRes_InstantSpeed_m_s"] = summary.instantaneous_speed_m_s

    out.attrs["low_res_summary"] = summary
    return out


__all__ = [
    "ActiveRestParams",
    "LowResSummary",
    "classify_active_rest_frames",
    "compute_low_res_summary",
    "enrich_results_dataframe",
    "framerate_from_config",
    "list_trackable_point_labels",
    "per_frame_displacement_m",
    "resolve_point_coords",
    "scale_factor_from_config",
    "speed_stats_from_steps",
    "total_path_length_m",
]
