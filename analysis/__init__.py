"""
Analysis module for zebrafish kinematic data.

Provides advanced analysis tools including cross-correlation
between body part movements and derived angles.
"""

from .cross_correlation import (
    CrossCorrelationResult,
    compute_cross_correlation,
    compute_cross_correlation_from_dataframe,
    get_available_signals,
    compute_all_pairwise_correlations,
)

__all__ = [
    "CrossCorrelationResult",
    "compute_cross_correlation",
    "compute_cross_correlation_from_dataframe",
    "get_available_signals",
    "compute_all_pairwise_correlations",
]

__version__ = "1.0.0"
