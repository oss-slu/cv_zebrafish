#!/usr/bin/env python3
"""Unit tests for the spine plotter selection + confidence pipeline."""

import math
from typing import List

import numpy as np
import pytest

import sys
from pathlib import Path

# Add parent to path for imports (repo/src/core)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from graphs.loader_bundle import GraphDataBundle
from graphs.plots import spines as spines_plot  # noqa: E402


def _make_spine_frame(values: List[float], conf: List[float]) -> dict:
    return {"x": np.array(values), "y": np.array(values), "conf": np.array(conf)}


def test_frame_budget_prioritized():
    time_ranges = [(0, 9)]
    bout_frames = spines_plot._select_frames_by_bout(time_ranges, spines_per_bout=4)
    assert bout_frames == [[0, 3, 6, 9]]

    left = [90, 85, 10, 10, 10, 40, 10, 50, 10, 47]
    right = [90, 95, 10, 12, 12, 94, 12, 51, 12, 49]
    parallel = spines_plot._select_frames_by_parallel(left, right, time_ranges, error_range=5)
    assert parallel == [[0]]

    peaks = spines_plot._select_frames_by_peaks(
        right, left, time_ranges, cutoff=90, opposing_cutoff=80, ignore_synchronized=True, sync_range=1
    )
    assert peaks == [[5]]  # peak at 1 is removed due to opposing fin crossing cutoff

    frames_by_mode = {"peaks": peaks[0], "parallel": parallel[0], "bout": bout_frames[0]}
    selected, trimmed = spines_plot._apply_frame_budget(frames_by_mode, budget=4, priority=("peaks", "parallel", "bout"))
    assert selected == [5, 0, 3, 6]
    assert trimmed is True


def test_confidence_repair_interpolates_and_passes():
    spine = [
        _make_spine_frame([0, 0, 0], [1.0, 1.0, 1.0]),
        _make_spine_frame([1, 1, 1], [1.0, 0.2, 1.0]),
        _make_spine_frame([2, 2, 2], [1.0, 0.2, 1.0]),
    ]

    repaired, diag = spines_plot._filter_and_repair_frame(
        spine,
        frame_idx=1,
        min_conf=0.3,
        max_broken_points=2,
        replace_threshold=0.5,
        max_run=2,
    )
    assert diag.skipped is False
    assert diag.repaired_points == 2
    assert repaired is not None
    # Without a right neighbor, interpolation copies the left valid point
    assert math.isclose(repaired[1]["x"], 0.0)
    assert math.isclose(repaired[2]["x"], 0.0)


def test_confidence_long_gap_skips_frame():
    spine = [
        _make_spine_frame([0, 0, 0, 0], [1.0, 1.0, 1.0, 1.0]),
        _make_spine_frame([1, 1, 1, 1], [0.1, 0.1, 0.1, 0.1]),
        _make_spine_frame([2, 2, 2, 2], [0.1, 0.1, 0.1, 0.1]),
    ]
    repaired, diag = spines_plot._filter_and_repair_frame(
        spine,
        frame_idx=0,
        min_conf=0.3,
        max_broken_points=1,
        replace_threshold=0.5,
        max_run=1,
    )
    assert repaired is None
    assert diag.skipped is True
    assert "exceeds" in (diag.reason or "")


def test_render_spines_smoke_split_and_combined():
    spine = [
        _make_spine_frame(list(range(6)), [1, 1, 1, 1, 1, 1]),
        _make_spine_frame([v + 1 for v in range(6)], [1, 1, 0.2, 1, 1, 1]),
        _make_spine_frame([v + 2 for v in range(6)], [1, 1, 1, 1, 1, 0.2]),
    ]
    left = [80, 95, 100, 70, 85, 92]
    right = [82, 97, 101, 72, 40, 93]
    bundle = GraphDataBundle(
        time_ranges=[[0, 2], [3, 5]],
        input_values={"spine": spine},
        calculated_values={"leftFinAngles": left, "rightFinAngles": right},
        config={
            "shown_outputs": {"show_spines": True},
            "spine_plot_settings": {
                "select_by_bout": True,
                "select_by_parallel_fins": True,
                "select_by_peaks": True,
                "spines_per_bout": 3,
                "parallel_error_range": 15,
                "fin_peaks_for_right_fin": True,
                "ignore_synchronized_fin_peaks": True,
                "sync_fin_peaks_range": 1,
                "min_accepted_confidence": 0.3,
                "accepted_broken_points": 1,
                "min_confidence_replace_from_surrounding_points": 0.5,
                "draw_with_gradient": True,
                "plot_draw_offset": 10,
                "split_plots_by_bout": True,
            },
            "graph_cutoffs": {"right_fin_angle": 90, "left_fin_angle": 80},
            "open_plots": False,
        },
    )

    split_result = spines_plot.render_spines(bundle, ctx=None)
    assert split_result.mode == "by_bout"
    assert len(split_result.figures) == 2
    assert all(len(frames) > 0 for frames in split_result.frames_by_bout)

    bundle.config["spine_plot_settings"]["split_plots_by_bout"] = False
    combined_result = spines_plot.render_spines(bundle, ctx=None)
    assert combined_result.mode == "combined"
    assert len(combined_result.figures) == 1
    assert sum(len(frames) for frames in combined_result.frames_by_bout) > 0


def test_runner_auto_wires_spine_plotter():
    spine = [
        _make_spine_frame([0, 1, 2], [1.0, 1.0, 1.0]),
        _make_spine_frame([1, 2, 3], [1.0, 1.0, 1.0]),
    ]
    bundle = GraphDataBundle(
        time_ranges=[[0, 2]],
        input_values={"spine": spine},
        calculated_values={"leftFinAngles": [90, 95, 90], "rightFinAngles": [90, 96, 91]},
        config={"shown_outputs": {"show_spines": True, "show_angle_and_distance_plot": False}},
    )

    from graphs.runner import run_all_graphs

    results = run_all_graphs(bundle)
    assert "render_spines" in results
    assert isinstance(results["render_spines"], spines_plot.SpinePlotResult)
