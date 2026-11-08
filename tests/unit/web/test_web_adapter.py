"""Tests for the web prototype adapter (spike #136). No web framework needed."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

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
    data = SAMPLE_CSV_PATH.read_bytes()

    # Load 2 fish through the web adapter
    loaded, failures = analyze_fish_files(
        [("fish_A.csv", data), ("fish_B.csv", data)],
        config,
    )
    assert not failures
    assert len(loaded) == 2
    assert loaded[0].label == "fish_A"
    assert loaded[1].label == "fish_B"

    # Direct desktop core comparison table
    expected_table = build_comparison_table(loaded)
    web_table = build_comparison_table(loaded)
    pd.testing.assert_frame_equal(web_table, expected_table)

    # Check exported CSV bytes contains headers and data
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
