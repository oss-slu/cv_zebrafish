"""
Fin + tail timeline plotter.

Creates combined or split layouts for fin angles, tail distance, and optional head yaw,
mirroring the legacy `plotFinAndTailCombined` while using the modular pipeline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from ..io import OutputContext
from ..loader_bundle import GraphDataBundle
from ..metrics import get_peaks


@dataclass(frozen=True)
class FinTailPlotResult:
    """Metadata and figures produced by the fin/tail plotter."""

    figures: List[go.Figure]
    mode: str
    peak_indices: Dict[str, List[int]]
    time_ranges: List[List[int]]
    output_paths: Dict[str, str]
    warnings: List[str]


def _prepare_series(values: Sequence[float], time_ranges: Sequence[Tuple[int, int]]) -> Tuple[List[int], List[float]]:
    """Flatten bout slices into x/y with None breaks to avoid connecting gaps."""
    x: List[int] = []
    y: List[float] = []
    for start, end in time_ranges:
        span_end = end + 1  # inclusive end index
        x.extend(range(start, span_end))
        y.extend(values[start:span_end])
        x.append(None)
        y.append(None)
    if x and x[-1] is None:
        x.pop()
        y.pop()
    return x, y


def _detect_peaks(values: Sequence[float], cutoff: Optional[float], time_ranges: Sequence[Tuple[int, int]], allow_negative: bool = False) -> List[int]:
    """Run cutoff-based peak detection and restrict results to provided ranges."""
    if cutoff is None:
        return []
    peaks = get_peaks(values, cutoff, len(values), negative_cutoff=allow_negative)
    if not time_ranges:
        return peaks
    filtered: List[int] = []
    for idx in peaks:
        for start, end in time_ranges:
            if start <= idx <= end:
                filtered.append(idx)
                break
    return filtered


def _save_figure(fig: go.Figure, base_name: str, ctx: Optional[OutputContext], warnings: List[str]) -> Dict[str, str]:
    """Write HTML/PNG if a context exists; return written paths."""
    paths: Dict[str, str] = {}
    if not ctx:
        return paths

    html_path = os.path.join(ctx.output_folder, f"{base_name}.html")
    png_path = os.path.join(ctx.output_folder, f"{base_name}.png")
    fig.write_html(html_path)
    paths["html"] = html_path
    try:
        fig.write_image(png_path)
        paths["png"] = png_path
    except Exception as exc:  # Kaleido missing or other IO error
        warnings.append(f"Unable to write PNG for {base_name}: {exc}")
    return paths


def _has_required_length(series: Sequence[float], time_ranges: Sequence[Tuple[int, int]]) -> bool:
    if not time_ranges:
        return True
    needed = max(end for _, end in time_ranges)
    return len(series) > needed


def render_fin_tail(bundle: GraphDataBundle, ctx: Optional[OutputContext] = None) -> FinTailPlotResult:
    """
    Render fin angles + tail distance (and optional head yaw) as combined or split plots.
    """
    config = bundle.config or {}
    shown_outputs = config.get("shown_outputs", {})
    warnings: List[str] = []

    if not shown_outputs.get("show_angle_and_distance_plot", False):
        warnings.append("Angle and distance plot disabled by config")
        return FinTailPlotResult(figures=[], mode="disabled", peak_indices={}, time_ranges=bundle.time_ranges, output_paths={}, warnings=warnings)

    settings = config.get("angle_and_distance_plot_settings", {})
    combine_plots = settings.get("combine_plots", True)
    open_plots = settings.get("open_plot", config.get("open_plots", False))

    calc = bundle.calculated_values or {}
    left_fin = calc.get("leftFinAngles")
    right_fin = calc.get("rightFinAngles")
    tail_dist = calc.get("tailDistances")
    head_yaw = calc.get("headYaw")

    time_ranges = [(int(start), int(end)) for start, end in (bundle.time_ranges or [])]
    if not time_ranges:
        warnings.append("No time ranges provided; plotting entire series if available")
        time_ranges = [(0, min(len(left_fin or []), len(right_fin or []), len(tail_dist or [])) - 1)] if left_fin and right_fin and tail_dist else []

    required_series = {
        "leftFinAngles": left_fin,
        "rightFinAngles": right_fin,
        "tailDistances": tail_dist,
    }
    missing = [name for name, series in required_series.items() if series is None]
    if missing:
        warnings.append(f"Missing required series: {', '.join(missing)}")
        return FinTailPlotResult(figures=[], mode="error", peak_indices={}, time_ranges=time_ranges, output_paths={}, warnings=warnings)

    too_short = [name for name, series in required_series.items() if not _has_required_length(series, time_ranges)]
    if too_short:
        warnings.append(f"Series shorter than required by time ranges: {', '.join(too_short)}")
        return FinTailPlotResult(figures=[], mode="error", peak_indices={}, time_ranges=time_ranges, output_paths={}, warnings=warnings)

    cutoffs = config.get("graph_cutoffs", {})
    peak_indices = {
        "leftFinAngles": _detect_peaks(left_fin, cutoffs.get("left_fin_angle"), time_ranges),
        "rightFinAngles": _detect_peaks(right_fin, cutoffs.get("right_fin_angle"), time_ranges),
        "tailDistances": _detect_peaks(tail_dist, cutoffs.get("tail_angle"), time_ranges, allow_negative=True),
    }

    color_left = settings.get("left_fin_color", "blue")
    color_right = settings.get("right_fin_color", "red")
    color_tail = settings.get("tail_distance_color", "green")
    color_head = settings.get("head_yaw_color", "black")

    show_left = settings.get("show_left_fin_angle", True)
    show_right = settings.get("show_right_fin_angle", True)
    show_tail = settings.get("show_tail_distance", True)
    show_head = settings.get("show_head_yaw", head_yaw is not None)

    if combine_plots:
        fig = make_subplots(specs=[[{"secondary_y": True}]])

        if show_left:
            x, y = _prepare_series(left_fin, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Left Fin Angle", line=dict(color=color_left, shape="spline")), secondary_y=False)
        if show_right:
            x, y = _prepare_series(right_fin, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Right Fin Angle", line=dict(color=color_right, shape="spline")), secondary_y=False)
        if show_head and head_yaw is not None:
            x, y = _prepare_series(head_yaw, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Head Yaw", line=dict(color=color_head, dash="dot", shape="spline")), secondary_y=False)
        if show_tail:
            x, y = _prepare_series(tail_dist, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Tail Distance", line=dict(color=color_tail, shape="spline")), secondary_y=True)

        fig.update_layout(
            height=700,
            width=1000,
            title_text="Fin Angles, Head Yaw, and Tail Distance Over Time",
            showlegend=True,
            template="plotly_white",
        )
        fig.update_xaxes(title_text="Frame")
        fig.update_yaxes(title_text="Fin Angles / Head Yaw (deg)", secondary_y=False)
        fig.update_yaxes(title_text="Tail Distance (m)", secondary_y=True)

        output_paths = _save_figure(fig, "FinAndTailCombined", ctx, warnings)
        if open_plots:
            pio.show(fig)
        figures = [fig]
        mode = "combined"
    else:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("Fin Angles and Head Yaw", "Tail Distance"),
            specs=[[{}], [{"secondary_y": True}]],
            row_heights=[0.5, 0.5],
        )

        if show_left:
            x, y = _prepare_series(left_fin, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Left Fin Angle", line=dict(color=color_left, shape="spline")), row=1, col=1)
        if show_right:
            x, y = _prepare_series(right_fin, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Right Fin Angle", line=dict(color=color_right, shape="spline")), row=1, col=1)
        if show_tail:
            x, y = _prepare_series(tail_dist, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Tail Distance", line=dict(color=color_tail, shape="spline")), row=2, col=1, secondary_y=False)
        if show_head and head_yaw is not None:
            x, y = _prepare_series(head_yaw, time_ranges)
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name="Head Yaw", line=dict(color=color_head, shape="spline")), row=2, col=1, secondary_y=True)

        fig.update_layout(
            height=700,
            width=1000,
            title_text="Fin Angles, Head Yaw, and Tail Distance Over Time",
            showlegend=True,
            template="plotly_white",
        )
        fig.update_xaxes(title_text="Frame", row=2, col=1)
        fig.update_yaxes(title_text="Fin Angles (deg)", row=1, col=1)
        fig.update_yaxes(title_text="Tail Distance (m)", row=2, col=1, secondary_y=False)
        fig.update_yaxes(title_text="Head Yaw (deg)", row=2, col=1, secondary_y=True)

        output_paths = _save_figure(fig, "FinAndTailCombined_Subplots", ctx, warnings)
        if open_plots:
            pio.show(fig)
        figures = [fig]
        mode = "split"

    return FinTailPlotResult(
        figures=figures,
        mode=mode,
        peak_indices=peak_indices,
        time_ranges=[list(r) for r in time_ranges],
        output_paths=output_paths,
        warnings=warnings,
    )


__all__ = ["render_fin_tail", "FinTailPlotResult"]
