"""Overlaid time-series figure for the fish comparison view (no PyQt imports)."""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import plotly.graph_objects as go

from src.core.comparison.fish_data import LoadedFish
from src.core.comparison.fish_plot_data import FishColorMap, get_axis_labels, get_time_series


def build_overlay_figure(
    fish_list: Sequence[LoadedFish],
    parameter: str,
    color_map: FishColorMap,
    custom_units: Optional[Dict[str, str]] = None,
) -> go.Figure:
    """
    Build one figure with one line per fish for a single parameter.

    Each fish is drawn in its color from ``color_map`` so colors match across
    every plot. Fish without the parameter are left out. Gaps (NaN values)
    appear as breaks in the line.

    Args:
        fish_list: Fish to draw, in legend order.
        parameter: Result column to plot against frame number.
        color_map: Shared fish-to-color assignment.
        custom_units: Optional parameter -> unit overrides for the y-axis label.

    Returns:
        A plotly figure with a legend, axis titles and units. It has no traces
        if no fish has the parameter.
    """
    x_label, y_label = get_axis_labels(parameter, custom_units)

    figure = go.Figure()
    for fish in fish_list:
        try:
            x, y = get_time_series(fish, parameter)
        except KeyError:
            continue
        figure.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=fish.label,
                line={"color": color_map.color_for(fish.fish_id), "width": 1.5},
                hovertemplate=f"{fish.label}<br>frame %{{x}}<br>{parameter} %{{y:.4g}}<extra></extra>",
            )
        )

    figure.update_layout(
        title=f"{parameter} by fish",
        xaxis_title=x_label,
        yaxis_title=y_label,
        legend_title_text="Fish",
        showlegend=True,
        margin={"l": 60, "r": 20, "t": 50, "b": 50},
    )
    return figure