"""
Unit tests for summary statistics calculations (src/core/analysis/summary_statistics.py).
Covers calculation of mean and median, NaN and missing value handling, edge cases,
and DataFrame formatting.
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd
import pytest

from src.core.analysis.summary_statistics import (
    clean_numeric_series,
    compute_series_summary_stats,
    compute_summary_statistics_df,
    get_parameter_units,
)


class TestComputeSeriesSummaryStats:
    """Tests for compute_series_summary_stats."""

    def test_odd_count(self):
        """Odd number of values computes exact median and accurate mean."""
        values = [10.0, 2.0, 30.0]
        res = compute_series_summary_stats(values)

        assert res.is_valid is True
        assert res.count == 3
        assert res.mean == pytest.approx(14.0)
        assert res.median == pytest.approx(10.0)

    def test_even_count(self):
        """Even number of values computes median as average of two middle values."""
        values = [1.0, 2.0, 10.0, 20.0]
        res = compute_series_summary_stats(values)

        assert res.is_valid is True
        assert res.count == 4
        assert res.mean == pytest.approx(8.25)
        assert res.median == pytest.approx(6.0)

    def test_single_value(self):
        """Single value series has identical mean and median."""
        values = [42.5]
        res = compute_series_summary_stats(values)

        assert res.is_valid is True
        assert res.count == 1
        assert res.mean == pytest.approx(42.5)
        assert res.median == pytest.approx(42.5)

    def test_empty_sequence(self):
        """Empty input yields count=0, invalid status, and NaN mean/median."""
        res = compute_series_summary_stats([])

        assert res.is_valid is False
        assert res.count == 0
        assert math.isnan(res.mean)
        assert math.isnan(res.median)

    def test_none_input(self):
        """None input returns empty statistics safely without raising exceptions."""
        res = compute_series_summary_stats(None)

        assert res.is_valid is False
        assert res.count == 0
        assert math.isnan(res.mean)
        assert math.isnan(res.median)

    def test_all_nan_and_none(self):
        """Series containing exclusively NaNs, None, and Infs yields count=0 and NaNs."""
        values = [np.nan, None, float("nan"), float("inf"), float("-inf")]
        res = compute_series_summary_stats(values)

        assert res.is_valid is False
        assert res.count == 0
        assert math.isnan(res.mean)
        assert math.isnan(res.median)

    def test_interleaved_nans_and_invalid_values(self):
        """NaNs, None, strings, and infinite values are filtered without skewing math."""
        values = [np.nan, 10.0, "invalid", 20.0, None, float("inf"), 30.0]
        res = compute_series_summary_stats(values)

        assert res.is_valid is True
        assert res.count == 3
        assert res.mean == pytest.approx(20.0)
        assert res.median == pytest.approx(20.0)

    def test_negative_and_zero_values(self):
        """Properly calculates symmetric negative, positive, and zero values."""
        values = [-50.0, 0.0, 50.0]
        res = compute_series_summary_stats(values)

        assert res.is_valid is True
        assert res.count == 3
        assert res.mean == pytest.approx(0.0)
        assert res.median == pytest.approx(0.0)


class TestParameterUnits:
    """Tests for get_parameter_units mapping."""

    def test_known_parameter_units(self):
        assert get_parameter_units("LF_Angle") == "deg"
        assert get_parameter_units("RF_Angle") == "deg"
        assert get_parameter_units("Tail_Distance") == "mm"
        assert get_parameter_units("tail_beat_frequency") == "Hz"
        assert get_parameter_units("velocity") == "mm/s"

    def test_dynamic_spine_segment_units(self):
        assert get_parameter_units("TailAngle_0") == "deg"
        assert get_parameter_units("TailAngle_4") == "deg"

    def test_custom_units_override(self):
        custom = {"LF_Angle": "radians", "velocity": "m/s"}
        assert get_parameter_units("LF_Angle", custom) == "radians"
        assert get_parameter_units("velocity", custom) == "m/s"


class TestComputeSummaryStatisticsDf:
    """Tests for compute_summary_statistics_df."""

    def test_dataframe_structure_and_columns(self):
        """Resulting DataFrame matches required ['parameter', 'mean', 'median', 'units'] columns."""
        df = pd.DataFrame({
            "Time": [0, 1, 2, 3],
            "LF_Angle": [10.0, 20.0, 30.0, 40.0],
            "RF_Angle": [15.0, np.nan, 25.0, 35.0],
            "Tail_Distance": [1.0, 2.0, 3.0, 4.0],
        })

        summary_df = compute_summary_statistics_df(df)

        assert list(summary_df.columns) == ["parameter", "mean", "median", "units"]
        # 'Time' should be excluded by default
        assert "Time" not in summary_df["parameter"].values
        assert set(summary_df["parameter"].values) == {"LF_Angle", "RF_Angle", "Tail_Distance"}

        # Verify LF_Angle stats
        lf_row = summary_df[summary_df["parameter"] == "LF_Angle"].iloc[0]
        assert lf_row["mean"] == pytest.approx(25.0)
        assert lf_row["median"] == pytest.approx(25.0)
        assert lf_row["units"] == "deg"

        # Verify RF_Angle stats (with 1 NaN filtered)
        rf_row = summary_df[summary_df["parameter"] == "RF_Angle"].iloc[0]
        assert rf_row["mean"] == pytest.approx(25.0)
        assert rf_row["median"] == pytest.approx(25.0)
        assert rf_row["units"] == "deg"

    def test_explicit_parameter_selection(self):
        """Allows selecting a specific subset of parameters."""
        df = pd.DataFrame({
            "LF_Angle": [10.0, 20.0],
            "RF_Angle": [30.0, 40.0],
            "ExtraCol": [1.0, 2.0],
        })

        summary_df = compute_summary_statistics_df(df, parameters=["LF_Angle"])
        assert len(summary_df) == 1
        assert summary_df.iloc[0]["parameter"] == "LF_Angle"

    def test_dict_input(self):
        """Accepts a dictionary of series as input."""
        data = {
            "Tail_Angle": [5.0, 15.0, 25.0],
        }
        summary_df = compute_summary_statistics_df(data)
        assert len(summary_df) == 1
        assert summary_df.iloc[0]["parameter"] == "Tail_Angle"
        assert summary_df.iloc[0]["mean"] == pytest.approx(15.0)
        assert summary_df.iloc[0]["median"] == pytest.approx(15.0)
        assert summary_df.iloc[0]["units"] == "deg"

    def test_invalid_type_raises(self):
        """Raises TypeError for non-DataFrame non-dict input."""
        with pytest.raises(TypeError):
            compute_summary_statistics_df(["not", "a", "dataframe"])
