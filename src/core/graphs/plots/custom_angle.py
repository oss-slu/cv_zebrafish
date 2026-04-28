from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import plotly.graph_objects as go
import plotly.io as pio

from ..io import OutputContext
from ..loader_bundle import GraphDataBundle


@dataclass(frozen=True)
class CustomAnglePlotResult:
    figures: List[go.Figure]
    output_paths: Dict[str, str]
    warnings: List[str]


def _save_figure(fig: go.Figure, base_name: str, ctx: Optional[OutputContext], warnings: List[str]) -> Dict[str, str]:
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


def render_custom_angle(bundle: GraphDataBundle, ctx: Optional[OutputContext] = None) -> Dict[str, object]:
    """
    Render custom angle time-series plots (e.g., ThreePointAngle) if enabled.

    Expects either:
    - bundle.dataframe has the output column (preferred), or
    - bundle.calculated_values contains the output series
    """
    config = bundle.config or {}
    custom = (config.get("custom_calculations") or {}).get("three_point_angle") or {}
    enabled = bool(custom.get("enabled", False))
    output_col = str(custom.get("output_column") or "ThreePointAngle")

    warnings: List[str] = []
    if not enabled:
        warnings.append("Custom angle disabled by config")
        return {"figures": [], "output_paths": {}, "warnings": warnings}

    # Pull data
    y = None
    if bundle.dataframe is not None and output_col in getattr(bundle.dataframe, "columns", []):
        y = bundle.dataframe[output_col].tolist()
    else:
        calc = bundle.calculated_values or {}
        if output_col in calc:
            y = list(calc[output_col])

    if y is None:
        warnings.append(f"Missing required series: {output_col}")
        return {"figures": [], "output_paths": {}, "warnings": warnings}

    x = list(range(len(y)))
    title = f"Custom Angle: {output_col}"

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=output_col))
    fig.update_layout(
        title=title,
        xaxis_title="Frame",
        yaxis_title="Angle (deg)",
        template="plotly_white",
        height=600,
        width=1000,
        showlegend=True,
    )

    output_paths = _save_figure(fig, f"CustomAngle_{output_col}", ctx, warnings)

    if config.get("open_plots", False):
        pio.show(fig)

    return {"figures": [fig], "output_paths": output_paths, "warnings": warnings}
