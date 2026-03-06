"""
Dataset comparison engine for zebrafish kinematic analysis.

Provides functionality to compare analysis results across multiple datasets,
computing pairwise differences in summary metrics like mean speed, frame counts,
and other calculated values.
"""

from __future__ import annotations

import warnings
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import pandas as pd
import numpy as np


def compare_datasets(
    results_dict: Dict[str, pd.DataFrame],
    include_metrics: Optional[List[str]] = None,
    exclude_metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Compare analysis results across multiple zebrafish datasets.
    
    Args:
        results_dict: Dictionary mapping dataset names to their analysis DataFrames
                     (output from Driver.run_calculations)
        include_metrics: Optional list of column names to include in comparison.
                        If None, all numeric columns are included.
        exclude_metrics: Optional list of column names to exclude from comparison.
                        Applied after include_metrics filtering.
    
    Returns:
        Dictionary containing:
        - 'summary': Overall comparison metadata
        - 'pairwise': Pairwise comparisons between all dataset combinations  
        - 'dataset_summaries': Individual dataset summary statistics
        
    Example:
        >>> results = {
        ...     "Fish1": df1,  # DataFrame from run_calculations
        ...     "Fish2": df2
        ... }
        >>> comparison = compare_datasets(results)
        >>> print(comparison['pairwise']['Fish1_vs_Fish2']['mean_differences'])
    """
    if not results_dict:
        raise ValueError("results_dict cannot be empty")
    
    if len(results_dict) < 2:
        raise ValueError("At least 2 datasets are required for comparison")
    
    # Validate inputs
    for name, df in results_dict.items():
        if not isinstance(df, pd.DataFrame):
            raise TypeError(f"Dataset '{name}' must be a pandas DataFrame")
        if df.empty:
            warnings.warn(f"Dataset '{name}' is empty and will be excluded from some comparisons")
    
    # Extract summary statistics for each dataset
    dataset_summaries = {}
    for name, df in results_dict.items():
        dataset_summaries[name] = _extract_dataset_summary(df, include_metrics, exclude_metrics)
    
    # Perform pairwise comparisons
    pairwise_comparisons = {}
    dataset_names = list(results_dict.keys())
    
    for i in range(len(dataset_names)):
        for j in range(i + 1, len(dataset_names)):
            name_a, name_b = dataset_names[i], dataset_names[j]
            comparison_key = f"{name_a}_vs_{name_b}"
            
            pairwise_comparisons[comparison_key] = _compare_two_datasets(
                dataset_summaries[name_a],
                dataset_summaries[name_b],
                name_a,
                name_b
            )
    
    # Generate overall summary
    all_metrics = set()
    for summary in dataset_summaries.values():
        all_metrics.update(summary['metrics'].keys())
    
    comparison_summary = {
        'dataset_count': len(results_dict),
        'datasets': list(results_dict.keys()),
        'comparison_count': len(pairwise_comparisons),
        'available_metrics': sorted(list(all_metrics)),
        'common_metrics': _find_common_metrics(dataset_summaries),
    }
    
    return {
        'summary': comparison_summary,
        'pairwise': pairwise_comparisons,
        'dataset_summaries': dataset_summaries
    }


def _extract_dataset_summary(
    df: pd.DataFrame,
    include_metrics: Optional[List[str]] = None,
    exclude_metrics: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Extract summary statistics from a single dataset DataFrame."""
    
    # Filter to numeric columns only (where we can calculate means, stds, etc.)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    # Apply include/exclude filters
    if include_metrics is not None:
        numeric_cols = [col for col in numeric_cols if col in include_metrics]
    
    if exclude_metrics is not None:
        numeric_cols = [col for col in numeric_cols if col not in exclude_metrics]
    
    # Calculate summary statistics
    metrics = {}
    for col in numeric_cols:
        series = df[col].dropna()  # Remove NaN values for accurate statistics
        
        if len(series) == 0:
            continue  # Skip columns with no valid data
            
        metrics[col] = {
            'mean': float(series.mean()),
            'std': float(series.std()),
            'min': float(series.min()),
            'max': float(series.max()),
            'count': int(len(series)),
            'median': float(series.median())
        }
    
    return {
        'frame_count': len(df),
        'metrics': metrics,
        'column_names': list(df.columns),
        'numeric_columns': numeric_cols
    }


def _compare_two_datasets(
    summary_a: Dict[str, Any],
    summary_b: Dict[str, Any],
    name_a: str,
    name_b: str
) -> Dict[str, Any]:
    """Compare two dataset summaries and compute differences."""
    
    # Find common metrics between the two datasets
    metrics_a = set(summary_a['metrics'].keys())
    metrics_b = set(summary_b['metrics'].keys())
    common_metrics = metrics_a.intersection(metrics_b)
    
    mean_differences = {}
    std_differences = {}
    metric_comparisons = {}
    
    for metric in common_metrics:
        stats_a = summary_a['metrics'][metric]
        stats_b = summary_b['metrics'][metric]
        
        # Calculate differences (B - A)
        mean_diff = stats_b['mean'] - stats_a['mean']
        std_diff = stats_b['std'] - stats_a['std']
        
        mean_differences[metric] = mean_diff
        std_differences[metric] = std_diff
        
        # Store detailed comparison
        metric_comparisons[metric] = {
            name_a: stats_a,
            name_b: stats_b,
            'mean_difference': mean_diff,
            'std_difference': std_diff,
            'percent_change_mean': (mean_diff / stats_a['mean'] * 100) if stats_a['mean'] != 0 else float('inf'),
            'range_overlap': _check_range_overlap(stats_a, stats_b)
        }
    
    # Frame count comparison
    frame_diff = summary_b['frame_count'] - summary_a['frame_count']
    
    return {
        'dataset_a': name_a,
        'dataset_b': name_b,
        'mean_differences': mean_differences,
        'std_differences': std_differences,
        'frame_count_difference': frame_diff,
        'common_metrics': sorted(list(common_metrics)),
        'metrics_only_in_a': sorted(list(metrics_a - metrics_b)),
        'metrics_only_in_b': sorted(list(metrics_b - metrics_a)),
        'detailed_comparisons': metric_comparisons
    }


def _check_range_overlap(stats_a: Dict[str, float], stats_b: Dict[str, float]) -> bool:
    """Check if the min-max ranges of two metrics overlap."""
    return not (stats_a['max'] < stats_b['min'] or stats_b['max'] < stats_a['min'])


def _find_common_metrics(dataset_summaries: Dict[str, Dict[str, Any]]) -> List[str]:
    """Find metrics that exist in all datasets."""
    if not dataset_summaries:
        return []
    
    common_metrics = set(list(dataset_summaries.values())[0]['metrics'].keys())
    for summary in dataset_summaries.values():
        common_metrics = common_metrics.intersection(set(summary['metrics'].keys()))
    
    return sorted(list(common_metrics))


def generate_comparison_report(comparison_result: Dict[str, Any]) -> str:
    """
    Generate a human-readable text report from comparison results.
    
    Args:
        comparison_result: Output from compare_datasets()
        
    Returns:
        Multi-line string containing formatted comparison report
    """
    report_lines = []
    summary = comparison_result['summary']
    
    report_lines.append("=== ZEBRAFISH DATASET COMPARISON REPORT ===")
    report_lines.append(f"Datasets compared: {', '.join(summary['datasets'])}")
    report_lines.append(f"Number of pairwise comparisons: {summary['comparison_count']}")
    report_lines.append(f"Common metrics across all datasets: {', '.join(summary['common_metrics'])}")
    report_lines.append("")
    
    # Individual dataset summaries
    report_lines.append("--- DATASET SUMMARIES ---")
    for dataset_name, dataset_summary in comparison_result['dataset_summaries'].items():
        report_lines.append(f"{dataset_name}:")
        report_lines.append(f"  Frame count: {dataset_summary['frame_count']}")
        report_lines.append(f"  Available metrics: {len(dataset_summary['metrics'])}")
        
        # Show a few key metrics if available
        key_metrics = ['LF_Angle', 'RF_Angle', 'HeadYaw', 'Tail_Distance']
        for metric in key_metrics:
            if metric in dataset_summary['metrics']:
                stats = dataset_summary['metrics'][metric]
                report_lines.append(f"  {metric}: mean={stats['mean']:.3f}, std={stats['std']:.3f}")
        report_lines.append("")
    
    # Pairwise comparisons
    report_lines.append("--- PAIRWISE COMPARISONS ---")
    for pair_name, pair_data in comparison_result['pairwise'].items():
        report_lines.append(f"{pair_name}:")
        report_lines.append(f"  Frame count difference: {pair_data['frame_count_difference']}")
        
        # Show significant mean differences
        mean_diffs = pair_data['mean_differences']
        if mean_diffs:
            report_lines.append("  Mean differences (B - A):")
            for metric, diff in sorted(mean_diffs.items()):
                report_lines.append(f"    {metric}: {diff:+.3f}")
        report_lines.append("")
    
    return "\n".join(report_lines)


# Convenience functions for common use cases
def compare_two_fish(df1: pd.DataFrame, df2: pd.DataFrame, name1: str = "Fish1", name2: str = "Fish2") -> Dict[str, Any]:
    """Convenience function to compare exactly two datasets."""
    return compare_datasets({name1: df1, name2: df2})


def get_speed_comparison(comparison_result: Dict[str, Any]) -> Dict[str, float]:
    """Extract speed-related metrics from comparison results."""
    speed_metrics = {}
    
    for pair_name, pair_data in comparison_result['pairwise'].items():
        speed_related = {}
        for metric, diff in pair_data['mean_differences'].items():
            # Look for metrics that might be speed-related
            if any(keyword in metric.lower() for keyword in ['speed', 'distance', 'velocity']):
                speed_related[metric] = diff
        
        if speed_related:
            speed_metrics[pair_name] = speed_related
    
    return speed_metrics


__all__ = [
    'compare_datasets',
    'generate_comparison_report', 
    'compare_two_fish',
    'get_speed_comparison'
]
