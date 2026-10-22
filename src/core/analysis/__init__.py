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
from .summary_statistics import (
    KNOWN_ANALYSIS_PARAMETERS,
    SeriesSummaryStats,
    clean_numeric_series,
    compute_series_summary_stats,
    compute_summary_statistics_df,
    export_summary_statistics_to_csv,
    export_summary_statistics_to_excel,
    get_parameter_units,
)

__all__ = [
    "CrossCorrelationResult",
    "compute_cross_correlation",
    "compute_cross_correlation_from_dataframe",
    "get_available_signals",
    "compute_all_pairwise_correlations",
    "KNOWN_ANALYSIS_PARAMETERS",
    "SeriesSummaryStats",
    "clean_numeric_series",
    "compute_series_summary_stats",
    "compute_summary_statistics_df",
    "export_summary_statistics_to_csv",
    "export_summary_statistics_to_excel",
    "get_parameter_units",
]

__version__ = "1.0.0"
