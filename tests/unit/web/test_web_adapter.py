"""Tests for the web prototype adapter (spike #136). No web framework needed."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "web_prototype"))

from adapter import (  # noqa: E402
    SAMPLE_CSV_PATH,
    analyze_csv_bytes,
    analyze_fish_files,
    build_comparison_table,
    comparison_table_csv_bytes,
    fin_tail_figure,
    load_sample_config,
    summary_table,
)
from src.core.analysis.summary_statistics import compute_summary_statistics_df  # noqa: E402
from src.core.calculations.Driver import run_calculations  # noqa: E402
from src.core.parsing.Parser import parse_dlc_csv  # noqa: E402


def test_upload_matches_desktop_pipeline():
    config = load_sample_config()
    result = analyze_csv_bytes(SAMPLE_CSV_PATH.read_bytes(), config, filename="sample.csv")

    assert result.ok, result.errors
    expected = run_calculations(parse_dlc_csv(str(SAMPLE_CSV_PATH), config), config)
    pd.testing.assert_frame_equal(result.results, expected)


def test_rejects_non_csv():
    result = analyze_csv_bytes(b"\x89HDF", load_sample_config(), filename="mouse.h5")
    assert not result.ok
    assert ".csv" in result.errors[0]


def test_reports_invalid_csv_instead_of_raising():
    result = analyze_csv_bytes(b"not,a,deeplabcut\nfile,at,all\n", load_sample_config(), filename="bad.csv")
    assert not result.ok
    assert result.errors


def test_summary_and_fin_tail_figure():
    config = load_sample_config()
    results = analyze_csv_bytes(SAMPLE_CSV_PATH.read_bytes(), config).results

    summary = summary_table(results)
    assert set(summary.columns) == {"parameter", "mean", "median", "units"}
    assert set(summary["parameter"]) >= {"LF_Angle", "RF_Angle", "Tail_Distance"}

    fig, warnings = fin_tail_figure(results, {**config, "time_ranges": [[0, 200]]})
    assert fig is not None, warnings
    assert len(fig.data) >= 3


def test_web_multi_fish_comparison_matches_core():
    config = load_sample_config()
    lines = SAMPLE_CSV_PATH.read_text(encoding="utf-8").splitlines()
    data_a = "\n".join(lines).encode()
    data_b = "\n".join(lines[:103]).encode()  # 3 header lines + 100 frames

    # Load 2 distinct fish through the web adapter
    loaded, failures = analyze_fish_files(
        [("fish_A.csv", data_a), ("fish_B.csv", data_b)],
        config,
    )
    assert not failures
    assert len(loaded) == 2
    assert loaded[0].label == "fish_A"
    assert loaded[1].label == "fish_B"
    assert len(loaded[0].results) == 5351
    assert len(loaded[1].results) == 100

    # Build comparison table via adapter
    web_table = build_comparison_table(loaded)

    # Directly verify against desktop core compute_summary_statistics_df for each fish
    for fish in loaded:
        expected_summary = compute_summary_statistics_df(fish.results).set_index("parameter")
        for param in expected_summary.index:
            for stat in ("mean", "median"):
                row = web_table[
                    (web_table["Parameter"] == param) & (web_table["Statistic"] == stat)
                ]
                assert not row.empty, f"Missing row for {param} {stat}"
                cell_val = row.iloc[0][fish.label]
                expected_val = expected_summary.at[param, stat]
                if pd.isna(expected_val):
                    assert pd.isna(cell_val)
                else:
                    assert cell_val == pytest.approx(expected_val)

    # Check exported CSV bytes contains headers and data for both fish
    csv_bytes = comparison_table_csv_bytes(web_table, loaded)
    assert b"Fish ID" in csv_bytes
    assert b"Source file" in csv_bytes
    assert b"fish_A" in csv_bytes
    assert b"fish_B" in csv_bytes


def test_rejects_file_missing_config_bodyparts():
    # A DeepLabCut CSV with other body parts (e.g. a mouse) must not "succeed" with empty results.
    header = (
        "scorer,DLC,DLC,DLC,DLC,DLC,DLC\n"
        "bodyparts,nose,nose,nose,tail_base,tail_base,tail_base\n"
        "coords,x,y,likelihood,x,y,likelihood\n"
    )
    rows = "".join(f"{i},{i}.0,{i}.0,0.99,{i}.5,{i}.5,0.98\n" for i in range(20))
    result = analyze_csv_bytes((header + rows).encode(), load_sample_config(), filename="mouse.csv")

    assert not result.ok
    assert "aren't in this file" in result.errors[0]
    assert "nose" in result.errors[0]
