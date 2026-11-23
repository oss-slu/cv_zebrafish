from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.core.parsing.adult_loader import (
    get_required_bodyparts,
    merge_adult_dlc_csvs,
)
from src.core.parsing.Parser import parse_adult_dlc_csv

REPO_ROOT = Path(__file__).resolve().parents[4]
ADULT_CONFIG_PATH = REPO_ROOT / "data" / "samples" / "jsons" / "AdultConfig.json"


def _write_dlc_csv(
    path: Path,
    scorer: str,
    bodyparts: list[str],
    n_frames: int,
    base_val: float = 1.0,
) -> Path:
    """Helper to generate a valid DeepLabCut CSV file."""
    col_scorer = ["scorer"]
    col_bp = ["bodyparts"]
    col_coords = ["coords"]
    for bp in bodyparts:
        col_scorer.extend([scorer, scorer, scorer])
        col_bp.extend([bp, bp, bp])
        col_coords.extend(["x", "y", "likelihood"])

    lines = [
        ",".join(col_scorer),
        ",".join(col_bp),
        ",".join(col_coords),
    ]

    for f in range(n_frames):
        row = [str(f)]
        for i, bp in enumerate(bodyparts):
            x = base_val + f + i * 0.1
            y = base_val * 2 + f + i * 0.1
            conf = 0.95
            row.extend([f"{x:.2f}", f"{y:.2f}", f"{conf:.2f}"])
        lines.append(",".join(row))

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


@pytest.fixture
def adult_config():
    return json.loads(ADULT_CONFIG_PATH.read_text(encoding="utf-8"))


def test_successful_merge_with_differing_scorers(tmp_path: Path):
    """body_points (p0..p9) and caudal_fin should merge cleanly on frame index even if scorers differ."""
    bp_names = [f"p{i}" for i in range(10)]
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "DLC_model_body_1100000", bp_names, n_frames=5, base_val=10.0)
    caudal_csv = _write_dlc_csv(tmp_path / "caudal.csv", "DLC_model_tail_600000", ["caudal_fin"], n_frames=5, base_val=50.0)

    merged = merge_adult_dlc_csvs(body_csv, caudal_csv)

    assert len(merged) == 5
    bps = list(merged.columns.get_level_values("bodyparts").unique())
    assert bps == bp_names + ["caudal_fin"]

    # Verify column count: (10 body points + 1 caudal fin) * 3 coords = 33
    assert merged.shape[1] == 33

    # Check coordinate values
    p0_x = merged.xs(("p0", "x"), level=("bodyparts", "coords"), axis=1).iloc[:, 0].values
    assert np.allclose(p0_x, [10.0, 11.0, 12.0, 13.0, 14.0])

    caudal_x = merged.xs(("caudal_fin", "x"), level=("bodyparts", "coords"), axis=1).iloc[:, 0].values
    assert np.allclose(caudal_x, [50.0, 51.0, 52.0, 53.0, 54.0])


def test_merge_with_optional_caudal_fin_omitted(tmp_path: Path):
    """Calling merge_adult_dlc_csvs without caudal_fin should succeed and return body_df."""
    bp_names = [f"p{i}" for i in range(10)]
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "DLC_model_body", bp_names, n_frames=4)

    merged = merge_adult_dlc_csvs(body_csv)
    assert len(merged) == 4
    bps = list(merged.columns.get_level_values("bodyparts").unique())
    assert bps == bp_names


def test_frame_count_mismatch_raises_error(tmp_path: Path):
    """Mismatched frame counts must raise an explicit readable ValueError."""
    bp_names = [f"p{i}" for i in range(10)]
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "DLC_model_body", bp_names, n_frames=10)
    caudal_csv = _write_dlc_csv(tmp_path / "caudal.csv", "DLC_model_tail", ["caudal_fin"], n_frames=8)

    with pytest.raises(ValueError, match="Frame count mismatch: body_points has 10 frames, while caudal_fin has 8 frames"):
        merge_adult_dlc_csvs(body_csv, caudal_csv)


