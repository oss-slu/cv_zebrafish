#!/usr/bin/env python3
"""Generate a CSV/JSON bundle that preserves both raw DLC pose data and derived metrics.

The legacy Bruce visualization pipeline (`outputDisplay.py`) consumed a CSV that
contained: (a) raw DeepLabCut (DLC) measurements for every tracked point,
(b) per-frame derived metrics (fin angles, tail distances, head yaw, spine angles),
and (c) bout metadata (fin peaks, time ranges, video context). Our modern
`run_calculation_to_csv.py` only emits the derived metrics, making it impossible
to recreate graphs such as `plotSpines`, movement overlays, and heatmaps without
re-reading the original DLC CSV.

This script runs the same calculation pipeline but augments its output so that
all three data categories live in the exported artifacts:

1. **Calculated metrics** — straight from `run_calculations` (fin/tail angles,
   distances, head yaw, `TailAngle_*`, bout ranges, peak buffers, etc.).
2. **Raw DLC coordinates** — flattened into `Spine_*`, `LeftFin_*`, `RightFin_*`,
   `Tail_*`, and `DLC_HeadPX/DLC_TailPX` columns so every point's x/y/confidence
   survives in the CSV.
3. **Graph metadata** — serialized spine JSON per frame, video path, scale factor,
   and optional companion JSON with the canonical time ranges and config source.

Example:

    python calculations/export_enriched_results.py \
        --csv data_schema_validation/sample_inputs/csv/correct_format.csv \
        --config data_schema_validation/sample_inputs/jsons/BaseConfig.json \
        --output calculations/tests/calculated_data_enriched.csv \
        --extra-json calculations/tests/calculated_data_enriched.meta.json

Downstream Plotly code can now read the enriched CSV (plus optional metadata JSON)
as a drop-in replacement for the legacy artifacts without touching the original
DLC files.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calculations.utils.Parser import parse_dlc_csv  # noqa: E402
from calculations.utils.Driver import run_calculations  # noqa: E402


def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def determine_output_path(csv_path: Path, output_arg: str | None) -> Path:
    if output_arg:
        return resolve_path(output_arg)
    return csv_path.with_name(f"{csv_path.stem}_results_enriched.csv")


def _safe_number(value: float | int) -> float | None:
    if value is None:
        return None
    try:
        if np.isnan(value):
            return None
    except TypeError:
        pass
    return float(value)


def build_point_dataframe(parsed_points: Dict[str, any], config: dict) -> pd.DataFrame:
    """Flatten DLC point arrays into columns (x/y/conf per label)."""
    n_frames = len(parsed_points["spine"][0]["x"])
    data: Dict[str, Iterable[float]] = {"Time": np.arange(n_frames)}

    def add_group(prefix: str, labels: List[str], arrs: List[dict]) -> None:
        for label, arr in zip(labels, arrs):
            base = f"{prefix}_{label}"
            data[f"{base}_x"] = arr["x"]
            data[f"{base}_y"] = arr["y"]
            data[f"{base}_conf"] = arr["conf"]

    add_group("Spine", config["points"]["spine"], parsed_points["spine"])
    add_group("LeftFin", config["points"]["left_fin"], parsed_points["left_fin"])
    add_group("RightFin", config["points"]["right_fin"], parsed_points["right_fin"])
    add_group("Tail", config["points"]["tail"], parsed_points["tail"])

    # Convenience columns for head/tail tips in pixel space (keep distinct names to avoid clashes).
    data["DLC_HeadPX"] = parsed_points["head"]["x"]
    data["DLC_HeadPY"] = parsed_points["head"]["y"]
    data["DLC_HeadPConf"] = parsed_points["head"]["conf"]
    data["DLC_TailPX"] = parsed_points["tp"]["x"]
    data["DLC_TailPY"] = parsed_points["tp"]["y"]
    data["DLC_TailPConf"] = parsed_points["tp"]["conf"]

    return pd.DataFrame(data)


def build_spine_json_column(parsed_points: Dict[str, any], config: dict) -> List[str]:
    """Serialize per-frame spine coordinates so downstream code can load them directly."""
    labels = config["points"]["spine"]
    spine = parsed_points["spine"]
    n_frames = len(spine[0]["x"])
    serialized: List[str] = []
    for frame_idx in range(n_frames):
        frame_points = []
        for label, arr in zip(labels, spine):
            frame_points.append(
                {
                    "label": label,
                    "x": _safe_number(arr["x"][frame_idx]),
                    "y": _safe_number(arr["y"][frame_idx]),
                    "conf": _safe_number(arr["conf"][frame_idx]),
                }
            )
        serialized.append(json.dumps(frame_points))
    return serialized


def extract_time_ranges(df: pd.DataFrame) -> List[List[int]]:
    """Read time-range columns (row 0) back into [[start, end], ...] pairs."""
    start_cols = sorted(c for c in df.columns if c.startswith("timeRangeStart_"))
    ranges: List[List[int]] = []
    for col in start_cols:
        suffix = col.replace("timeRangeStart_", "")
        end_col = f"timeRangeEnd_{suffix}"
        if end_col not in df.columns:
            continue
        start_val = df.at[0, col]
        end_val = df.at[0, end_col]
        if start_val in ("", None) or end_val in ("", None):
            continue
        try:
            start_int = int(float(start_val))
            end_int = int(float(end_val))
        except (TypeError, ValueError):
            continue
        ranges.append([start_int, end_int])
    return ranges


def enrich_results_dataframe(
    results_df: pd.DataFrame,
    parsed_points: Dict[str, any],
    config: dict,
) -> pd.DataFrame:
    """Attach pixel-space columns, serialized spine, and constant metadata."""
    enriched = results_df.copy()
    enriched["HeadPX"] = parsed_points["head"]["x"]
    enriched["HeadPY"] = parsed_points["head"]["y"]
    enriched["TailPX"] = parsed_points["tp"]["x"]
    enriched["TailPY"] = parsed_points["tp"]["y"]
    enriched["spine_points_json"] = build_spine_json_column(parsed_points, config)

    video_file = config.get("file_inputs", {}).get("video", "")
    enriched["videoFile"] = video_file
    vp = config.get("video_parameters", {})
    enriched["pixel_scale_factor"] = vp.get("pixel_scale_factor", "")
    return enriched


def write_metadata_json(
    output_path: Path,
    enriched_df: pd.DataFrame,
    config_path: Path,
    config: dict,
) -> None:
    payload = {
        "config_source": str(config_path),
        "video_file": config.get("file_inputs", {}).get("video", ""),
        "pixel_scale_factor": config.get("video_parameters", {}).get("pixel_scale_factor"),
        "dish_diameter_m": config.get("video_parameters", {}).get("dish_diameter_m"),
        "pixel_diameter": config.get("video_parameters", {}).get("pixel_diameter"),
        "time_ranges": extract_time_ranges(enriched_df),
    }
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the cv_zebrafish calculation pipeline and export an enriched CSV."
    )
    parser.add_argument("--csv", required=True, help="Path to the DeepLabCut CSV file to process.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON configuration file describing points and parameters.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path for the enriched output CSV (defaults to <input_stem>_results_enriched.csv).",
    )
    parser.add_argument(
        "--extra-json",
        default=None,
        help="Optional path for a companion JSON artifact with metadata (video path, scale, time ranges).",
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
    enriched_df = enrich_results_dataframe(results_df, parsed_points, config)

    raw_points_df = build_point_dataframe(parsed_points, config)
    merged_df = pd.concat([enriched_df, raw_points_df.drop(columns=["Time"])], axis=1)

    output_path = determine_output_path(csv_path, args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged_df.to_csv(output_path, index=False)
    print(f"Saved enriched calculation results to {output_path}")

    if args.extra_json:
        metadata_path = resolve_path(args.extra_json)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        write_metadata_json(metadata_path, merged_df, config_path, config)
        print(f"Wrote metadata artifact to {metadata_path}")


if __name__ == "__main__":
    main()
