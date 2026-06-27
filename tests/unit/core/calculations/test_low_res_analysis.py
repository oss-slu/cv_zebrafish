"""Unit tests for low-resolution kinematic analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.calculations.low_res_analysis import (
    ActiveRestParams,
    classify_active_rest_frames,
    compute_low_res_summary,
    enrich_results_dataframe,
    per_frame_displacement_m,
    resolve_point_coords,
    total_path_length_m,
)


def _sample_config():
    return {
        "points": {
            "spine": ["Head", "T1", "ET"],
            "tail": ["T1", "ET"],
            "right_fin": ["RF1", "RF2"],
            "left_fin": ["LF1", "LF2"],
            "head": {"pt1": "Head", "pt2": "SB"},
        },
        "video_parameters": {
            "pixel_diameter": 1000,
            "dish_diameter_m": 0.02,
            "recorded_framerate": 100.0,
            "pixel_scale_factor": 1.0,
        },
        "low_res_analysis": {
            "enabled": True,
            "track_point_distance_speed": "Head",
            "active_rest": {
                "track_point": "Head",
                "min_total_movement_m": 0.001,
                "min_frame_displacement_m": 0.00005,
                "movement_fraction_of_mean": 0.5,
                "min_rest_frames_to_split_bout": 3,
            },
        },
    }


def _parsed_points(n: int = 20):
  x = np.linspace(0, 50, n)
  y = np.zeros(n)
  pt = {"x": x, "y": y, "conf": np.ones(n)}
  return {
      "spine": [pt, pt, pt],
      "tail": [pt, pt],
      "right_fin": [pt, pt],
      "left_fin": [pt, pt],
      "clp1": pt,
      "clp2": pt,
      "head": pt,
      "tp": pt,
      "tailPoints": ["T1", "ET"],
  }


def test_per_frame_displacement_and_path_length():
    x = [0.0, 10.0, 20.0, 30.0]
    y = [0.0, 0.0, 0.0, 0.0]
    steps = per_frame_displacement_m(x, y, scale_factor=0.001)
    assert steps[0] == 0.0
    assert np.isclose(steps[1], 0.01)
    assert np.isclose(total_path_length_m(steps), 0.03)


def test_resolve_point_coords_spine_label():
    parsed = _parsed_points()
    cfg = _sample_config()
    coords = resolve_point_coords(parsed, cfg, "Head")
    assert coords is not None
    assert len(coords["x"]) == 20


def test_classify_active_rest_merges_short_gaps():
    steps = np.zeros(30)
    steps[5:8] = 0.01
    steps[20:25] = 0.01
    params = ActiveRestParams(
        min_total_movement_m=0.001,
        min_frame_displacement_m=0.005,
        movement_fraction_of_mean=0.3,
        min_rest_frames_to_split_bout=5,
    )
    states, bouts = classify_active_rest_frames(steps, params)
    assert int(np.sum(states)) > 0
    assert len(bouts) >= 1


def test_classify_active_rest_all_rest_when_below_min_total():
    steps = np.full(10, 0.0)
    steps[1:] = 1e-9
    params = ActiveRestParams(min_total_movement_m=1.0)
    states, bouts = classify_active_rest_frames(steps, params)
    assert int(np.sum(states)) == 0
    assert bouts == []


def test_compute_low_res_summary_distance_and_speed():
    parsed = _parsed_points()
    summary = compute_low_res_summary(parsed, _sample_config())
    assert summary.distance_covered_m > 0
    assert summary.mean_speed_m_s > 0
    assert summary.active_bout_count >= 1


def test_enrich_results_dataframe_adds_columns():
    parsed = _parsed_points()
    df = pd.DataFrame({"Time": np.arange(20)})
    out = enrich_results_dataframe(parsed, df, _sample_config())
    assert "ActiveRest_State" in out.columns
    assert "LowRes_InstantSpeed_m_s" in out.columns
    assert "low_res_summary" in out.attrs
