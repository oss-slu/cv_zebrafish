"""Tests for the fin-free adult zebrafish calculation path."""

import numpy as np

from src.core.calculations.Driver import run_adult_calculations

N_FRAMES = 6
N_SPINE_POINTS = 10


def make_spine(conf=1.0):
    """Build a straight spine along the x-axis with constant confidence."""
    return [
        {
            "x": np.full(N_FRAMES, float(i)),
            "y": np.zeros(N_FRAMES),
            "conf": np.full(N_FRAMES, conf),
        }
        for i in range(N_SPINE_POINTS)
    ]


def test_adult_output_has_eight_body_angles():
    df = run_adult_calculations({"spine": make_spine()})
    for i in range(1, 9):
        assert f"BodyAngle_{i}" in df.columns
    assert "BodyAngle_0" not in df.columns
    assert "BodyAngle_9" not in df.columns
    assert len(df) == N_FRAMES


def test_adult_output_has_no_fin_columns():
    df = run_adult_calculations({"spine": make_spine()})
    assert not [c for c in df.columns if c.startswith(("LF_", "RF_"))]


def test_adult_head_yaw_uses_p0_to_p1():
    spine = make_spine()
    spine[1]["y"] = np.full(N_FRAMES, 1.0)  # p1 is up and to the right of p0
    df = run_adult_calculations({"spine": spine})
    assert np.allclose(df["HeadYaw"], -45.0)


def test_low_confidence_points_become_nan():
    spine = make_spine()
    spine[0]["conf"][2] = 0.1
    df = run_adult_calculations({"spine": spine}, min_accepted_confidence=0.3)
    assert np.isnan(df["HeadYaw"].iloc[2])
    assert np.isnan(df["BodyAngle_1"].iloc[2])
    assert not np.isnan(df["HeadYaw"].iloc[1])


def test_confidence_masking_does_not_modify_input():
    spine = make_spine()
    spine[0]["conf"][2] = 0.1
    run_adult_calculations({"spine": spine}, min_accepted_confidence=0.3)
    assert spine[0]["x"][2] == 0.0