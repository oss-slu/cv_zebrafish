#!/usr/bin/env python3
"""
Compare legacy Bruce pipeline calculations with the new cv_zebrafish implementation.

This script serves as a command-line tool to run both the legacy and new
calculation pipelines on the same input data and configuration. It then
compares their outputs on a column-by-column basis, producing a detailed
report of any discrepancies. This is essential for verifying the correctness
and consistency of the new implementation.

The script handles the complexities of running the legacy pipeline, which is
not a standard Python package, and normalizes its output to allow for a
meaningful comparison with the new pipeline's results.

Usage:
    python calculations/compare_calculations.py \\
        --csv data_schema_validation/sample_inputs/csv/correct_format.csv \\
        --config data_schema_validation/sample_inputs/jsons/BaseConfig.json
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import types
import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEGACY_ROOT = (REPO_ROOT.parent / "codes" / "bruce" / "codes").resolve()

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

@dataclass
class ColumnComparison:
    """
    Holds the results of comparing a single column between two dataframes.

    Attributes:
        name: The name of the column.
        kind: The data type of the column ('numeric' or 'categorical').
        mismatches: The number of rows where the values differ.
        max_abs_diff: For numeric columns, the maximum absolute difference found.
        sample_indices: A list of row indices where mismatches were found.
    """
    name: str
    kind: str
    mismatches: int
    max_abs_diff: Optional[float] = None
    sample_indices: Optional[List[int]] = None


def parse_args() -> argparse.Namespace:
    """
    Defines and parses command-line arguments for the script.

    Returns:
        An argparse.Namespace object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Run both calculation pipelines and compare their outputs."
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the DeepLabCut CSV file to process.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON configuration file to use.",
    )
    parser.add_argument(
        "--legacy-root",
        default=str(DEFAULT_LEGACY_ROOT),
        help="Path to the root of the legacy Bruce codebase (defaults to ../codes/bruce/codes).",
    )
    parser.add_argument(
        "--atol",
        type=float,
        default=1e-6,
        help="Absolute tolerance for numeric comparisons (default: 1e-6).",
    )
    parser.add_argument(
        "--rtol",
        type=float,
        default=1e-6,
        help="Relative tolerance for numeric comparisons (default: 1e-6).",
    )
    parser.add_argument(
        "--export-dir",
        default=None,
        help="Optional directory to export the normalized legacy and new outputs as CSV files.",
    )
    return parser.parse_args()


