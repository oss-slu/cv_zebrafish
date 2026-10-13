"""
summary_statistics.py
---------------------
Core calculation module for computing summary statistics (mean, median, and counts)
across kinematic analysis outputs.

NaN and DLC Likelihood Handling:
--------------------------------
In DeepLabCut workflows, frames with missing detections or likelihoods below the
filtering cutoff yield NaN values in kinematics arrays (angles, distances, yaw).
This module follows standard scientific data processing rules:
1. Missing, NaN, None, and non-finite (infinite) values are excluded prior to
   computing statistical aggregations (mean, median).
2. If all values are NaN or a series is empty, the count is 0, and both mean and
   median evaluate to float('nan').
3. For odd counts of valid values, median is the central sorted value.
4. For even counts of valid values, median is the mean of the two central sorted values.
5. Calculation logic remains strictly decoupled from Qt UI and presentation layers.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd


# Canonical metadata mapping for zebrafish kinematic parameters and outputs.
# Maps column/parameter identifier to human-readable description and physical units.
KNOWN_ANALYSIS_PARAMETERS: Dict[str, Dict[str, str]] = {
    "LF_Angle": {
        "label": "Left Fin Angle",
        "units": "deg",
        "category": "angles",
    },
    "RF_Angle": {
        "label": "Right Fin Angle",
        "units": "deg",
        "category": "angles",
    },
    "Tail_Angle": {
        "label": "Tail Angle",
        "units": "deg",
        "category": "angles",
    },
    "HeadYaw": {
        "label": "Head Yaw",
        "units": "deg",
        "category": "angles",
    },
    "curBoutHeadYaw": {
        "label": "Bout Head Yaw",
        "units": "deg",
        "category": "angles",
    },
    "Tail_Distance": {
        "label": "Tail Distance",
        "units": "mm",
        "category": "displacement",
    },
    "Tail_Distance_Pixels": {
        "label": "Tail Distance (Pixels)",
        "units": "px",
        "category": "displacement",
    },
    "HeadX": {
        "label": "Head X Position",
        "units": "mm",
        "category": "position",
    },
    "HeadY": {
        "label": "Head Y Position",
        "units": "mm",
        "category": "position",
    },
    "tail_beat_frequency": {
        "label": "Tail Beat Frequency",
        "units": "Hz",
        "category": "frequency",
    },
    "left_fin_beat_frequency": {
        "label": "Left Fin Beat Frequency",
        "units": "Hz",
        "category": "frequency",
    },
    "right_fin_beat_frequency": {
        "label": "Right Fin Beat Frequency",
        "units": "Hz",
        "category": "frequency",
    },
    "velocity": {
        "label": "Velocity",
        "units": "mm/s",
        "category": "velocity",
    },
}


def get_parameter_units(param_name: str, custom_units: Optional[Dict[str, str]] = None) -> str:
    """
    Return measurement units for a given parameter name.

    Resolves units through custom mappings, known parameter metadata, or dynamic naming patterns
    (e.g., segmented spine tail angles, angle/frequency/velocity heuristics).
    """
    if custom_units and param_name in custom_units:
        return custom_units[param_name]
    if param_name in KNOWN_ANALYSIS_PARAMETERS:
        return KNOWN_ANALYSIS_PARAMETERS[param_name]["units"]
    if param_name.startswith("TailAngle_"):
        return "deg"
    if "angle" in param_name.lower():
        return "deg"
    if "frequency" in param_name.lower() or "freq" in param_name.lower():
        return "Hz"
    if "distance" in param_name.lower():
        return "mm"
    if "velocity" in param_name.lower() or "speed" in param_name.lower():
        return "mm/s"
    return ""


@dataclass(frozen=True)
class SeriesSummaryStats:
    """Statistical summary for a single series of values."""

    count: int
    mean: float
    median: float
    is_valid: bool


def clean_numeric_series(values: Optional[Sequence[Any]]) -> List[float]:
    """
    Extract finite, numeric float values from a sequence, skipping None, NaN, inf,
    and non-numeric elements.
    """
    if values is None:
        return []

    cleaned: List[float] = []
    for val in values:
        if val is None:
            continue
        try:
            f = float(val)
        except (ValueError, TypeError):
            continue

        if math.isnan(f) or math.isinf(f):
            continue

        cleaned.append(f)

    return cleaned


def compute_series_summary_stats(values: Optional[Sequence[Any]]) -> SeriesSummaryStats:
    """
    Compute mean and median for a sequence of values, safely handling empty series,
    all-NaN values, and mixed types.

    Returns:
        SeriesSummaryStats with count, mean, median, and is_valid flag.
        If no valid numeric values exist, count is 0, mean and median are NaN,
        and is_valid is False.
    """
    cleaned = clean_numeric_series(values)
    count = len(cleaned)

    if count == 0:
        return SeriesSummaryStats(
            count=0,
            mean=float("nan"),
            median=float("nan"),
            is_valid=False,
        )

    mean_val = float(np.mean(cleaned))
    median_val = float(np.median(cleaned))

    return SeriesSummaryStats(
        count=count,
        mean=mean_val,
        median=median_val,
        is_valid=True,
    )


def compute_summary_statistics_df(
    data: Union[pd.DataFrame, Dict[str, Sequence[Any]]],
    parameters: Optional[Sequence[str]] = None,
    custom_units: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """
    Compute mean and median for multiple analysis parameters and return a standardized
    DataFrame with columns: ['parameter', 'mean', 'median', 'units'].

    Args:
        data: DataFrame or dictionary of parameter series.
        parameters: Optional list of parameters to include. If None, all numeric columns/series are processed.
        custom_units: Optional dictionary mapping parameter names to custom unit strings.

    Returns:
        pd.DataFrame: Columns ['parameter', 'mean', 'median', 'units'] containing summary statistics.
    """
    if isinstance(data, pd.DataFrame):
        df = data
    elif isinstance(data, dict):
        df = pd.DataFrame(data)
    else:
        raise TypeError("Input data must be a pandas DataFrame or dictionary of series.")

    if parameters is None:
        candidate_params = [
            col for col in df.columns
            if col != "Time" and not col.startswith("timeRange") and not col.endswith("Peaks")
        ]
    else:
        candidate_params = list(parameters)

    rows: List[Dict[str, Any]] = []
    for param in candidate_params:
        if param not in df.columns:
            continue

        stats = compute_series_summary_stats(df[param].values)
        units = get_parameter_units(param, custom_units)

        rows.append({
            "parameter": param,
            "mean": stats.mean,
            "median": stats.median,
            "units": units,
        })

    return pd.DataFrame(rows, columns=["parameter", "mean", "median", "units"])
