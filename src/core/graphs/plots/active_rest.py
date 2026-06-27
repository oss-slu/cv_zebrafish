"""Active/rest state timeline plot for low-resolution movement analysis."""

from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np
import plotly.graph_objs as go


def render_active_rest_plot(
    time_s: Sequence[float],
    states: Sequence[int],
    *,
    active_bouts: Optional[List[List[int]]] = None,
    framerate: float = 1.0,
    track_point: str = "",
) -> go.Figure:
    """
    Render active (1) vs rest (0) states over time.

    Args:
        time_s: Time axis in seconds.
        states: Per-frame 0/1 state array.
        active_bouts: Optional list of [start, end] frame indices for annotations.
        framerate: Used only for bout labels when time_s is frame-index based.
        track_point: Bodypart label shown in the title.
    """
    t = np.asarray(time_s, dtype=float)
    y = np.asarray(states, dtype=float)

    trace = go.Scatter(
        x=t,
        y=y,
        mode="lines",
        name="Movement state",
        line=dict(shape="hv", color="#2ca02c", width=2),
        fill="tozeroy",
        fillcolor="rgba(44, 160, 44, 0.25)",
        hovertemplate="Time: %{x:.3f} s<br>State: %{customdata}<extra></extra>",
        customdata=["Active" if v >= 0.5 else "Rest" for v in y],
    )

    fig = go.Figure(data=[trace])
    title = "Active / Rest movement states"
    if track_point:
        title += f" ({track_point})"

    fig.update_layout(
        title=title,
        xaxis_title="Time (s)",
        yaxis_title="State",
        yaxis=dict(
            tickmode="array",
            tickvals=[0, 1],
            ticktext=["Rest", "Active"],
            range=[-0.1, 1.1],
        ),
        margin=dict(l=60, r=30, t=50, b=50),
        showlegend=False,
    )

    if active_bouts:
        for i, bout in enumerate(active_bouts, start=1):
            if len(bout) < 2:
                continue
            start, end = int(bout[0]), int(bout[1])
            if start < len(t):
                x0 = float(t[start])
                x1 = float(t[min(end, len(t) - 1)])
                fig.add_vrect(
                    x0=x0,
                    x1=x1,
                    fillcolor="rgba(44, 160, 44, 0.08)",
                    line_width=0,
                    annotation_text=f"Bout {i}",
                    annotation_position="top left",
                    annotation_font_size=10,
                )

    return fig
