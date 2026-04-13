"""
Analysis utilities for zebrafish kinematic data.

Provides cross-correlation analysis for identifying temporal
relationships and lead/lag patterns between movement signals.
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
