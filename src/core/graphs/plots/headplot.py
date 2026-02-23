"""
Head orientation plotter.

Renders head yaw over time using the modular plotting pipeline conventions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import plotly.graph_objects as go
import plotly.io as pio

from ..io import OutputContext
from ..loader_bundle import GraphDataBundle


@dataclass(frozen=True)
class HeadPlotResult:
    figures: List[go.Figure]
    output_paths: Dict[str, str]
    warnings: List[str]


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
    except Exception as exc:
        warnings.append(f"Unable to write PNG for {base_name}: {exc}")

    return paths


def render_headplot(bundle: GraphDataBundle, ctx: Optional[OutputContext] = None) -> HeadPlotResult:
    """
    Render a head yaw timeline plot.

    Requires bundle.calculated_values["headYaw"] (already computed by calculations).
    """
    config = bundle.config or {}
    shown_outputs = config.get("shown_outputs", {})
    warnings: List[str] = []

    if not shown_outputs.get("show_head_plot", False):
        warnings.append("Head plot disabled by config")
        return HeadPlotResult(figures=[], output_paths={}, warnings=warnings)

    settings = config.get("head_plot_settings", {})
    open_plots = settings.get("open_plot", config.get("open_plots", False))
    color_head = settings.get("head_yaw_color", "black")

    calc = bundle.calculated_values or {}
    head_yaw = calc.get("headYaw")

    if head_yaw is None:
        warnings.append("Missing required series: headYaw")
        return HeadPlotResult(figures=[], output_paths={}, warnings=warnings)

    time_ranges = [(int(s), int(e)) for s, e in (bundle.time_ranges or [])]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(range(len(head_yaw))),
            y=head_yaw,
            mode="lines",
            name="Head Yaw",
            line=dict(color=color_head, shape="spline"),
        )
    )

    # Optional: shade bout ranges if present
    for start, end in time_ranges:
        fig.add_vrect(x0=start, x1=end, fillcolor="LightSkyBlue", opacity=0.2, line_width=0)

    fig.update_layout(
        title="Head Orientation (Head Yaw) Over Time",
        xaxis_title="Frame",
        yaxis_title="Head Yaw (deg)",
        template="plotly_white",
        height=600,
        width=1000,
        showlegend=True,
    )

    output_paths = _save_figure(fig, "HeadPlot", ctx, warnings)

    if open_plots:
        pio.show(fig)

    return HeadPlotResult(figures=[fig], output_paths=output_paths, warnings=warnings)


__all__ = ["render_headplot", "HeadPlotResult"]
