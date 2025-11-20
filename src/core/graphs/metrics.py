"""
Pure helpers extracted from the legacy plotting module.

The goal is to keep these functions free of I/O or plotting concerns so they are
easy to unit test.
"""

from __future__ import annotations

import numpy as np
from typing import Iterable, List, Sequence, Tuple


def check_confidence(spine: Sequence[Sequence[dict]], row: int, min_conf: float, max_broken_points: int) -> bool:
    """Return True if a spine frame has acceptable confidence."""
    broken_points = sum(1 for pt in spine if pt[row]["conf"] < min_conf)
    return broken_points <= max_broken_points


def get_frequency_and_peak_num(cutoff: float, values: Sequence[float], time_ranges: Iterable[Tuple[int, int]], time_factor: float, tail: bool = False) -> Tuple[float, int]:
    """
    Compute frequency (events per second) and peak count for the provided values inside time_ranges.
    Matches the legacy logic: peaks are counted when crossing the cutoff.
    """
    peak_distances: List[int] = []
    on_peak = False
    peaks: List[int] = []

    if tail:
        for start, end in time_ranges:
            for i in range(start, end + 1):
                if (not on_peak) and (values[i] > cutoff or values[i] < -cutoff):
                    on_peak = True
                elif on_peak and (-cutoff <= values[i] <= cutoff):
                    peaks.append(i)
                    on_peak = False
        if len(peaks) > 1:
            peak_distances.extend(peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1))
        freq = 0
        if peak_distances:
            freq = 1 / (np.mean(peak_distances) / time_factor / 2)
        return freq, int(len(peaks) / 2)

    for start, end in time_ranges:
        for i in range(start, end + 1):
            if (not on_peak) and values[i] > cutoff:
                on_peak = True
            elif on_peak and values[i] <= cutoff:
                peaks.append(i)
                on_peak = False
    if len(peaks) > 1:
        peak_distances.extend(peaks[i + 1] - peaks[i] for i in range(len(peaks) - 1))
    freq = 0
    if peak_distances:
        freq = 1 / (np.mean(peak_distances) / time_factor)
    return freq, len(peaks)


def rotate_around_origin(x: float, y: float, origin_x: float, origin_y: float, head_angle: float, in_rads: bool = True) -> Tuple[float, float]:
    """Rotate a point about an origin by head_angle, mirroring the legacy convention."""
    angle_rad = (np.pi / 2 - head_angle + np.pi) if in_rads else np.deg2rad(head_angle)
    x_shifted = x - origin_x
    y_shifted = y - origin_y
    x_rotated = x_shifted * np.cos(angle_rad) - y_shifted * np.sin(angle_rad)
    y_rotated = x_shifted * np.sin(angle_rad) + y_shifted * np.cos(angle_rad)
    return x_rotated + origin_x, y_rotated + origin_y


def flip_across_origin_x(x: float, origin_x: float) -> float:
    """Mirror a point across the vertical axis at origin_x."""
    return origin_x + (origin_x - x)


def get_peaks(values: Sequence[float], cutoff: float, total_range: int, negative_cutoff: bool = False) -> List[int]:
    """
    Detect peaks crossing the cutoff within a range.
    Returns indices of peak maxima (or minima if negative_cutoff).
    """
    peaks: List[int] = []
    on_peak = False
    current_peak_pos = 0
    current_peak_extreme = 0.0

    if negative_cutoff:
        for i in range(total_range):
            if (not on_peak) and values[i] < cutoff:
                current_peak_pos = i
                current_peak_extreme = values[i]
                on_peak = True
            elif on_peak and values[i] >= cutoff:
                peaks.append(current_peak_pos)
                on_peak = False
            elif on_peak:
                new_min = min(current_peak_extreme, values[i])
                if new_min < current_peak_extreme:
                    current_peak_extreme = new_min
                    current_peak_pos = i
    else:
        for i in range(total_range):
            if (not on_peak) and values[i] > cutoff:
                current_peak_pos = i
                current_peak_extreme = values[i]
                on_peak = True
            elif on_peak and values[i] <= cutoff:
                peaks.append(current_peak_pos)
                on_peak = False
            elif on_peak:
                new_max = max(current_peak_extreme, values[i])
                if new_max > current_peak_extreme:
                    current_peak_extreme = new_max
                    current_peak_pos = i
    if on_peak:
        peaks.append(total_range - 1)
    return peaks


