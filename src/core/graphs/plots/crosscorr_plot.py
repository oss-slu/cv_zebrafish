"""
Cross-correlation plot renderer using Plotly.

Renders lag vs correlation coefficient plots for visual
identification of temporal relationships between signals.
"""

from typing import List, Optional

import plotly.graph_objs as go
import numpy as np


def render_crosscorr_plot(
    lags: List[int],
    correlations: List[float],
    signal_a_name: str,
    signal_b_name: str,
    peak_lag: int,
    peak_correlation: float,
) -> go.Figure:
    """
    Render a cross-correlation plot showing lag vs correlation coefficient.

    Args:
        lags: Array of lag values (frames).
        correlations: Correlation coefficient at each lag.
        signal_a_name: Name of the first signal.
        signal_b_name: Name of the second signal.
        peak_lag: Lag at maximum absolute correlation.
        peak_correlation: Correlation value at peak lag.

    Returns:
        Plotly Figure ready for display or export.
    """
    # Main trace: correlation vs lag
    trace = go.Scatter(
        x=lags,
        y=correlations,
        mode="lines",
        name=f"{signal_a_name} vs {signal_b_name}",
        line=dict(color="royalblue", width=2),
        hovertemplate="Lag: %{x}<br>Correlation: %{y:.4f}<extra></extra>",
    )

    # Highlight the peak
    peak_trace = go.Scatter(
        x=[peak_lag],
        y=[peak_correlation],
        mode="markers",
        name="Peak",
        marker=dict(color="red", size=10, symbol="x"),
        hovertemplate=f"Peak at lag {peak_lag}<br>Correlation: {peak_correlation:.4f}<extra></extra>",
    )

    # Zero-lag reference line
    zero_line = go.Scatter(
        x=[0, 0],
        y=[min(correlations), max(correlations)],
        mode="lines",
        name="Zero Lag",
        line=dict(color="gray", dash="dash", width=1),
        hoverinfo="skip",
    )

    layout = go.Layout(
        title=f"Cross-Correlation: {signal_a_name} vs {signal_b_name}",
        xaxis=dict(
            title="Lag (frames)",
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="lightgray",
        ),
        yaxis=dict(
            title="Correlation Coefficient",
            zeroline=True,
            zerolinewidth=1,
            zerolinecolor="lightgray",
        ),
        hovermode="closest",
        showlegend=True,
        template="plotly_white",
    )

    fig = go.Figure(data=[zero_line, trace, peak_trace], layout=layout)
    return fig
