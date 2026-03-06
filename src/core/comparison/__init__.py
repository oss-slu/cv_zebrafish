"""
Dataset comparison module for zebrafish kinematic analysis.

This module provides functionality to compare analysis results across multiple
datasets, computing pairwise differences in summary metrics and other statistics.
"""

from .comparison_engine import (
    compare_datasets,
    generate_comparison_report,
    compare_two_fish,
    get_speed_comparison
)

__all__ = [
    'compare_datasets',
    'generate_comparison_report', 
    'compare_two_fish',
    'get_speed_comparison'
]

__version__ = '1.0.0'
