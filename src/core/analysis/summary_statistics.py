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
5. Heading/yaw angles (e.g., HeadYaw, curBoutHeadYaw) wrap across [-180°, 180°].
   For these circular quantities, circular mean and median are computed so that
   opposing boundary angles (such as 179° and -179°) average correctly to 180°
   rather than falsely averaging to 0°.
6. Non-numeric or completely empty/all-NaN columns (such as text markers like
   Tail_Side or Furthest_Tail_Point) are omitted from summary statistics tables.
7. Calculation logic remains strictly decoupled from Qt UI and presentation layers.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

PathLike = Union[str, Path]


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
        "units": "m",
        "category": "displacement",
    },
    "Tail_Distance_Pixels": {
        "label": "Tail Distance (Pixels)",
        "units": "px",
        "category": "displacement",
    },
    "HeadX": {
        "label": "Head X Position",
        "units": "m",
        "category": "position",
    },
    "HeadY": {
        "label": "Head Y Position",
        "units": "m",
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
        "units": "m/s",
        "category": "velocity",
    },
}

CIRCULAR_PARAMETERS = {"HeadYaw", "curBoutHeadYaw"}


def is_circular_parameter(param_name: str) -> bool:
    """Return True if parameter is an angular heading/yaw quantity wrapping around +/-180 deg."""
    if param_name in CIRCULAR_PARAMETERS:
        return True
    lower = param_name.lower()
    return "yaw" in lower or "heading" in lower


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
    lower = param_name.lower()
    if "angle" in lower:
        return "deg"
    if "frequency" in lower or "freq" in lower:
        return "Hz"
    if "distance" in lower:
        if "pixel" in lower or "px" in lower:
            return "px"
        return "m"
    if "velocity" in lower or "speed" in lower:
        return "m/s"
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


def compute_circular_mean(angles_deg: Sequence[float]) -> float:
    """
    Compute circular mean for angles specified in degrees wrapped around [-180, 180].

    Avoids arithmetic average distortion for wrapping angles (e.g., 179° and -179°
    average to 180°, not 0°).
    """
    cleaned = clean_numeric_series(angles_deg)
    if not cleaned:
        return float("nan")

    rads = np.radians(cleaned)
    sin_sum = float(np.sum(np.sin(rads)))
    cos_sum = float(np.sum(np.cos(rads)))

    if math.isclose(sin_sum, 0.0, abs_tol=1e-9) and math.isclose(cos_sum, 0.0, abs_tol=1e-9):
        return float("nan")

    mean_rad = math.atan2(sin_sum, cos_sum)
    mean_deg = math.degrees(mean_rad)
    return float(round(mean_deg, 6))


def compute_circular_median(angles_deg: Sequence[float]) -> float:
    """
    Compute circular median for angles specified in degrees wrapped around [-180, 180].

    Finds the angle(s) that minimize circular arc distance to all sample points,
    taking the circular midpoint if multiple candidates achieve the minimum.
    """
    cleaned = clean_numeric_series(angles_deg)
    if not cleaned:
        return float("nan")
    if len(cleaned) == 1:
        return float(cleaned[0])

    angles = np.array(cleaned, dtype=float)
    wrapped = (angles + 180.0) % 360.0 - 180.0
    sorted_angles = np.sort(wrapped)

    candidates = list(sorted_angles)
    n = len(sorted_angles)
    for i in range(n):
        a1 = sorted_angles[i]
        a2 = sorted_angles[(i + 1) % n]
        diff = (a2 - a1 + 180.0) % 360.0 - 180.0
        mid = (a1 + diff / 2.0 + 180.0) % 360.0 - 180.0
        candidates.append(mid)

    min_dist = float("inf")
    best_candidates = []
    for cand in candidates:
        diffs = np.abs((angles - cand + 180.0) % 360.0 - 180.0)
        tot_dist = float(np.sum(diffs))
        if tot_dist < min_dist - 1e-6:
            min_dist = tot_dist
            best_candidates = [cand]
        elif abs(tot_dist - min_dist) <= 1e-6:
            best_candidates.append(cand)

    if len(best_candidates) == 1:
        return float(round(best_candidates[0], 6))
    return float(round(compute_circular_mean(best_candidates), 6))