def ensure_import_paths(legacy_root: Path) -> None:
    """
    Ensure that the repository root and legacy code paths are in the system path.

    This allows for seamless imports from both the new and legacy pipelines.

    Args:
        legacy_root: The path to the root of the legacy codebase.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(legacy_root) not in sys.path:
        sys.path.insert(0, str(legacy_root))


def load_config(config_path: Path) -> dict:
    """
    Load a JSON configuration file.

    Args:
        config_path: The path to the JSON configuration file.

    Returns:
        A dictionary containing the loaded configuration.
    """
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_new_pipeline(csv_path: Path, config: dict) -> pd.DataFrame:
    """
    Run the new cv_zebrafish calculation pipeline.

    Args:
        csv_path: Path to the DeepLabCut CSV file to process.
        config: A dictionary with the configuration for the new pipeline.

    Returns:
        A pandas DataFrame with the calculated results, with the index reset.
    """
    from calculations.utils.Parser import parse_dlc_csv
    from calculations.utils.Driver import run_calculations

    parsed_points = parse_dlc_csv(str(csv_path), config)
    new_df = run_calculations(parsed_points, config)
    return new_df.reset_index(drop=True)


def run_legacy_pipeline(
    csv_path: Path, config: dict, legacy_root: Optional[Path] = None
) -> Tuple[pd.DataFrame, List[List[int]]]:
    """
    Run the legacy Bruce calculation pipeline.

    This function is complex because it needs to dynamically load the legacy
    code, which is not structured as a standard Python package. It carefully
    manipulates `sys.path` and `sys.modules` to import the legacy
    `mainCalculation` module without interfering with the current project's
    modules.

    Args:
        csv_path: Path to the DeepLabCut CSV file to process.
        config: A dictionary with the configuration for the legacy pipeline.
        legacy_root: Optional path to the root of the legacy codebase.

    Returns:
        A tuple containing:
        - A pandas DataFrame with the calculated results, with the index reset.
        - A list of time ranges detected by the legacy calculation.
    """
    if legacy_root is None:
        legacy_root = DEFAULT_LEGACY_ROOT
    ensure_import_paths(legacy_root)
    sys.modules.pop("utils.mainCalculation", None)
    prev_utils = sys.modules.pop("utils", None)
    legacy_utils_pkg = types.ModuleType("utils")
    legacy_utils_pkg.__path__ = [str(legacy_root / "utils")]
    sys.modules["utils"] = legacy_utils_pkg
    legacy_module = importlib.import_module("utils.mainCalculation")
    if prev_utils is not None:
        sys.modules["utils"] = prev_utils
    else:
        sys.modules.pop("utils", None)
    setupValueStructs = legacy_module.setupValueStructs
    getCalculated = legacy_module.getCalculated

    df_raw = pd.read_csv(csv_path, header=1)
    calculated_values, input_values = setupValueStructs(config, df_raw)
    results_list, time_ranges = getCalculated(input_values, calculated_values, config, df_raw)
    legacy_df = pd.DataFrame(results_list).reset_index(drop=True)
    return legacy_df, time_ranges


def normalize_time_range_columns(
    n_rows: int, time_ranges: Sequence[Sequence[int]]
) -> pd.DataFrame:
    """
    Create a DataFrame with normalized time range columns.

    The legacy pipeline produces time range columns where the values only
    exist in the first row. This function replicates that structure.

    Args:
        n_rows: The total number of rows for the resulting DataFrame.
        time_ranges: A sequence of (start, end) time pairs.

    Returns:
        A pandas DataFrame with columns for each time range, e.g.,
        `timeRangeStart_0`, `timeRangeEnd_0`, etc.
    """
    if not time_ranges:
        return pd.DataFrame(index=range(n_rows))
    data = {}
    for idx, (start, end) in enumerate(time_ranges):
        start_col = f"timeRangeStart_{idx}"
        end_col = f"timeRangeEnd_{idx}"
        data[start_col] = [start] + [""] * (n_rows - 1)
        data[end_col] = [end] + [""] * (n_rows - 1)
    return pd.DataFrame(data)


def normalize_legacy_dataframe(
    legacy_df: pd.DataFrame, time_ranges: Sequence[Sequence[int]]
) -> pd.DataFrame:
    """
    Normalize the legacy DataFrame to facilitate comparison.

    This involves renaming columns to match the new pipeline's output,
    handling special time range columns, and dropping columns that are
    no longer in use.

    Args:
        legacy_df: The raw DataFrame from the legacy pipeline.
        time_ranges: The list of time ranges from the legacy pipeline.

    Returns:
        A new, normalized pandas DataFrame.
    """
    df = legacy_df.copy()
    rename_map = {
        "ET_DistancefromCenterline": "Tail_Distance",
        "ET_Side": "Tail_Side",
    }
    df = df.rename(columns=rename_map)
    for column in list(df.columns):
        if column.startswith("TailAngle "):
            df = df.rename(columns={column: column.replace("TailAngle ", "TailAngle_")})
    drop_cols = [col for col in ("timeRangeStart", "timeRangeEnd") if col in df.columns]
    if drop_cols:
        df = df.drop(columns=drop_cols)
    time_range_df = normalize_time_range_columns(len(df), time_ranges)
    df = pd.concat([df, time_range_df], axis=1)
    return df


def align_new_dataframe(new_df: pd.DataFrame, target_length: int) -> pd.DataFrame:
    """
    Align the new DataFrame to match the length of the legacy one.

    The new pipeline may produce a few extra rows compared to the legacy one.
    This function trims the new DataFrame to the same length as the legacy
    one for a row-by-row comparison.

    Args:
        new_df: The DataFrame from the new calculation pipeline.
        target_length: The number of rows in the legacy DataFrame.

    Returns:
        A trimmed pandas DataFrame.

    Raises:
        ValueError: If the new DataFrame is shorter than the legacy one.
    """
    if len(new_df) < target_length:
        raise ValueError(
            f"New calculations produced {len(new_df)} rows, fewer than legacy output ({target_length})."
        )
    trimmed = new_df.iloc[:target_length].reset_index(drop=True)
    return trimmed


def column_is_numeric(series: pd.Series) -> bool:
    """
    Check if a pandas Series can be treated as numeric.

    This is more robust than just checking `series.dtype` because columns
    containing a mix of numbers and `None`/`NaN` may have an 'object' dtype.

    Args:
        series: The pandas Series to check.

    Returns:
        True if the series is numeric, False otherwise.
    """
    if pd.api.types.is_numeric_dtype(series):
        return True
    coerced = pd.to_numeric(series, errors="coerce")
    return coerced.notna().any()


def compare_columns(
    new_series: pd.Series,
    legacy_series: pd.Series,
    atol: float,
    rtol: float,
) -> ColumnComparison:
    """
    Compare two pandas Series and summarize the differences.

    This function handles both numeric and categorical data. For numeric
    columns, it uses `np.isclose` with the specified tolerances. For others,
    it compares the string representations.

    Args:
        new_series: The column from the new DataFrame.
        legacy_series: The column from the legacy DataFrame.
        atol: The absolute tolerance for numeric comparison.
        rtol: The relative tolerance for numeric comparison.

    Returns:
        A ColumnComparison object summarizing the differences.
    """
    name = new_series.name
    if column_is_numeric(new_series) or column_is_numeric(legacy_series):
        new_numeric = pd.to_numeric(new_series, errors="coerce")
        legacy_numeric = pd.to_numeric(legacy_series, errors="coerce")
        diff = np.abs(new_numeric - legacy_numeric)
        mismatches = int(
            (~np.isclose(new_numeric, legacy_numeric, rtol=rtol, atol=atol, equal_nan=True)).sum()
        )
        if np.isnan(diff).all():
            max_abs_diff = None
        else:
            max_abs_diff = float(np.nanmax(diff))
        sample = (
            diff[~np.isclose(new_numeric, legacy_numeric, rtol=rtol, atol=atol, equal_nan=True)]
            .index[:5]
            .tolist()
            if mismatches
            else None
        )
        kind = "numeric"
        return ColumnComparison(name, kind, mismatches, max_abs_diff, sample)
    new_values = new_series.fillna("").astype(str)
    legacy_values = legacy_series.fillna("").astype(str)
    diff_mask = new_values != legacy_values
    mismatches = int(diff_mask.sum())
    sample = diff_mask[diff_mask].index[:5].tolist() if mismatches else None
    return ColumnComparison(name, "categorical", mismatches, None, sample)


def compare_dataframes(
    new_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
    atol: float,
    rtol: float,
) -> Tuple[List[ColumnComparison], List[str], List[str]]:
    """
    Compare two DataFrames column by column.

    This function identifies shared columns, columns unique to the new DataFrame,
    and columns unique to the legacy DataFrame. It then compares the
    shared columns.

    Args:
        new_df: The DataFrame from the new pipeline.
        legacy_df: The DataFrame from the legacy pipeline.
        atol: The absolute tolerance for numeric comparison.
        rtol: The relative tolerance for numeric comparison.

    Returns:
        A tuple containing:
        - A list of ColumnComparison objects for each shared column.
        - A list of column names only present in the new DataFrame.
        - A list of column names only present in the legacy DataFrame.
    """
    new_columns = set(new_df.columns)
    legacy_columns = set(legacy_df.columns)
    shared_columns = sorted(new_columns & legacy_columns)
    comparisons = [
        compare_columns(new_df[col], legacy_df[col], atol, rtol) for col in shared_columns
    ]
    only_new = sorted(new_columns - legacy_columns)
    only_legacy = sorted(legacy_columns - new_columns)
    return comparisons, only_new, only_legacy


def export_outputs(
    export_dir: Path,
    new_df: pd.DataFrame,
    legacy_df: pd.DataFrame,
) -> None:
    """
    Save the new and legacy DataFrames to CSV files for inspection.

    Args:
        export_dir: The directory in which to save the CSV files.
        new_df: The DataFrame from the new pipeline.
        legacy_df: The DataFrame from the legacy pipeline.
    """
    export_dir.mkdir(parents=True, exist_ok=True)
    new_path = export_dir / "new_results.csv"
    legacy_path = export_dir / "legacy_results.csv"
    new_df.to_csv(new_path, index=False)
    legacy_df.to_csv(legacy_path, index=False)
    print(f"Saved new results to {new_path}")
    print(f"Saved legacy results to {legacy_path}")


def print_report(
    comparisons: Sequence[ColumnComparison],
    only_new: Sequence[str],
    only_legacy: Sequence[str],
) -> None:
    """
    Print a human-readable report of the comparison results.

    Args:
        comparisons: A sequence of ColumnComparison objects.
        only_new: A sequence of column names only present in the new output.
        only_legacy: A sequence of column names only present in the legacy output.
    """
    matched = [c for c in comparisons if c.mismatches == 0]
    mismatched = [c for c in comparisons if c.mismatches > 0]

    print("=== Comparison Summary ===")
    print(f"Shared columns: {len(comparisons)}")
    print(f"Perfect matches: {len(matched)}")
    print(f"Columns with differences: {len(mismatched)}")

    if mismatched:
        print("\nColumns with discrepancies:")
        for comp in mismatched:
            if comp.kind == "numeric":
                max_diff = "n/a" if comp.max_abs_diff is None else f"{comp.max_abs_diff:.6g}"
                print(
                    f"  - {comp.name} ({comp.kind}): {comp.mismatches} mismatched rows "
                    f"(max abs diff {max_diff})"
                )
            else:
                print(
                    f"  - {comp.name} ({comp.kind}): {comp.mismatches} mismatched rows"
                )
            if comp.sample_indices:
                print(f"      sample row indices: {comp.sample_indices}")

    if only_new:
        print("\nColumns only in new output:")
        for col in only_new:
            print(f"  - {col}")

    if only_legacy:
        print("\nColumns only in legacy output:")
        for col in only_legacy:
            print(f"  - {col}")


def main() -> None:
    """
    Main entry point for the script.

    Parses arguments, runs both pipelines, normalizes the outputs,
    compares the results, and prints a report.
    """
    args = parse_args()
    csv_path = Path(args.csv).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve()
    legacy_root = Path(args.legacy_root).expanduser().resolve()

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if not (legacy_root / "utils" / "mainCalculation.py").exists():
        raise FileNotFoundError(
            f"Legacy pipeline not found under {legacy_root}. "
            "Pass --legacy-root if the repository layout differs."
        )

    config = load_config(config_path)

    print("Running new calculation pipeline...")
    new_df_raw = run_new_pipeline(csv_path, config)

    print("Running legacy calculation pipeline...")
    legacy_raw, time_ranges = run_legacy_pipeline(csv_path, config, legacy_root)
    legacy_df = normalize_legacy_dataframe(legacy_raw, time_ranges)

    new_df = align_new_dataframe(new_df_raw, len(legacy_df))

    comparisons, only_new, only_legacy = compare_dataframes(
        new_df, legacy_df, args.atol, args.rtol
    )

    print_report(comparisons, only_new, only_legacy)

    if args.export_dir:
        export_outputs(Path(args.export_dir).expanduser().resolve(), new_df, legacy_df)


if __name__ == "__main__":
    main()
