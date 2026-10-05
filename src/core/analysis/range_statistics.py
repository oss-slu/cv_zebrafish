"""
range_statistics.py
-------------------
Core calculation module for computing basic statistics (minimum, maximum,
corresponding x/frame positions, and mean) across user-selected ranges of graph data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import plotly.graph_objs as go


@dataclass(frozen=True)
class RangeStatisticsResult:
    """Statistics calculated for a specific range of x/frame values."""

    is_valid: bool
    error_message: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    min_x: Optional[float] = None
    max_x: Optional[float] = None
    mean_value: Optional[float] = None
    count: int = 0
    start_x: Optional[float] = None
    end_x: Optional[float] = None


def clean_numeric_pairs(
    x_values: Sequence[Any],
    y_values: Sequence[Any],
) -> Tuple[List[float], List[float]]:
    """
    Filter paired sequences to valid, finite numeric floats.

    Skips pairs where either x or y is None, non-numeric, NaN, or infinite.
    Ensures x and y stay strictly aligned.
    """
    cleaned_x: List[float] = []
    cleaned_y: List[float] = []

    for xi, yi in zip(x_values, y_values):
        if xi is None or yi is None:
            continue
        try:
            xf = float(xi)
            yf = float(yi)
        except (ValueError, TypeError):
            continue

        if math.isnan(xf) or math.isnan(yf) or math.isinf(xf) or math.isinf(yf):
            continue

        cleaned_x.append(xf)
        cleaned_y.append(yf)

    return cleaned_x, cleaned_y


def compute_range_statistics(
    x_values: Optional[Sequence[Any]],
    y_values: Optional[Sequence[Any]],
    start_x: float,
    end_x: float,
) -> RangeStatisticsResult:
    """
    Calculate min, max, corresponding x positions, and mean for data points
    whose x-value falls within [start_x, end_x].

    Handles empty ranges, invalid ranges (start_x > end_x), non-numeric values,
    None values, and NaNs without raising exceptions.
    """
    if y_values is None or len(y_values) == 0:
        return RangeStatisticsResult(
            is_valid=False,
            error_message="No data points available.",
            start_x=start_x,
            end_x=end_x,
        )

    if x_values is None:
        x_values = list(range(len(y_values)))

    if len(x_values) != len(y_values):
        return RangeStatisticsResult(
            is_valid=False,
            error_message="Mismatched X and Y data lengths.",
            start_x=start_x,
            end_x=end_x,
        )

    try:
        s_x = float(start_x)
        e_x = float(end_x)
    except (ValueError, TypeError):
        return RangeStatisticsResult(
            is_valid=False,
            error_message="Range bounds must be numeric.",
            start_x=start_x,
            end_x=end_x,
        )

    if math.isnan(s_x) or math.isnan(e_x):
        return RangeStatisticsResult(
            is_valid=False,
            error_message="Range bounds cannot be NaN.",
            start_x=start_x,
            end_x=end_x,
        )

    if s_x > e_x:
        return RangeStatisticsResult(
            is_valid=False,
            error_message=f"Invalid range: Start ({s_x:g}) cannot exceed End ({e_x:g}).",
            start_x=s_x,
            end_x=e_x,
        )

    # Clean numeric pairs and filter to [start_x, end_x]
    cleaned_x, cleaned_y = clean_numeric_pairs(x_values, y_values)
    filtered_x: List[float] = []
    filtered_y: List[float] = []

    for xf, yf in zip(cleaned_x, cleaned_y):
        if s_x <= xf <= e_x:
            filtered_x.append(xf)
            filtered_y.append(yf)

    if not filtered_y:
        return RangeStatisticsResult(
            is_valid=False,
            error_message=f"No data points in selected range [{s_x:g}, {e_x:g}].",
            start_x=s_x,
            end_x=e_x,
            count=0,
        )

    # Calculate statistics
    min_idx = int(np.argmin(filtered_y))
    max_idx = int(np.argmax(filtered_y))

    min_val = float(filtered_y[min_idx])
    max_val = float(filtered_y[max_idx])
    min_x = float(filtered_x[min_idx])
    max_x = float(filtered_x[max_idx])
    mean_val = float(np.mean(filtered_y))
    count = len(filtered_y)

    return RangeStatisticsResult(
        is_valid=True,
        min_value=min_val,
        max_value=max_val,
        min_x=min_x,
        max_x=max_x,
        mean_value=mean_val,
        count=count,
        start_x=s_x,
        end_x=e_x,
    )


def extract_traces_from_figure(
    fig: Optional[go.Figure],
) -> Dict[str, Tuple[List[float], List[float]]]:
    """
    Extract named numeric traces (x, y) from a Plotly Figure.
    Returns a dict mapping trace name to (x_list, y_list).
    """
    if not isinstance(fig, go.Figure) or not fig.data:
        return {}

    traces: Dict[str, Tuple[List[float], List[float]]] = {}

    for i, trace in enumerate(fig.data):
        y_data = getattr(trace, "y", None)
        if y_data is None or len(y_data) == 0:
            continue

        x_data = getattr(trace, "x", None)
        if x_data is None or len(x_data) == 0:
            x_data = list(range(len(y_data)))

        # Clean into finite floats
        cleaned_x, cleaned_y = clean_numeric_pairs(x_data, y_data)
        if not cleaned_y:
            continue

        name = str(getattr(trace, "name", "") or "").strip()
        if not name:
            name = f"Trace {i + 1}"

        # Deduplicate trace names if multiple traces have the exact same name
        base_name = name
        dup_idx = 2
        while name in traces:
            name = f"{base_name} ({dup_idx})"
            dup_idx += 1

        traces[name] = (cleaned_x, cleaned_y)

    return traces


def get_figure_x_bounds(fig: Optional[go.Figure]) -> Optional[Tuple[float, float]]:
    """
    Find the global minimum and maximum X values across all traces in a Plotly Figure.
    Returns (min_x, max_x) or None if no valid data exists.
    """
    traces = extract_traces_from_figure(fig)
    if not traces:
        return None

    all_x: List[float] = []
    for x_vals, _ in traces.values():
        all_x.extend(x_vals)

    if not all_x:
        return None

    return float(min(all_x)), float(max(all_x))