def compute_series_summary_stats(
    values: Optional[Sequence[Any]],
    is_circular: bool = False,
) -> SeriesSummaryStats:
    """
    Compute mean and median for a sequence of values, safely handling empty series,
    all-NaN values, and mixed types.

    If is_circular=True, circular mean and median are used to properly handle
    angle wrap-around (e.g. for heading/yaw data wrapping across +/-180 deg).

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

    if is_circular:
        mean_val = compute_circular_mean(cleaned)
        median_val = compute_circular_median(cleaned)
    else:
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
    skip_all_nan: bool = True,
) -> pd.DataFrame:
    """
    Compute mean and median for multiple analysis parameters and return a standardized
    DataFrame with columns: ['parameter', 'mean', 'median', 'units'].

    Args:
        data: DataFrame or dictionary of parameter series.
        parameters: Optional list of parameters to include. If None, all numeric columns/series are processed.
        custom_units: Optional dictionary mapping parameter names to custom unit strings.
        skip_all_nan: If True (default), parameters with zero valid numeric points (or all NaN) are skipped.

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

        is_circ = is_circular_parameter(param)
        stats = compute_series_summary_stats(df[param].values, is_circular=is_circ)
        if skip_all_nan and stats.count == 0:
            continue

        units = get_parameter_units(param, custom_units)

        rows.append({
            "parameter": param,
            "mean": stats.mean,
            "median": stats.median,
            "units": units,
        })

    return pd.DataFrame(rows, columns=["parameter", "mean", "median", "units"])


def export_summary_statistics_to_csv(
    data: Union[pd.DataFrame, Dict[str, Sequence[Any]]],
    output_path: PathLike,
    parameters: Optional[Sequence[str]] = None,
    custom_units: Optional[Dict[str, str]] = None,
    skip_all_nan: bool = True,
) -> Path:
    """
    Export summary statistics table (parameter, mean, median, units) to a CSV file.

    Args:
        data: Either an existing summary statistics DataFrame or raw kinematic data.
        output_path: Target CSV file path.
        parameters: Optional list of parameters to filter.
        custom_units: Optional dictionary of parameter units.
        skip_all_nan: Whether to skip all-NaN/empty columns.

    Returns:
        Path to the exported CSV file.
    """
    if isinstance(data, pd.DataFrame) and list(data.columns) == ["parameter", "mean", "median", "units"]:
        summary_df = data
    else:
        summary_df = compute_summary_statistics_df(
            data, parameters=parameters, custom_units=custom_units, skip_all_nan=skip_all_nan
        )

    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.suffix:
        path = path.with_suffix(".csv")
    summary_df.to_csv(path, index=False)
    return path


def export_summary_statistics_to_excel(
    data: Union[pd.DataFrame, Dict[str, Sequence[Any]]],
    output_path: PathLike,
    sheet_name: str = "Summary Statistics",
    parameters: Optional[Sequence[str]] = None,
    custom_units: Optional[Dict[str, str]] = None,
    skip_all_nan: bool = True,
) -> Path:
    """
    Export summary statistics table (parameter, mean, median, units) to an Excel spreadsheet.

    Args:
        data: Either an existing summary statistics DataFrame or raw kinematic data.
        output_path: Target Excel file path (.xlsx).
        sheet_name: Name of the Excel sheet (defaults to 'Summary Statistics').
        parameters: Optional list of parameters to filter.
        custom_units: Optional dictionary of parameter units.
        skip_all_nan: Whether to skip all-NaN/empty columns.

    Returns:
        Path to the exported Excel file.
    """
    if isinstance(data, pd.DataFrame) and list(data.columns) == ["parameter", "mean", "median", "units"]:
        summary_df = data
    else:
        summary_df = compute_summary_statistics_df(
            data, parameters=parameters, custom_units=custom_units, skip_all_nan=skip_all_nan
        )

    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.suffix:
        path = path.with_suffix(".xlsx")
    summary_df.to_excel(path, sheet_name=sheet_name, index=False)
    return path
