"""
Reusable dot/scatter plot rendering.

Provides `render_dot_plot` which mirrors the legacy `showDotPlot` behavior with
cleaner IO hooks and metadata.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Sequence

import plotly.graph_objects as go
import plotly.io as pio

from ..io import OutputContext


@dataclass(frozen=True)
class DotPlotResult:
    """Metadata returned after rendering a dot plot."""

    figure: go.Figure
    x_label: str
    y_label: str
    point_count: int
    output_base: Optional[str]


def _sanitize_filename(name: str) -> str:
    """Convert arbitrary label combinations into safe filenames."""
    return re.sub(r"[^0-9A-Za-z_\-]+", "_", name.strip()) or "dot_plot"


def render_dot_plot(
    values_x: Sequence[float],
    values_y: Sequence[float],
    *,
    name_x: str = "A",
    name_y: str = "B",
    units_x: str = "m",
    units_y: str = "m",
    ctx: Optional[OutputContext] = None,
    open_plot: bool = False,
    filename: Optional[str] = None,
) -> DotPlotResult:
    """
    Render a scatter plot comparing two numeric series.

    Saves PNG + HTML when an OutputContext is provided and returns metadata.
    """
    if len(values_x) != len(values_y):
        raise ValueError(f"{name_x} and {name_y} must have the same length")

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=values_x,
            y=values_y,
            mode="markers",
            marker=dict(size=10, color="royalblue", opacity=0.7, line=dict(width=1, color="black")),
            name=f"{name_x} vs {name_y}",
        )
    )
    fig.update_layout(
        title=f"Dot Plot: {name_x} vs {name_y}",
        xaxis_title=f"{name_x} ({units_x})",
        yaxis_title=f"{name_y} ({units_y})",
        template="plotly_white",
    )

    output_base: Optional[str] = None
    if ctx:
        output_base = filename or f"{name_x}_{name_y}_dot_plot"
        output_base = _sanitize_filename(output_base)
        html_path = os.path.join(ctx.output_folder, f"{output_base}.html")
        png_path = os.path.join(ctx.output_folder, f"{output_base}.png")
        fig.write_html(html_path)
        fig.write_image(png_path)

    if open_plot:
        pio.show(fig)

    return DotPlotResult(
        figure=fig,
        x_label=f"{name_x} ({units_x})",
        y_label=f"{name_y} ({units_y})",
        point_count=len(values_x),
        output_base=output_base,
    )


__all__ = ["render_dot_plot", "DotPlotResult"]