def test_invalid_csv_raises_error(tmp_path: Path):
    """Corrupted CSV (e.g. wrong column structure) must trigger verify_deeplabcut_csv error."""
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("scorer,p0,p0\nbodyparts,p0,p0\ncoords,x,invalid_col\n0,1.0,2.0\n", encoding="utf-8")
    valid_csv = _write_dlc_csv(tmp_path / "valid.csv", "model", ["caudal_fin"], n_frames=1)

    with pytest.raises(ValueError, match="body_points CSV verification failed"):
        merge_adult_dlc_csvs(bad_csv, valid_csv)

    with pytest.raises(ValueError, match="caudal_fin CSV verification failed"):
        merge_adult_dlc_csvs(valid_csv, bad_csv)


def test_missing_required_bodyparts_raises_error(tmp_path: Path, adult_config):
    """If the config requires bodyparts not found in the merged data, raise clear error (#143)."""
    # Create body CSV missing p9
    incomplete_bps = [f"p{i}" for i in range(9)]  # p0..p8 only
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "model_body", incomplete_bps, n_frames=3)
    caudal_csv = _write_dlc_csv(tmp_path / "caudal.csv", "model_tail", ["caudal_fin"], n_frames=3)

    with pytest.raises(ValueError, match="Missing required bodyparts in merged adult CSV: \\['p9'\\]"):
        merge_adult_dlc_csvs(body_csv, caudal_csv, config=adult_config)


def test_missing_caudal_fin_when_required_by_config_raises_error(tmp_path: Path, adult_config):
    """If config requires caudal_fin but caudal_fin CSV is omitted, raise clear error (#143)."""
    body_bps = [f"p{i}" for i in range(10)]
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "model_body", body_bps, n_frames=3)

    with pytest.raises(ValueError, match="Missing required bodyparts in merged adult CSV: \\['caudal_fin'\\]"):
        merge_adult_dlc_csvs(body_csv, config=adult_config)


def test_unified_scorer_option(tmp_path: Path):
    """unified_scorer parameter should normalize top-level scorer across all columns."""
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "scorer_1", ["p0", "p1"], n_frames=2)
    caudal_csv = _write_dlc_csv(tmp_path / "caudal.csv", "scorer_2", ["caudal_fin"], n_frames=2)

    merged = merge_adult_dlc_csvs(body_csv, caudal_csv, unified_scorer="UnifiedModel")
    scorers = list(merged.columns.get_level_values("scorer").unique())
    assert scorers == ["UnifiedModel"]


def test_parse_adult_dlc_csv_integration(tmp_path: Path, adult_config):
    """parse_adult_dlc_csv parses merged DataFrames into standard inputValues dictionary."""
    bp_names = [f"p{i}" for i in range(10)]
    body_csv = _write_dlc_csv(tmp_path / "body.csv", "scorer_body", bp_names, n_frames=6)
    caudal_csv = _write_dlc_csv(tmp_path / "caudal.csv", "scorer_tail", ["caudal_fin"], n_frames=6)

    input_values = parse_adult_dlc_csv(body_csv, caudal_csv, config=adult_config)

    assert "spine" in input_values
    assert len(input_values["spine"]) == 10
    assert len(input_values["spine"][0]["x"]) == 6

    assert "tail" in input_values
    assert len(input_values["tail"]) == 1
    assert len(input_values["tail"][0]["x"]) == 6

    assert "head" in input_values
    assert np.allclose(input_values["head"]["x"], input_values["spine"][0]["x"])


def test_get_required_bodyparts(adult_config):
    required = get_required_bodyparts(adult_config)
    assert "p0" in required
    assert "p9" in required
    assert "caudal_fin" in required
    # AdultConfig has empty left_fin/right_fin, so no fins should be in required
    assert not any("fin" in p and p != "caudal_fin" for p in required)