def get_time_ranges(
    left_fin_angles: Sequence[float],
    right_fin_angles: Sequence[float],
    tail_distances: Sequence[float],
    lf_cutoff: float,
    rf_cutoff: float,
    tail_cutoff: float,
    mov_bout_cutoff: int,
    total_range: int,
    swim_bout_buffer: int,
    swim_bout_right_shift: int,
    use_tail_angle: bool,
) -> List[List[int]]:
    """
    Derive time ranges from fin/tail peaks using the legacy heuristic.
    """
    on_range = False
    time_ranges: List[List[int]] = []
    new_range_start = 0

    tail_pos_peaks = get_peaks(tail_distances, tail_cutoff, total_range)
    tail_neg_peaks = get_peaks(tail_distances, tail_cutoff, total_range, negative_cutoff=True)

    lf_peaks = get_peaks(left_fin_angles, lf_cutoff, total_range)
    rf_peaks = get_peaks(right_fin_angles, rf_cutoff, total_range)
    tail_all_peaks = sorted(tail_pos_peaks + tail_neg_peaks)

    last_lf_peak = last_rf_peak = last_tail_peak = -mov_bout_cutoff * 2

    if use_tail_angle:
        for i in range(total_range):
            if i in lf_peaks:
                last_lf_peak = i
            if i in rf_peaks:
                last_rf_peak = i
            if i in tail_all_peaks:
                last_tail_peak = i
            if not on_range and (i - last_lf_peak <= mov_bout_cutoff and i - last_rf_peak <= mov_bout_cutoff and i - last_tail_peak <= mov_bout_cutoff):
                new_range_start = max(min(min(last_lf_peak, last_rf_peak), last_tail_peak) - swim_bout_buffer + swim_bout_right_shift, 0)
                on_range = True
            elif on_range and (i - last_lf_peak > mov_bout_cutoff or i - last_rf_peak > mov_bout_cutoff or i - last_tail_peak > mov_bout_cutoff):
                new_range_end = min(max(max(last_lf_peak, last_rf_peak), last_tail_peak) + swim_bout_buffer + swim_bout_right_shift, total_range)
                time_ranges.append([new_range_start, new_range_end])
                on_range = False
    else:
        for i in range(total_range):
            if i in lf_peaks:
                last_lf_peak = i
            if i in rf_peaks:
                last_rf_peak = i
            if i in tail_all_peaks:
                last_tail_peak = i
            if not on_range and (i - last_lf_peak <= mov_bout_cutoff and i - last_rf_peak <= mov_bout_cutoff):
                new_range_start = max(min(last_lf_peak, last_rf_peak) - swim_bout_buffer + swim_bout_right_shift, 0)
                on_range = True
            elif on_range and (i - last_lf_peak > mov_bout_cutoff or i - last_rf_peak > mov_bout_cutoff):
                new_range_end = min(max(last_lf_peak, last_rf_peak) + swim_bout_buffer + swim_bout_right_shift, total_range - 1)
                time_ranges.append([new_range_start, new_range_end])
                on_range = False

    return time_ranges


def total_distance(head_x: Sequence[float], head_y: Sequence[float], time_ranges: Iterable[Tuple[int, int]]) -> List[float]:
    """Compute straight-line distance traveled per time range."""
    distances: List[float] = []
    for start_idx, end_idx in time_ranges:
        dist_x = head_x[end_idx] - head_x[start_idx]
        dist_y = head_y[end_idx] - head_y[start_idx]
        distances.append(float(np.sqrt(dist_x ** 2 + dist_y ** 2)))
    return distances


def total_speed(head_x: Sequence[float], head_y: Sequence[float], time_ranges: Iterable[Tuple[int, int]], framerate: float) -> List[float]:
    """Compute average speed (distance / framerate) for each time range."""
    speeds: List[float] = []
    for start_idx, end_idx in time_ranges:
        dist_x = head_x[end_idx] - head_x[start_idx]
        dist_y = head_y[end_idx] - head_y[start_idx]
        speeds.append(float(np.sqrt(dist_x ** 2 + dist_y ** 2) / framerate))
    return speeds


__all__ = [
    "check_confidence",
    "get_frequency_and_peak_num",
    "rotate_around_origin",
    "flip_across_origin_x",
    "get_peaks",
    "get_time_ranges",
    "total_distance",
    "total_speed",
]
