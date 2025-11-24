"""
Spine snapshot plotter.

Reimplements the legacy `plotSpines` selection/drawing logic with clearer
selection modes, confidence handling, and IO hooks.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from ..io import OutputContext
from ..loader_bundle import GraphDataBundle
from ..metrics import flip_across_origin_x, get_peaks, rotate_around_origin


PALETTE = [
    (1.0, 0.0, 0.0),
    (1.0, 1.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 1.0, 1.0),
    (0.0, 0.0, 1.0),
    (1.0, 0.0, 1.0),
]


@dataclass(frozen=True)
class SpineFrameDiagnostics:
    """Per-frame debugging info."""

    frame_index: int
    max_gap: int
    end_gap: int
    repaired_points: int
    skipped: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class SpinePlotResult:
    """Metadata returned after rendering spine plots."""

    figures: List[go.Figure]
    mode: str
    frames_by_bout: List[List[int]]
    warnings: List[str]
    output_paths: List[Dict[str, str]]
    diagnostics: List[SpineFrameDiagnostics]


def _extract_frame(spine: Sequence[Dict[str, Sequence[float]]], frame_idx: int) -> List[Dict[str, float]]:
    """Convert the columnar spine arrays into a per-frame list of dicts."""
    frame: List[Dict[str, float]] = []
    for pt in spine:
        try:
            x = float(pt["x"][frame_idx])
            y = float(pt["y"][frame_idx])
            conf_arr = pt.get("conf", [])
            conf = float(conf_arr[frame_idx]) if conf_arr is not None else 1.0
        except Exception:
            return []
        frame.append({"x": x, "y": y, "conf": conf})
    return frame


def _gap_stats(points: Sequence[Dict[str, float]], threshold: float) -> Tuple[int, int]:
    """Return (max_gap, end_gap) of consecutive points under the threshold."""
    max_gap = 0
    current = 0
    for pt in points:
        if pt["conf"] < threshold:
            current += 1
        else:
            max_gap = max(max_gap, current)
            current = 0
    max_gap = max(max_gap, current)
    end_gap = current
    return max_gap, end_gap


def _repair_spine_frame(
    points: List[Dict[str, float]],
    replace_threshold: float,
    min_conf: float,
    max_run: int,
) -> Tuple[Optional[List[Dict[str, float]]], int, Optional[str]]:
    """
    Attempt to repair low-confidence points by interpolating between nearest valid neighbors.
    Endpoints fall back to the closest valid neighbor.
    """
    if not points:
        return None, 0, "no points found"

    reliable = [pt["conf"] >= replace_threshold for pt in points]
    repaired_points = 0

    if all(reliable):
        return points, repaired_points, None

    if not any(reliable):
        return None, repaired_points, "no reliable points to repair from"

    idx = 0
    total = len(points)
    while idx < total:
        if reliable[idx]:
            idx += 1
            continue

        run_start = idx
        while idx < total and not reliable[idx]:
            idx += 1
        run_end = idx - 1
        run_length = run_end - run_start + 1

        if run_length > max_run:
            return None, repaired_points, f"gap of {run_length} exceeds max repairable run {max_run}"

        left_idx = run_start - 1 if run_start - 1 >= 0 else None
        right_idx = idx if idx < total else None

        left_pt = points[left_idx] if left_idx is not None and reliable[left_idx] else None
        right_pt = points[right_idx] if right_idx is not None and reliable[right_idx] else None

        if not left_pt and not right_pt:
            return None, repaired_points, "unable to interpolate gap without neighbors"

        for gap_offset, gap_idx in enumerate(range(run_start, idx)):
            if left_pt and right_pt:
                ratio = (gap_offset + 1) / (run_length + 1)
                x = left_pt["x"] + (right_pt["x"] - left_pt["x"]) * ratio
                y = left_pt["y"] + (right_pt["y"] - left_pt["y"]) * ratio
            elif left_pt:
                x, y = left_pt["x"], left_pt["y"]
            else:
                x, y = right_pt["x"], right_pt["y"]
            points[gap_idx]["x"] = x
            points[gap_idx]["y"] = y
            points[gap_idx]["conf"] = max(replace_threshold, min_conf)
            repaired_points += 1

    return points, repaired_points, None


def _filter_and_repair_frame(
    spine: Sequence[Dict[str, Sequence[float]]],
    frame_idx: int,
    min_conf: float,
    max_broken_points: int,
    replace_threshold: Optional[float],
    max_run: int,
) -> Tuple[Optional[List[Dict[str, float]]], SpineFrameDiagnostics]:
    """Apply confidence rules to a frame; return repaired points or skip with diagnostics."""
    pts = _extract_frame(spine, frame_idx)
    default_diag = SpineFrameDiagnostics(
        frame_index=frame_idx, max_gap=0, end_gap=0, repaired_points=0, skipped=True, reason="missing frame data"
    )
    if not pts:
        return None, default_diag

    threshold = replace_threshold if replace_threshold is not None else min_conf
    max_gap, end_gap = _gap_stats(pts, threshold)
    broken = sum(1 for pt in pts if pt["conf"] < min_conf)

    if broken > max_broken_points and replace_threshold is None:
        return None, SpineFrameDiagnostics(
            frame_index=frame_idx,
            max_gap=max_gap,
            end_gap=end_gap,
            repaired_points=0,
            skipped=True,
            reason=f"{broken} points below confidence {min_conf}",
        )

    repaired_points = 0
    if replace_threshold is not None:
        repaired_pts, repaired_points, reason = _repair_spine_frame(
            pts, replace_threshold, min_conf, max_run=max(1, max_run)
        )
        if repaired_pts is None:
            return None, SpineFrameDiagnostics(
                frame_index=frame_idx,
                max_gap=max_gap,
                end_gap=end_gap,
                repaired_points=repaired_points,
                skipped=True,
                reason=reason,
            )
        pts = repaired_pts

    broken_after = sum(1 for pt in pts if pt["conf"] < min_conf)
    if broken_after > max_broken_points:
        return None, SpineFrameDiagnostics(
            frame_index=frame_idx,
            max_gap=max_gap,
            end_gap=end_gap,
            repaired_points=repaired_points,
            skipped=True,
            reason=f"{broken_after} points below confidence {min_conf} after repair",
        )

    return pts, SpineFrameDiagnostics(
        frame_index=frame_idx,
        max_gap=max_gap,
        end_gap=end_gap,
        repaired_points=repaired_points,
        skipped=False,
        reason=None,
    )


def _select_frames_by_bout(time_ranges: Sequence[Tuple[int, int]], spines_per_bout: int) -> List[List[int]]:
    """Evenly space N frames across each bout range."""
    selections: List[List[int]] = []
    for start, end in time_ranges:
        if spines_per_bout <= 0:
            selections.append([])
            continue
        if spines_per_bout == 1 or start == end:
            selections.append([int(start)])
            continue
        frames = []
        span = end - start
        for i in range(spines_per_bout):
            frame_val = int(round(start + span * (i / float(spines_per_bout - 1))))
            frames.append(frame_val)
        selections.append(sorted(set(frames)))
    return selections


def _select_frames_by_parallel(
    left_fin: Sequence[float],
    right_fin: Sequence[float],
    time_ranges: Sequence[Tuple[int, int]],
    error_range: float,
) -> List[List[int]]:
    """
    Identify frames where both fins are near parallel (close to 90 degrees).
    Mirrors the legacy heuristic of picking the closest approach per run.
    """
    selections: List[List[int]] = []
    for start, end in time_ranges:
        current: List[int] = []
        on_peak = False
        closest_idx = None
        closest_dist = 0.0

        for idx in range(start, end + 1):
            left_dist = abs(left_fin[idx] - 90)
            right_dist = abs(right_fin[idx] - 90)
            if left_dist < error_range and right_dist < error_range:
                if on_peak:
                    if left_dist + right_dist < closest_dist:
                        closest_idx = idx
                        closest_dist = left_dist + right_dist
                else:
                    on_peak = True
                    closest_idx = idx
                    closest_dist = left_dist + right_dist
            elif on_peak and closest_idx is not None:
                current.append(closest_idx)
                on_peak = False
                closest_idx = None

        if on_peak and closest_idx is not None:
            current.append(closest_idx)
        selections.append(sorted(set(current)))
    return selections


def _select_frames_by_peaks(
    fin_values: Sequence[float],
    opposing_fin: Sequence[float],
    time_ranges: Sequence[Tuple[int, int]],
    cutoff: Optional[float],
    opposing_cutoff: Optional[float],
    ignore_synchronized: bool,
    sync_range: int,
) -> List[List[int]]:
    """Pick frames at fin peaks, optionally removing synchronized opposing peaks."""
    if cutoff is None:
        return [[] for _ in time_ranges]

    peaks = get_peaks(fin_values, cutoff, len(fin_values))
    selections: List[List[int]] = []
    for start, end in time_ranges:
        bout_peaks = []
        for peak_idx in peaks:
            if peak_idx < start or peak_idx > end:
                continue
            if ignore_synchronized and opposing_cutoff is not None:
                win_start = max(0, peak_idx - sync_range)
                win_end = min(len(opposing_fin) - 1, peak_idx + sync_range)
                if any(opposing_fin[i] > opposing_cutoff for i in range(win_start, win_end + 1)):
                    continue
            bout_peaks.append(peak_idx)
        selections.append(sorted(set(bout_peaks)))
    return selections


def _apply_frame_budget(
    frames_by_mode: Dict[str, List[int]],
    budget: int,
    priority: Sequence[str],
) -> Tuple[List[int], bool]:
    """Union frames using the provided priority order and enforce a budget."""
    chosen: List[int] = []
    seen = set()
    total_unique = len(set().union(*frames_by_mode.values()))

    for mode in priority:
        for idx in sorted(frames_by_mode.get(mode, [])):
            if idx in seen:
                continue
            seen.add(idx)
            chosen.append(idx)
            if budget and len(chosen) >= budget:
                return chosen, total_unique > budget
    return chosen, total_unique > budget


def _build_spine_traces(
    points: List[Dict[str, float]],
    offset: float,
    spine_idx: int,
    total_spines: int,
    draw_with_gradient: bool,
    mult_spine_gradient: bool,
) -> Tuple[List[go.Scatter], Tuple[float, float, float, float]]:
    """Create Plotly traces for a single spine frame and return its bounding box."""
    if not points:
        return [], (0, 0, 0, 0)

    origin_x = points[0]["x"]
    origin_y = points[0]["y"]
    head_angle = 0.0
    if len(points) > 1:
        head_angle = math.atan2(points[1]["y"] - origin_y, points[1]["x"] - origin_x)

    xs: List[float] = []
    ys: List[float] = []

    for pt in points:
        rel_x = pt["x"] - origin_x + offset
        rel_y = pt["y"] - origin_y
        rotated_x, rotated_y = rotate_around_origin(rel_x, rel_y, offset, 0, head_angle)
        flipped_x = flip_across_origin_x(rotated_x, offset)
        xs.append(flipped_x)
        ys.append(rotated_y)

    bbox = (min(xs), max(xs), min(ys), max(ys))

    traces: List[go.Scatter] = []
    base_color = PALETTE[spine_idx % len(PALETTE)]

    for i in range(len(xs) - 1):
        if draw_with_gradient:
            shade_ratio = (i + 1) / max(1, len(xs) - 1)
            if mult_spine_gradient:
                global_ratio = 1 - spine_idx / max(1, total_spines)
                color = tuple(channel * (0.5 + 0.5 * shade_ratio) * (0.9 * global_ratio) for channel in base_color)
            else:
                color = tuple(channel * (0.5 + 0.5 * shade_ratio) for channel in base_color)
        else:
            color = base_color
        rgb_str = f"rgb({int(color[0] * 255)}, {int(color[1] * 255)}, {int(color[2] * 255)})"
        traces.append(
            go.Scatter(
                x=xs[i : i + 2],
                y=ys[i : i + 2],
                mode="lines",
                line=dict(color=rgb_str, shape="spline"),
                showlegend=False,
            )
        )

    return traces, bbox


def _bboxes_overlap(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> bool:
    """Axis-aligned overlap check."""
    min_ax, max_ax, min_ay, max_ay = a
    min_bx, max_bx, min_by, max_by = b
    return not (max_ax < min_bx or max_bx < min_ax or max_ay < min_by or max_by < min_ay)


def _render_figures(
    per_bout_frames: List[List[Tuple[int, List[Dict[str, float]], SpineFrameDiagnostics]]],
    time_ranges: Sequence[Tuple[int, int]],
    split_by_bout: bool,
    draw_with_gradient: bool,
    mult_spine_gradient: bool,
    plot_draw_offset: float,
    open_plot: bool,
    ctx: Optional[OutputContext],
    warnings: List[str],
) -> Tuple[List[go.Figure], List[Dict[str, str]]]:
    figures: List[go.Figure] = []
    output_paths: List[Dict[str, str]] = []

    def save_fig(fig: go.Figure, base_name: str) -> Dict[str, str]:
        paths: Dict[str, str] = {}
        if ctx:
            html_path = os.path.join(ctx.output_folder, f"{base_name}.html")
            png_path = os.path.join(ctx.output_folder, f"{base_name}.png")
            fig.write_html(html_path)
            paths["html"] = html_path
            try:
                fig.write_image(png_path)
                paths["png"] = png_path
            except Exception as exc:
                warnings.append(f"Unable to write PNG for {base_name}: {exc}")
        if open_plot:
            pio.show(fig)
        return paths

    if split_by_bout:
        for bout_idx, frames in enumerate(per_bout_frames):
            fig = go.Figure()
            fig.update_yaxes(scaleanchor="x", scaleratio=1, visible=False)
            fig.update_xaxes(constrain="domain", visible=False)
            fig.update_layout(showlegend=False, title="Spine Plot")

            offset = 0.0
            bboxes: List[Tuple[float, float, float, float]] = []
            for spine_idx, (frame_idx, pts, _) in enumerate(frames):
                traces, bbox = _build_spine_traces(
                    pts, offset, spine_idx, len(frames), draw_with_gradient, mult_spine_gradient
                )
                for trace in traces:
                    fig.add_trace(trace)
                bboxes.append(bbox)
                offset += plot_draw_offset

            for i in range(len(bboxes)):
                for j in range(i + 1, len(bboxes)):
                    if _bboxes_overlap(bboxes[i], bboxes[j]):
                        warnings.append(f"Potential overlap in bout {bout_idx} between spines {i} and {j}")
                        break

            start, end = time_ranges[bout_idx]
            paths = save_fig(fig, f"spines_bout-{bout_idx}_range_{start}-{end}")
            figures.append(fig)
            output_paths.append(paths)
    else:
        fig = make_subplots(rows=len(per_bout_frames), cols=1, shared_xaxes=False, subplot_titles=None)
        fig.update_layout(showlegend=False, title="Spine Plot")

        for bout_idx, frames in enumerate(per_bout_frames):
            offset = 0.0
            bboxes: List[Tuple[float, float, float, float]] = []
            for spine_idx, (frame_idx, pts, _) in enumerate(frames):
                traces, bbox = _build_spine_traces(
                    pts, offset, spine_idx, len(frames), draw_with_gradient, mult_spine_gradient
                )
                for trace in traces:
                    fig.add_trace(trace, row=bout_idx + 1, col=1)
                bboxes.append(bbox)
                offset += plot_draw_offset

            fig.update_yaxes(scaleanchor="x", scaleratio=1, visible=False, row=bout_idx + 1, col=1)
            fig.update_xaxes(constrain="domain", visible=False, row=bout_idx + 1, col=1)

            for i in range(len(bboxes)):
                for j in range(i + 1, len(bboxes)):
                    if _bboxes_overlap(bboxes[i], bboxes[j]):
                        warnings.append(f"Potential overlap in bout {bout_idx} between spines {i} and {j}")
                        break

        paths = save_fig(fig, "spines_combined")
        figures.append(fig)
        output_paths.append(paths)

    return figures, output_paths


def render_spines(bundle: GraphDataBundle, ctx: Optional[OutputContext] = None) -> SpinePlotResult:
    """
    Render spine snapshots using bout/parallel/peak selections with confidence repair.
    """
    warnings: List[str] = []
    config = bundle.config or {}
    shown_outputs = config.get("shown_outputs", {})
    if not shown_outputs.get("show_spines", False):
        warnings.append("Spine plotting disabled by config")
        return SpinePlotResult(
            figures=[],
            mode="disabled",
            frames_by_bout=[],
            warnings=warnings,
            output_paths=[],
            diagnostics=[],
        )

    spine = (bundle.input_values or {}).get("spine")
    calc = bundle.calculated_values or {}
    left_fin = calc.get("leftFinAngles")
    right_fin = calc.get("rightFinAngles")

    time_ranges_raw = bundle.time_ranges or []
    time_ranges: List[Tuple[int, int]] = [(int(start), int(end)) for start, end in time_ranges_raw]

    if not spine or left_fin is None or right_fin is None or not time_ranges:
        missing = []
        if not spine:
            missing.append("spine")
        if left_fin is None:
            missing.append("leftFinAngles")
        if right_fin is None:
            missing.append("rightFinAngles")
        if not time_ranges:
            missing.append("time_ranges")
        warnings.append(f"Missing required inputs: {', '.join(missing)}")
        return SpinePlotResult(
            figures=[],
            mode="error",
            frames_by_bout=[],
            warnings=warnings,
            output_paths=[],
            diagnostics=[],
        )

    settings = config.get("spine_plot_settings", {})
    spines_per_bout = int(settings.get("spines_per_bout", 0) or 0)
    error_range = float(settings.get("parallel_error_range", 20))
    select_by_bout = bool(settings.get("select_by_bout", True))
    select_by_parallel = bool(settings.get("select_by_parallel_fins", False))
    select_by_peaks = bool(settings.get("select_by_peaks", False))
    split_by_bout = bool(settings.get("split_plots_by_bout", True))
    draw_with_gradient = bool(settings.get("draw_with_gradient", True))
    mult_spine_gradient = bool(settings.get("mult_spine_gradient", True))
    plot_draw_offset = float(settings.get("plot_draw_offset", 50))
    min_conf = float(settings.get("min_accepted_confidence", 0.3))
    max_broken_points = int(settings.get("accepted_broken_points", 1))
    replace_threshold = settings.get("min_confidence_replace_from_surrounding_points")
    replace_threshold = float(replace_threshold) if replace_threshold is not None else None
    max_repair_run = max_broken_points if max_broken_points > 0 else 1
    open_plot = bool(settings.get("open_plot", config.get("open_plots", False)))

    # Frame selection
    bout_frames = _select_frames_by_bout(time_ranges, spines_per_bout) if select_by_bout else [[] for _ in time_ranges]
    parallel_frames = (
        _select_frames_by_parallel(left_fin, right_fin, time_ranges, error_range) if select_by_parallel else [[] for _ in time_ranges]
    )

    cutoff_left = (config.get("graph_cutoffs", {}) or {}).get("left_fin_angle")
    cutoff_right = (config.get("graph_cutoffs", {}) or {}).get("right_fin_angle")
    use_right = bool(settings.get("fin_peaks_for_right_fin", True))
    ignore_sync = bool(settings.get("ignore_synchronized_fin_peaks", True))
    sync_range = int(settings.get("sync_fin_peaks_range", 0))

    if select_by_peaks and (cutoff_right is None and cutoff_left is None):
        warnings.append("Peak selection requested but graph_cutoffs are missing; skipping peak mode")
    peaks_frames = (
        _select_frames_by_peaks(
            right_fin if use_right else left_fin,
            left_fin if use_right else right_fin,
            time_ranges,
            cutoff_right if use_right else cutoff_left,
            cutoff_left if use_right else cutoff_right,
            ignore_sync,
            sync_range,
        )
        if select_by_peaks and (cutoff_right is not None or cutoff_left is not None)
        else [[] for _ in time_ranges]
    )

    per_bout_frames: List[List[Tuple[int, List[Dict[str, float]], SpineFrameDiagnostics]]] = []
    frames_by_bout: List[List[int]] = []
    diagnostics: List[SpineFrameDiagnostics] = []

    for bout_idx, time_range in enumerate(time_ranges):
        frames_by_mode = {
            "peaks": peaks_frames[bout_idx],
            "parallel": parallel_frames[bout_idx],
            "bout": bout_frames[bout_idx],
        }
        frame_budget = spines_per_bout if spines_per_bout > 0 else sum(len(v) for v in frames_by_mode.values())
        selected_frames, trimmed = _apply_frame_budget(frames_by_mode, frame_budget, priority=("peaks", "parallel", "bout"))
        if trimmed:
            warnings.append(f"Frame budget enforced for bout {bout_idx}; capped at {frame_budget} frames")

        bout_renderables: List[Tuple[int, List[Dict[str, float]], SpineFrameDiagnostics]] = []
        for frame_idx in selected_frames:
            repaired_pts, diag = _filter_and_repair_frame(
                spine,
                frame_idx,
                min_conf=min_conf,
                max_broken_points=max_broken_points,
                replace_threshold=replace_threshold,
                max_run=max_repair_run,
            )
            diagnostics.append(diag)
            if diag.skipped:
                warnings.append(f"Skipping frame {frame_idx} in bout {bout_idx}: {diag.reason}")
                continue
            bout_renderables.append((frame_idx, repaired_pts or [], diag))

        frames_by_bout.append([frame for frame, _, _ in bout_renderables])
        per_bout_frames.append(bout_renderables)

    figures, output_paths = _render_figures(
        per_bout_frames,
        time_ranges,
        split_by_bout=split_by_bout,
        draw_with_gradient=draw_with_gradient,
        mult_spine_gradient=mult_spine_gradient,
        plot_draw_offset=plot_draw_offset,
        open_plot=open_plot,
        ctx=ctx,
        warnings=warnings,
    )

    mode = "by_bout" if split_by_bout else "combined"
    return SpinePlotResult(
        figures=figures,
        mode=mode,
        frames_by_bout=frames_by_bout,
        warnings=warnings,
        output_paths=output_paths,
        diagnostics=diagnostics,
    )


__all__ = ["render_spines", "SpinePlotResult", "SpineFrameDiagnostics"]
