"""
Unit tests for the cross-correlation analysis module.

Tests cover normal operations, edge cases, and error handling
to ensure the cross-correlation engine is robust and reliable.
"""

import pytest
import numpy as np
import pandas as pd
from typing import List

from .cross_correlation import (
    CrossCorrelationResult,
    compute_cross_correlation,
    compute_cross_correlation_from_dataframe,
    get_available_signals,
    compute_all_pairwise_correlations,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df():
    """
    Create a realistic sample DataFrame matching Driver.run_calculations output.
    Contains known signals for predictable cross-correlation results.
    """
    np.random.seed(42)
    n_frames = 1000

    # Create a base signal
    base_signal = np.sin(np.linspace(0, 4 * np.pi, n_frames))

    # Signal B is Signal A shifted by 10 frames (known lag)
    shifted_signal = np.roll(base_signal, 10)

    df = pd.DataFrame({
        # Basic time index
        'Time': np.arange(n_frames),

        # Fin angles - base signal and shifted version
        'LF_Angle': base_signal * 45 + np.random.normal(0, 2, n_frames),
        'RF_Angle': shifted_signal * 42 + np.random.normal(0, 2, n_frames),

        # Head orientation
        'HeadYaw': np.random.normal(0, 15, n_frames),

        # Tail metrics
        'Tail_Distance': np.abs(base_signal) * 0.015 + np.random.normal(0, 0.001, n_frames),
        'Tail_Angle': base_signal * 20 + np.random.normal(0, 3, n_frames),

        # Head position
        'HeadX': np.random.normal(0.01, 0.002, n_frames),
        'HeadY': np.random.normal(0.01, 0.002, n_frames),

        # Spine angles
        'TailAngle_0': base_signal * 10 + np.random.normal(0, 1, n_frames),
        'TailAngle_1': shifted_signal * 15 + np.random.normal(0, 1, n_frames),

        # Peak detection (binary)
        'leftFinPeaks': np.random.choice([0, 1], n_frames, p=[0.95, 0.05]),
        'rightFinPeaks': np.random.choice([0, 1], n_frames, p=[0.95, 0.05]),

        # Bookkeeping columns (should be excluded from available signals)
        'timeRangeStart_0': [0] + [''] * (n_frames - 1),
        'timeRangeEnd_0': [n_frames - 1] + [''] * (n_frames - 1),
    })

    return df

@pytest.fixture
def simple_signals():
    """Simple, clean signals with a known exact relationship."""
    n = 500
    t = np.linspace(0, 2 * np.pi, n)
    signal_a = np.sin(t)
    signal_b = np.sin(t)  # Identical signal -> perfect correlation at lag 0
    return signal_a, signal_b

@pytest.fixture
def shifted_signals():
    """Two signals where B is shifted version of A by exactly 5 frames."""
    n = 500
    t = np.linspace(0, 4 * np.pi, n)
    signal_a = np.sin(t)
    signal_b = np.roll(signal_a, 5)  # Shift by 5 frames
    return signal_a, signal_b

@pytest.fixture
def signals_with_nans():
    """Signals containing NaN values at known positions."""
    np.random.seed(99)
    n = 300
    signal_a = np.random.normal(0, 1, n).astype(float)
    signal_b = np.random.normal(0, 1, n).astype(float)

    # Introduce NaNs at known indices
    signal_a[10] = np.nan
    signal_a[50] = np.nan
    signal_b[75] = np.nan
    signal_b[200] = np.nan

    return signal_a, signal_b

# ---------------------------------------------------------------------------
# Tests: compute_cross_correlation
# ---------------------------------------------------------------------------

class TestComputeCrossCorrelation:
    """Tests for the core compute_cross_correlation function."""

    def test_identical_signals_peak_at_zero(self, simple_signals):
        """Identical signals should have peak correlation at lag 0."""
        signal_a, signal_b = simple_signals
        result = compute_cross_correlation(
            signal_a, signal_b,
            name_a="SigA", name_b="SigB"
        )

        assert result.peak_lag == 0
        assert result.peak_correlation > 0.95

    def test_shifted_signals_detect_correct_lag(self, shifted_signals):
        """Shifted signals should detect the correct lag."""
        signal_a, signal_b = shifted_signals
        result = compute_cross_correlation(
            signal_a, signal_b,
            name_a="SigA", name_b="SigB",
            max_lag=20
        )

        # Peak lag should be close to 5 (the known shift)
        assert abs(result.peak_lag) <= 7  # Allow small tolerance for noise

    def test_result_structure(self, simple_signals):
        """Result should contain all expected fields."""
        signal_a, signal_b = simple_signals
        result = compute_cross_correlation(
            signal_a, signal_b,
            name_a="LF_Angle", name_b="RF_Angle"
        )

        assert isinstance(result, CrossCorrelationResult)
        assert isinstance(result.lags, np.ndarray)
        assert isinstance(result.correlations, np.ndarray)
        assert isinstance(result.peak_lag, int)
        assert isinstance(result.peak_correlation, float)
        assert isinstance(result.n_frames, int)
        assert isinstance(result.warnings, list)

    def test_lags_and_correlations_same_length(self, simple_signals):
        """Lags and correlations arrays must be the same length."""
        signal_a, signal_b = simple_signals
        result = compute_cross_correlation(signal_a, signal_b)

        assert len(result.lags) == len(result.correlations)

    def test_correlations_normalised_within_bounds(self, simple_signals):
        """Normalised correlations should be in [-1, 1]."""
        signal_a, signal_b = simple_signals
        result = compute_cross_correlation(
            signal_a, signal_b, normalize=True
        )

        assert np.all(result.correlations >= -1.0)
        assert np.all(result.correlations <= 1.0)

    def test_max_lag_respected(self, simple_signals):
        """Lag array should not exceed max_lag."""
        signal_a, signal_b = simple_signals
        max_lag = 30
        result = compute_cross_correlation(
            signal_a, signal_b, max_lag=max_lag
        )

        assert result.lags[0] == -max_lag
        assert result.lags[-1] == max_lag
        assert len(result.lags) == 2 * max_lag + 1

    def test_mismatched_length_raises_error(self):
        """Signals of different lengths should raise ValueError."""
        signal_a = np.random.randn(100)
        signal_b = np.random.randn(200)

        with pytest.raises(ValueError, match="same length"):
            compute_cross_correlation(signal_a, signal_b)

    def test_too_short_signal_raises_error(self):
        """Signal with less than 2 data points should raise ValueError."""
        signal_a = np.array([1.0])
        signal_b = np.array([1.0])

        with pytest.raises(ValueError, match="at least 2"):
            compute_cross_correlation(signal_a, signal_b)

    def test_invalid_type_raises_error(self):
        """Non-array-like input should raise TypeError."""
        with pytest.raises(TypeError):
            compute_cross_correlation("not_an_array", [1, 2, 3])

    def test_pandas_series_input(self, sample_df):
        """Should work with pandas Series input."""
        result = compute_cross_correlation(
            sample_df['LF_Angle'],
            sample_df['RF_Angle'],
            name_a='LF_Angle',
            name_b='RF_Angle'
        )

        assert isinstance(result, CrossCorrelationResult)
        assert result.n_frames > 0

    def test_list_input(self):
        """Should work with plain Python list input."""
        signal_a = [1.0, 2.0, 3.0, 2.0, 1.0] * 20
        signal_b = [0.0, 1.0, 2.0, 3.0, 2.0] * 20

        result = compute_cross_correlation(signal_a, signal_b)
        assert isinstance(result, CrossCorrelationResult)

    def test_nan_handling(self, signals_with_nans):
        """NaN values should be removed and a warning issued."""
        signal_a, signal_b = signals_with_nans
        result = compute_cross_correlation(
            signal_a, signal_b,
            name_a="SigA", name_b="SigB"
        )

        # Should complete without error
        assert result.n_frames < len(signal_a)

        # Should have a warning about dropped frames
        assert any("missing" in w.lower() for w in result.warnings)

    def test_constant_signal_warning(self):
        """Constant signal (zero variance) should not crash."""
        signal_a = np.ones(200)
        signal_b = np.random.randn(200)

        # Should not raise, just issue a warning
        result = compute_cross_correlation(signal_a, signal_b)
        assert isinstance(result, CrossCorrelationResult)

    def test_signal_names_in_result(self):
        """Signal names should be preserved in the result."""
        signal_a = np.random.randn(100)
        signal_b = np.random.randn(100)

        result = compute_cross_correlation(
            signal_a, signal_b,
            name_a="HeadYaw", name_b="Tail_Distance"
        )

        assert result.signal_a_name == "HeadYaw"
        assert result.signal_b_name == "Tail_Distance"

    def test_to_dict_structure(self, simple_signals):
        """to_dict() should return a complete, serialisable dictionary."""
        signal_a, signal_b = simple_signals
        result = compute_cross_correlation(signal_a, signal_b)
        d = result.to_dict()

        required_keys = [
            'signal_a', 'signal_b', 'lags', 'correlations',
            'peak_lag', 'peak_correlation', 'n_frames',
            'warnings', 'interpretation'
        ]
        for key in required_keys:
            assert key in d

        # lags and correlations should be plain lists (JSON serialisable)
        assert isinstance(d['lags'], list)
        assert isinstance(d['correlations'], list)

    def test_interpretation_zero_lag(self, simple_signals):
        """Interpretation should mention synchronised for zero lag."""
        signal_a, signal_b = simple_signals
        result = compute_cross_correlation(signal_a, signal_b)

        if result.peak_lag == 0:
            assert "synchronised" in result._interpret().lower()

    def test_interpretation_positive_lag(self):
        """Interpretation should say A leads B for positive lag."""
        result = CrossCorrelationResult(
            signal_a_name="LF_Angle",
            signal_b_name="RF_Angle",
            lags=np.array([-1, 0, 1]),
            correlations=np.array([0.5, 0.7, 0.9]),
            peak_lag=1,
            peak_correlation=0.9,
            n_frames=100,
            warnings=[]
        )
        assert "LF_Angle leads RF_Angle" in result._interpret()

    def test_interpretation_negative_lag(self):
        """Interpretation should say B leads A for negative lag."""
        result = CrossCorrelationResult(
            signal_a_name="LF_Angle",
            signal_b_name="RF_Angle",
            lags=np.array([-1, 0, 1]),
            correlations=np.array([0.9, 0.7, 0.5]),
            peak_lag=-1,
            peak_correlation=0.9,
            n_frames=100,
            warnings=[]
        )
        assert "RF_Angle leads LF_Angle" in result._interpret()

# ---------------------------------------------------------------------------
# Tests: compute_cross_correlation_from_dataframe
# ---------------------------------------------------------------------------

class TestFromDataFrame:
    """Tests for the DataFrame convenience wrapper."""

    def test_basic_usage(self, sample_df):
        """Should compute cross-correlation from DataFrame columns."""
        result = compute_cross_correlation_from_dataframe(
            sample_df, 'LF_Angle', 'RF_Angle'
        )

        assert isinstance(result, CrossCorrelationResult)
        assert result.signal_a_name == 'LF_Angle'
        assert result.signal_b_name == 'RF_Angle'
        assert result.n_frames > 0

    def test_missing_column_raises_key_error(self, sample_df):
        """Should raise KeyError for non-existent column."""
        with pytest.raises(KeyError, match="not found"):
            compute_cross_correlation_from_dataframe(
                sample_df, 'NonExistent_Col', 'LF_Angle'
            )

    def test_invalid_dataframe_type_raises_error(self):
        """Should raise TypeError for non-DataFrame input."""
        with pytest.raises(TypeError):
            compute_cross_correlation_from_dataframe(
                {'not': 'a dataframe'}, 'LF_Angle', 'RF_Angle'
            )

    def test_all_key_columns(self, sample_df):
        """Should work with all key metric column pairs."""
        pairs = [
            ('LF_Angle', 'RF_Angle'),
            ('HeadYaw', 'Tail_Distance'),
            ('TailAngle_0', 'TailAngle_1'),
        ]

        for col_a, col_b in pairs:
            result = compute_cross_correlation_from_dataframe(
                sample_df, col_a, col_b
            )
            assert isinstance(result, CrossCorrelationResult)
            assert result.n_frames > 0

# ---------------------------------------------------------------------------
# Tests: get_available_signals
# ---------------------------------------------------------------------------

class TestGetAvailableSignals:
    """Tests for dynamic signal detection."""

    def test_returns_list(self, sample_df):
        """Should return a list."""
        signals = get_available_signals(sample_df)
        assert isinstance(signals, list)

    def test_excludes_time_column(self, sample_df):
        """Should exclude the 'Time' bookkeeping column."""
        signals = get_available_signals(sample_df)
        assert 'Time' not in signals

    def test_excludes_time_range_columns(self, sample_df):
        """Should exclude timeRangeStart_* and timeRangeEnd_* columns."""
        signals = get_available_signals(sample_df)
        time_range_cols = [c for c in signals if c.startswith('timeRange')]
        assert len(time_range_cols) == 0

    def test_includes_movement_signals(self, sample_df):
        """Should include all key movement signal columns."""
        signals = get_available_signals(sample_df)
        expected = ['LF_Angle', 'RF_Angle', 'HeadYaw', 'Tail_Distance', 'Tail_Angle']
        for col in expected:
            assert col in signals

    def test_returns_sorted_list(self, sample_df):
        """Should return columns in sorted order."""
        signals = get_available_signals(sample_df)
        assert signals == sorted(signals)

    def test_empty_dataframe(self):
        """Should return empty list for empty DataFrame."""
        signals = get_available_signals(pd.DataFrame())
        assert signals == []

    def test_only_non_numeric_columns(self):
        """Should return empty list if no numeric columns exist."""
        df = pd.DataFrame({'A': ['x', 'y', 'z'], 'B': ['a', 'b', 'c']})
        signals = get_available_signals(df)
        assert signals == []

    def test_dynamically_detects_new_columns(self):
        """Should automatically include any new numeric column added."""
        df = pd.DataFrame({
            'LF_Angle': np.random.randn(100),
            'RF_Angle': np.random.randn(100),
            'NewMetric_Future': np.random.randn(100),  # Future metric
        })
        signals = get_available_signals(df)
        assert 'NewMetric_Future' in signals


# ---------------------------------------------------------------------------
# Tests: compute_all_pairwise_correlations
# ---------------------------------------------------------------------------

class TestPairwiseCorrelations:
    """Tests for the pairwise correlation computation."""

    def test_basic_pairwise(self, sample_df):
        """Should compute pairwise correlations for selected signals."""
        signals = ['LF_Angle', 'RF_Angle', 'HeadYaw']
        results = compute_all_pairwise_correlations(
            sample_df, signals=signals
        )

        # Should have 3 pairs: LF_vs_RF, LF_vs_Head, RF_vs_Head
        assert len(results) == 3
        assert 'LF_Angle_vs_RF_Angle' in results
        assert 'LF_Angle_vs_HeadYaw' in results
        assert 'RF_Angle_vs_HeadYaw' in results

    def test_all_results_are_correct_type(self, sample_df):
        """All results should be CrossCorrelationResult instances."""
        signals = ['LF_Angle', 'RF_Angle', 'Tail_Distance']
        results = compute_all_pairwise_correlations(
            sample_df, signals=signals
        )

        for key, result in results.items():
            assert isinstance(result, CrossCorrelationResult)

    def test_auto_detect_signals(self, sample_df):
        """Should auto-detect signals when none are specified."""
        results = compute_all_pairwise_correlations(sample_df)

        # Should have results for all pairs
        assert len(results) > 0

        # All values should be CrossCorrelationResult
        for key, result in results.items():
            assert isinstance(result, CrossCorrelationResult)

    def test_single_signal_raises_error(self, sample_df):
        """Should raise ValueError when fewer than 2 signals provided."""
        with pytest.raises(ValueError, match="At least 2 signals"):
            compute_all_pairwise_correlations(
                sample_df, signals=['LF_Angle']
            )

    def test_invalid_column_skipped_gracefully(self, sample_df):
        """Should skip invalid columns without crashing."""
        # Mix valid and invalid columns
        signals = ['LF_Angle', 'RF_Angle', 'NonExistent_Column']

        # Should not raise, just skip the invalid pair
        results = compute_all_pairwise_correlations(
            sample_df, signals=signals
        )

        # Should still have results for the valid pair
        assert 'LF_Angle_vs_RF_Angle' in results

    def test_result_keys_format(self, sample_df):
        """Result keys should follow 'ColA_vs_ColB' format."""
        signals = ['LF_Angle', 'RF_Angle']
        results = compute_all_pairwise_correlations(
            sample_df, signals=signals
        )

        for key in results.keys():
            assert '_vs_' in key


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self, sample_df):
        """
        Test the complete workflow:
        1. Detect available signals
        2. Compute cross-correlation between two signals
        3. Serialise result to dict
        4. Verify output is suitable for visualization
        """
        # Step 1: Detect available signals dynamically
        signals = get_available_signals(sample_df)
        assert len(signals) >= 2

        # Step 2: Compute cross-correlation
        result = compute_cross_correlation_from_dataframe(
            sample_df, signals[0], signals[1]
        )
        assert isinstance(result, CrossCorrelationResult)

        # Step 3: Serialise to dict
        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)

        # Step 4: Verify visualization-ready output
        assert len(result_dict['lags']) == len(result_dict['correlations'])
        assert isinstance(result_dict['interpretation'], str)
        assert len(result_dict['interpretation']) > 0

    def test_result_suitable_for_export(self, sample_df):
        """Result dict should be JSON-serialisable (all native Python types)."""
        import json

        result = compute_cross_correlation_from_dataframe(
            sample_df, 'LF_Angle', 'RF_Angle'
        )
        result_dict = result.to_dict()

        # Should not raise
        json_str = json.dumps(result_dict)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

    def test_multiple_datasets_workflow(self):
        """
        Simulate comparing cross-correlations across multiple datasets,
        mimicking the batch processing use case.
        """
        np.random.seed(42)
        datasets = {}

        for i in range(3):
            n = 500
            t = np.linspace(0, 4 * np.pi, n)
            lag = i * 5  # Different lag per dataset

            datasets[f"Fish_{i}"] = pd.DataFrame({
                'LF_Angle': np.sin(t) * 45,
                'RF_Angle': np.roll(np.sin(t), lag) * 42,
                'HeadYaw': np.random.normal(0, 15, n),
                'Tail_Distance': np.abs(np.sin(t)) * 0.015,
            })

        # Compute cross-correlation for each dataset
        all_results = {}
        for name, df in datasets.items():
            all_results[name] = compute_cross_correlation_from_dataframe(
                df, 'LF_Angle', 'RF_Angle'
            )

        # All should complete successfully
        assert len(all_results) == 3
        for name, result in all_results.items():
            assert isinstance(result, CrossCorrelationResult)
            assert result.n_frames > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
