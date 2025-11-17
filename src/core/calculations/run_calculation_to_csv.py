#!/usr/bin/env python3
"""Run the zebrafish calculation pipeline and export results as CSV.

Example command:
    python src/core/calculations/run_calculation_to_csv.py --csv data/samples/csv/correct_format.csv --config data/samples/jsons/BaseConfig.json --output calculations/tests/calculated_data.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SRC_ROOT = Path(__file__).resolve().parents[3]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from src.core.parsing.Parser import parse_dlc_csv
from src.core.calculations.Driver import run_calculations


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def determine_output_path(csv_path: Path, output_arg: str | None) -> Path:
    if output_arg:
        return resolve_path(output_arg)
    return csv_path.with_name(f"{csv_path.stem}_results.csv")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the cv_zebrafish calculation pipeline and export the results as CSV."
    )
    parser.add_argument(
        "--csv",
        required=True,
        help="Path to the DeepLabCut CSV file to process."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON configuration file describing points and parameters."
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path for the output CSV (defaults to <input_stem>_results.csv)."
    )

    args = parser.parse_args()

    csv_path = resolve_path(args.csv)
    config_path = resolve_path(args.config)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    config = load_config(config_path)
    parsed_points = parse_dlc_csv(str(csv_path), config)
    results_df = run_calculations(parsed_points, config)

    output_path = determine_output_path(csv_path, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_path, index=False)

    print(f"Saved calculation results to {output_path}")


if __name__ == "__main__":
    main()
