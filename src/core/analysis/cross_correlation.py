"""
Cross-correlation analysis module for zebrafish kinematic data.

Provides functionality to compute cross-correlation between any two
movement signals (body part coordinates or derived angles) to identify
synchronization and lead/lag relationships between body part movements.

Suggested by Dr. Sengupta to support advanced behavioral analysis.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Core result dataclass
# ---------------------------------------------------------------------------

class CrossCorrelationResult:
    """
    Structured result from a cross-correlation computation.

    Attributes:
        signal_a_name: Name/label of the first signal.
        signal_b_name: Name/label of the second signal.
        lags: Array of lag values (in frames). Negative lag means
              signal_b leads signal_a; positive lag means signal_a leads.
        correlations: Normalised cross-correlation coefficient at each lag.
        peak_lag: Lag at which the absolute correlation is highest.
        peak_correlation: Correlation value at the peak lag.
        n_frames: Number of frames used after removing missing values.
        warnings: List of non-fatal issues encountered during computation.
    """

    def __init__(
        self,
        signal_a_name: str,
        signal_b_name: str,
        lags: np.ndarray,
        correlations: np.ndarray,
        peak_lag: int,
        peak_correlation: float,
        n_frames: int,
        warnings: List[str],
    ):
        self.signal_a_name = signal_a_name
        self.signal_b_name = signal_b_name
        self.lags = lags
        self.correlations = correlations
        self.peak_lag = peak_lag
        self.peak_correlation = peak_correlation
        self.n_frames = n_frames
        self.warnings = warnings

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialise the result to a plain dictionary suitable for
        export, UI consumption, or JSON serialisation.
        """
        return {
            "signal_a": self.signal_a_name,
            "signal_b": self.signal_b_name,
            "lags": self.lags.tolist(),
            "correlations": self.correlations.tolist(),
            "peak_lag": self.peak_lag,
            "peak_correlation": self.peak_correlation,
            "n_frames": self.n_frames,
            "warnings": self.warnings,
            "interpretation": self._interpret(),
        }

    def _interpret(self) -> str:
        """Return a human-readable interpretation of the peak lag."""
        if self.peak_lag == 0:
            return (
                f"{self.signal_a_name} and {self.signal_b_name} are "
                "maximally synchronised (zero lag)."
            )
        elif self.peak_lag > 0:
            return (
                f"{self.signal_a_name} leads {self.signal_b_name} "
                f"by {self.peak_lag} frame(s)."
            )
        else:
            return (
                f"{self.signal_b_name} leads {self.signal_a_name} "
                f"by {abs(self.peak_lag)} frame(s)."
            )

    def __repr__(self) -> str:
        return (
            f"CrossCorrelationResult("
            f"'{self.signal_a_name}' vs '{self.signal_b_name}', "
            f"peak_lag={self.peak_lag}, "
            f"peak_correlation={self.peak_correlation:.4f}, "
            f"n_frames={self.n_frames})"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_cross_correlation(
    signal_a: Union[pd.Series, np.ndarray, List[float]],
    signal_b: Union[pd.Series, np.ndarray, List[float]],
    *,
    name_a: str = "Signal A",
    name_b: str = "Signal B",
    max_lag: Optional[int] = None,
    normalize: bool = True,
) -> CrossCorrelationResult:
    """
    Compute cross-correlation between two movement signals.

    Args:
        signal_a: First signal (any numeric sequence).
        signal_b: Second signal (any numeric sequence, same length as signal_a).
        name_a: Human-readable label for signal_a (used in output/reports).
        name_b: Human-readable label for signal_b.
        max_lag: Maximum lag (in frames) to compute. If None, uses
                 min(len // 4, 500) to keep results manageable.
        normalize: If True (default) correlations are normalised to [-1, 1].

    Returns:
        CrossCorrelationResult with lags, correlations, peak info, and
        a plain-English interpretation.

    Raises:
        ValueError: If inputs cannot be converted to numeric arrays or
                    have mismatched lengths.
        TypeError: If inputs are not array-like.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({'LF_Angle': [...], 'RF_Angle': [...]})
        >>> result = compute_cross_correlation(
        ...     df['LF_Angle'], df['RF_Angle'],
        ...     name_a='LF_Angle', name_b='RF_Angle'
        ... )
        >>> print(result)
    """
    warn_list: List[str] = []

    # --- Convert inputs to numpy float arrays ---
    a = _to_float_array(signal_a, name_a)
    b = _to_float_array(signal_b, name_b)

    # --- Length check ---
    if len(a) != len(b):
        raise ValueError(
            f"Signals must have the same length. "
            f"'{name_a}' has {len(a)} frames, '{name_b}' has {len(b)} frames."
        )

    if len(a) < 2:
        raise ValueError("Signals must contain at least 2 data points.")

    # --- Handle missing values (NaN) ---
    a, b, n_dropped = _handle_missing_values(a, b)
    if n_dropped > 0:
        warn_list.append(
            f"{n_dropped} frame(s) with missing values were excluded "
            f"from the cross-correlation computation."
        )

    n_frames = len(a)
    if n_frames < 2:
        raise ValueError(
            "After removing missing values, fewer than 2 valid frames remain. "
            "Cannot compute cross-correlation."
        )

    # --- Determine max lag ---
    if max_lag is None:
        max_lag = min(n_frames // 4, 500)
    else:
        if max_lag >= n_frames:
            max_lag = n_frames - 1
            warn_list.append(
                f"max_lag was reduced to {max_lag} (signal length - 1)."
            )

    # --- Normalise signals to zero mean and unit variance ---
    a_norm, b_norm = _normalise(a), _normalise(b)

    # --- Compute full cross-correlation using numpy ---
    full_xcorr = np.correlate(a_norm, b_norm, mode="full")

    # --- Extract the lag window we care about ---
    mid = len(full_xcorr) // 2
    lag_indices = range(mid - max_lag, mid + max_lag + 1)
    lags = np.arange(-max_lag, max_lag + 1, dtype=int)
    correlations = full_xcorr[lag_indices[0]: lag_indices[-1] + 1]

    # --- Normalise to [-1, 1] ---
    if normalize:
        norm_factor = n_frames  # matches standard normalised cross-correlation
        correlations = correlations / norm_factor

        # Clip to valid range to guard against floating-point overshoot
        correlations = np.clip(correlations, -1.0, 1.0)

    # --- Find peak ---
    peak_idx = int(np.argmax(np.abs(correlations)))
    peak_lag = int(lags[peak_idx])
    peak_correlation = float(correlations[peak_idx])

    return CrossCorrelationResult(
        signal_a_name=name_a,
        signal_b_name=name_b,
        lags=lags,
        correlations=correlations,
        peak_lag=peak_lag,
        peak_correlation=peak_correlation,
        n_frames=n_frames,
        warnings=warn_list,
    )


def compute_cross_correlation_from_dataframe(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    *,
    max_lag: Optional[int] = None,
    normalize: bool = True,
) -> CrossCorrelationResult:
    """
    Convenience wrapper: compute cross-correlation directly from a DataFrame.

    Args:
        df: DataFrame produced by Driver.run_calculations().
        col_a: Column name of the first signal.
        col_b: Column name of the second signal.
        max_lag: Maximum lag in frames (optional).
        normalize: Normalise correlations to [-1, 1] (default True).

    Returns:
        CrossCorrelationResult.

    Raises:
        KeyError: If either column name is not found in the DataFrame.
        ValueError: For data quality issues.

    Example:
        >>> result = compute_cross_correlation_from_dataframe(
        ...     results_df, 'LF_Angle', 'RF_Angle'
        ... )
    """
    _validate_dataframe(df, col_a, col_b)

    return compute_cross_correlation(
        df[col_a],
        df[col_b],
        name_a=col_a,
        name_b=col_b,
        max_lag=max_lag,
        normalize=normalize,
    )


def get_available_signals(df: pd.DataFrame) -> List[str]:
    """
    Dynamically detect all numeric columns available for cross-correlation.

    Excludes internal bookkeeping columns (time range markers, the Time
    index column) so only meaningful movement signals are returned.

    Args:
        df: DataFrame produced by Driver.run_calculations().

    Returns:
        Sorted list of column names suitable for cross-correlation.

    Example:
        >>> signals = get_available_signals(results_df)
        >>> print(signals)
        ['Furthest_Tail_Point', 'HeadX', 'HeadY', 'HeadYaw', 'LF_Angle', ...]
    """
    # Columns that are bookkeeping, not movement signals
    exclude_prefixes = ("timeRangeStart_", "timeRangeEnd_")
    exclude_exact = {"Time"}

    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()

    available = [
        col for col in numeric_cols
        if col not in exclude_exact
        and not any(col.startswith(prefix) for prefix in exclude_prefixes)
    ]

    return sorted(available)


def compute_all_pairwise_correlations(
    df: pd.DataFrame,
    signals: Optional[List[str]] = None,
    *,
    max_lag: Optional[int] = None,
) -> Dict[str, CrossCorrelationResult]:
    """
    Compute cross-correlation for every unique pair of signals.

    Args:
        df: DataFrame produced by Driver.run_calculations().
        signals: List of column names to include. If None, all available
                 numeric signals are used (see get_available_signals).
        max_lag: Maximum lag in frames (optional).

    Returns:
        Dictionary mapping "ColA_vs_ColB" keys to CrossCorrelationResult objects.

    Notes:
        For large DataFrames with many columns this can be slow.
        Prefer compute_cross_correlation_from_dataframe for targeted queries.
    """
    if signals is None:
        signals = get_available_signals(df)

    if len(signals) < 2:
        raise ValueError("At least 2 signals are required for pairwise comparison.")

    results: Dict[str, CrossCorrelationResult] = {}

    for i in range(len(signals)):
        for j in range(i + 1, len(signals)):
            col_a, col_b = signals[i], signals[j]
            key = f"{col_a}_vs_{col_b}"
            try:
                results[key] = compute_cross_correlation_from_dataframe(
                    df, col_a, col_b, max_lag=max_lag
                )
            except Exception as exc:
                warnings.warn(f"Skipping '{key}': {exc}")

    return results


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_float_array(signal: Any, name: str) -> np.ndarray:
    """Convert input signal to a float64 numpy array."""
    if isinstance(signal, pd.Series):
        arr = pd.to_numeric(signal, errors="coerce").to_numpy(dtype=float)
    elif isinstance(signal, np.ndarray):
        arr = signal.astype(float)
    elif isinstance(signal, list):
        try:
            arr = np.array(signal, dtype=float)
        except (ValueError, TypeError) as exc:
            raise TypeError(
                f"Signal '{name}' could not be converted to a numeric array: {exc}"
            )
    else:
        raise TypeError(
            f"Signal '{name}' must be a pandas Series, numpy array, or list. "
            f"Got {type(signal).__name__}."
        )
    return arr


def _handle_missing_values(
    a: np.ndarray, b: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Remove frames where either signal has a NaN value.

    Returns the cleaned arrays and the number of dropped frames.
    """
    valid_mask = ~(np.isnan(a) | np.isnan(b))
    n_dropped = int(np.sum(~valid_mask))
    return a[valid_mask], b[valid_mask], n_dropped


def _normalise(arr: np.ndarray) -> np.ndarray:
    """
    Subtract mean and divide by standard deviation.
    Returns zeros if standard deviation is zero (constant signal).
    """
    mean = np.mean(arr)
    std = np.std(arr)
    if std == 0:
        warnings.warn("Signal has zero variance (constant values); correlation will be zero.")
        return np.zeros_like(arr)
    return (arr - mean) / std


def _validate_dataframe(df: pd.DataFrame, col_a: str, col_b: str) -> None:
    """Validate that the DataFrame contains the requested columns."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"Expected a pandas DataFrame, got {type(df).__name__}.")
    missing = [c for c in (col_a, col_b) if c not in df.columns]
    if missing:
        raise KeyError(
            f"Column(s) not found in DataFrame: {', '.join(missing)}. "
            f"Available columns: {', '.join(df.columns.tolist())}"
        )


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "CrossCorrelationResult",
    "compute_cross_correlation",
    "compute_cross_correlation_from_dataframe",
    "get_available_signals",
    "compute_all_pairwise_correlations",
]
