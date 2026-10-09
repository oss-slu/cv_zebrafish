"""
Unit tests for range statistics calculation (src/core/analysis/range_statistics.py).
"""

from __future__ import annotations

import math
import numpy as np
import plotly.graph_objects as go
import pytest

from src.core.analysis.range_statistics import (
    RangeStatisticsResult,
    compute_range_statistics,
    extract_traces_from_figure,
    get_figure_x_bounds,
)


class TestComputeRangeStatistics:
    """Tests for compute_range_statistics."""

    def test_basic_statistics_calculation(self):
        """Verify min, max, mean, and positions on a simple range."""
        x = [0, 10, 20, 30, 40, 50]
        y = [5.0, 15.0, 3.0, 25.0, 10.0, 8.0]

        res = compute_range_statistics(x, y, start_x=10, end_x=40)

        assert res.is_valid is True
        assert res.error_message is None
        assert res.count == 4
        assert res.min_value == 3.0
        assert res.min_x == 20.0
        assert res.max_value == 25.0
        assert res.max_x == 30.0
        assert res.mean_value == pytest.approx((15.0 + 3.0 + 25.0 + 10.0) / 4)

    def test_single_point_range(self):
        """A range containing exactly one point should have min == max == mean."""
        x = [1, 2, 3]
        y = [10.5, 20.5, 30.5]

        res = compute_range_statistics(x, y, start_x=2, end_x=2)

        assert res.is_valid is True
        assert res.count == 1
        assert res.min_value == 20.5
        assert res.max_value == 20.5
        assert res.min_x == 2.0
        assert res.max_x == 2.0
        assert res.mean_value == 20.5

    def test_floating_point_coordinates(self):
        """Works seamlessly with float coordinates (such as distances or angles)."""
        x = [0.05, 0.12, 0.18, 0.25, 0.31]
        y = [-2.4, 8.1, 14.5, -6.8, 3.2]

        res = compute_range_statistics(x, y, start_x=0.10, end_x=0.26)

        assert res.is_valid is True
        assert res.count == 3
        assert res.min_value == -6.8
        assert res.min_x == 0.25
        assert res.max_value == 14.5
        assert res.max_x == 0.18
        assert res.mean_value == pytest.approx((8.1 + 14.5 - 6.8) / 3)

    def test_default_x_indices_when_none(self):
        """When x_values is None, index numbers 0..N-1 should be used."""
        y = [100.0, 200.0, 50.0, 300.0]

        res = compute_range_statistics(None, y, start_x=1, end_x=2)

        assert res.is_valid is True
        assert res.count == 2
        assert res.min_value == 50.0
        assert res.min_x == 2.0
        assert res.max_value == 200.0
        assert res.max_x == 1.0
        assert res.mean_value == 125.0

    def test_invalid_range_start_greater_than_end(self):
        """start_x > end_x should return invalid result without raising."""
        x = [0, 1, 2, 3]
        y = [10, 20, 30, 40]

        res = compute_range_statistics(x, y, start_x=30, end_x=10)

        assert res.is_valid is False
        assert "cannot exceed" in res.error_message
        assert res.min_value is None
        assert res.max_value is None
        assert res.mean_value is None

    def test_empty_range_no_points(self):
        """Range outside the data span returns empty/invalid result without raising."""
        x = [10, 20, 30]
        y = [1.0, 2.0, 3.0]

        res = compute_range_statistics(x, y, start_x=100, end_x=200)

        assert res.is_valid is False
        assert res.count == 0
        assert "No data points" in res.error_message

    def test_empty_y_data(self):
        """Empty data should return an invalid result gracefully."""
        res = compute_range_statistics([], [], start_x=0, end_x=10)
        assert res.is_valid is False
        assert "No data points" in res.error_message

    def test_mismatched_x_y_lengths(self):
        """Mismatched x and y lengths should be caught."""
        res = compute_range_statistics([1, 2], [1, 2, 3], start_x=0, end_x=10)
        assert res.is_valid is False
        assert "Mismatched" in res.error_message

    def test_nan_and_none_filtering(self):
        """None and NaN values in x or y should be skipped cleanly."""
        x = [0, 1, None, 3, 4, 5]
        y = [10.0, None, 25.0, float("nan"), 40.0, 20.0]

        res = compute_range_statistics(x, y, start_x=0, end_x=5)

        assert res.is_valid is True
        # Valid points are: (0, 10.0), (4, 40.0), (5, 20.0)
        assert res.count == 3
        assert res.min_value == 10.0
        assert res.min_x == 0.0
        assert res.max_value == 40.0
        assert res.max_x == 4.0
        assert res.mean_value == pytest.approx((10.0 + 40.0 + 20.0) / 3)

    def test_nan_bounds(self):
        """NaN bounds return invalid result gracefully."""
        res = compute_range_statistics([1, 2], [3, 4], start_x=float("nan"), end_x=10)
        assert res.is_valid is False
        assert "cannot be NaN" in res.error_message


class TestFigureTraceExtraction:
    """Tests for extract_traces_from_figure and get_figure_x_bounds."""

    def test_extract_traces_single_trace(self):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[1, 2, 3], y=[10, 20, 30], name="Signal A"))

        traces = extract_traces_from_figure(fig)
        assert "Signal A" in traces
        x_vals, y_vals = traces["Signal A"]
        assert x_vals == [1.0, 2.0, 3.0]
        assert y_vals == [10.0, 20.0, 30.0]

    def test_extract_traces_multiple_traces(self):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1, 2], y=[5, 10, 15], name="Left Fin"))
        fig.add_trace(go.Scatter(x=[0, 1, 2], y=[8, 6, 4], name="Right Fin"))

        traces = extract_traces_from_figure(fig)
        assert len(traces) == 2
        assert "Left Fin" in traces
        assert "Right Fin" in traces

    def test_extract_traces_with_none_gaps(self):
        """Plotly timeline series with None gaps should be cleaned."""
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[0, 1, None, 3, 4], y=[2.0, 4.0, None, 6.0, 8.0], name="Bout"))

        traces = extract_traces_from_figure(fig)
        x_vals, y_vals = traces["Bout"]
        assert len(x_vals) == 4
        assert None not in x_vals
        assert x_vals == [0.0, 1.0, 3.0, 4.0]
        assert y_vals == [2.0, 4.0, 6.0, 8.0]

    def test_extract_traces_empty_figure(self):
        traces = extract_traces_from_figure(go.Figure())
        assert traces == {}

    def test_extract_traces_none(self):
        traces = extract_traces_from_figure(None)
        assert traces == {}

    def test_get_figure_x_bounds(self):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=[5, 15, 25], y=[1, 2, 3]))
        fig.add_trace(go.Scatter(x=[2, 10, 30], y=[4, 5, 6]))

        bounds = get_figure_x_bounds(fig)
        assert bounds is not None
        min_x, max_x = bounds
        assert min_x == 2.0
        assert max_x == 30.0

    def test_get_figure_x_bounds_empty(self):
        assert get_figure_x_bounds(go.Figure()) is None
        assert get_figure_x_bounds(None) is None
