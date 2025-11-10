#!/usr/bin/env python3
"""
Compare legacy Bruce pipeline calculations with the new cv_zebrafish implementation.
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
    name: str
    kind: str
    mismatches: int
    max_abs_diff: Optional[float] = None
    sample_indices: Optional[List[int]] = None


def parse_args() -> argparse.Namespace:
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
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(legacy_root) not in sys.path:
        sys.path.insert(0, str(legacy_root))


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def run_new_pipeline(csv_path: Path, config: dict) -> pd.DataFrame:
    from calculations.utils.Parser import parse_dlc_csv
    from calculations.utils.Driver import run_calculations

    parsed_points = parse_dlc_csv(str(csv_path), config)
    new_df = run_calculations(parsed_points, config)
    return new_df.reset_index(drop=True)


def run_legacy_pipeline(
    csv_path: Path, config: dict, legacy_root: Optional[Path] = None
) -> Tuple[pd.DataFrame, List[List[int]]]:
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
    if len(new_df) < target_length:
        raise ValueError(
            f"New calculations produced {len(new_df)} rows, fewer than legacy output ({target_length})."
        )
    trimmed = new_df.iloc[:target_length].reset_index(drop=True)
    return trimmed


def column_is_numeric(series: pd.Series) -> bool:
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
