#!/usr/bin/env python3
"""Utility script to run the zebrafish pipeline and persist Plotly graphs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cvzebrafish.core.calculations.Driver import run_calculations
from cvzebrafish.core.parsing.Parser import parse_dlc_csv
from cvzebrafish.platform.paths import default_sample_config, default_sample_csv
from cvzebrafish.viz.figures.outputDisplay import make_outputs


def _default_paths(repo_root: Path) -> tuple[Path, Path, Path]:
    """Return default csv, config, and output folders based on the repo root."""
    csv_path = default_sample_csv()
    config_path = default_sample_config()
    output_dir = repo_root / "results"
    return csv_path, config_path, output_dir


def parse_args() -> argparse.Namespace:
    repo_root = REPO_ROOT
    default_csv, default_config, default_output = _default_paths(repo_root)

    parser = argparse.ArgumentParser(
        description="Run calculations and generate zebrafish graphs."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=default_csv,
        help=f"Path to DLC CSV input (default: {default_csv})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=default_config,
        help=f"Path to config JSON (default: {default_config})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_output,
        help=f"Directory to save generated assets (default: {default_output})",
    )
    parser.add_argument(
        "--skip-heatmap",
        action="store_true",
        help="Disable the movement heatmap export.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = REPO_ROOT

    if not args.csv.is_file():
        raise FileNotFoundError(f"DLC csv not found at '{args.csv}'")
    if not args.config.is_file():
        raise FileNotFoundError(f"Config json not found at '{args.config}'")

    with args.config.open("r", encoding="utf-8") as fh:
        config = json.load(fh)

    # Ensure graph exports land in a writable folder and skip Excel if dependencies are missing.
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    config["results_path"] = str(output_dir)
    config["save_excel"] = False

    shown_outputs = {
        "show_angle_and_distance_plot": True,
        "show_spines": True,
        "show_movement_track": True,
        "show_head_plot": True,
    }
    if args.skip_heatmap:
        shown_outputs["show_heatmap"] = False
    else:
        shown_outputs["show_heatmap"] = True
    config["shown_outputs"] = {**shown_outputs, **config.get("shown_outputs", {})}

    parsed_points = parse_dlc_csv(str(args.csv), config)
    result_df = run_calculations(parsed_points, config)

    graph_result = make_outputs(
        result_df,
        config,
        parsed_points=parsed_points,
        save_images=True,
        save_html=False,
    )

    print("[INFO] Graphs generated:")
    for name, artifact in graph_result.artifacts.items():
        location = artifact.image_path or "in-memory"
        print(f"  - {name}: {location}")

    if graph_result.output_folder:
        relative = graph_result.output_folder.replace(str(repo_root), ".")
        print(f"[INFO] Assets saved under: {relative}")


if __name__ == "__main__":
    main()
