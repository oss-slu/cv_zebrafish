"""
Unit tests for the dataset comparison engine.

Tests all major functionality including normal comparisons, edge cases,
and error handling to ensure the comparison engine is robust and reliable.
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, Any

from .comparison_engine import (
    compare_datasets,
    generate_comparison_report,
    compare_two_fish,
    get_speed_comparison
)


class TestComparisonEngine:
    """Test suite for the dataset comparison engine."""
    
    def setup_method(self):
        """Set up test data that mimics real zebrafish analysis results."""
        # Create realistic test DataFrames that match Driver.py output structure
        
        # Fish 1: Slower, fewer frames
        np.random.seed(42)  # For reproducible tests
        n_frames_1 = 1000
        
        self.fish1_df = pd.DataFrame({
            'Time': np.arange(n_frames_1),
            'LF_Angle': np.random.normal(45, 10, n_frames_1),  # Left fin angle
            'RF_Angle': np.random.normal(42, 12, n_frames_1),  # Right fin angle  
            'HeadYaw': np.random.normal(0, 15, n_frames_1),    # Head yaw
            'Tail_Distance': np.random.normal(0.015, 0.005, n_frames_1),  # Tail distance in meters
            'HeadX': np.random.normal(0.01, 0.002, n_frames_1),
            'HeadY': np.random.normal(0.01, 0.002, n_frames_1),
            'Tail_Angle': np.random.normal(20, 8, n_frames_1),
            'TailAngle_0': np.random.normal(10, 5, n_frames_1),
            'TailAngle_1': np.random.normal(15, 6, n_frames_1),
        })
        
        # Fish 2: Faster, more frames
        np.random.seed(123)
        n_frames_2 = 1200
        
        self.fish2_df = pd.DataFrame({
            'Time': np.arange(n_frames_2),
            'LF_Angle': np.random.normal(52, 15, n_frames_2),  # Higher mean, more variance
            'RF_Angle': np.random.normal(48, 14, n_frames_2),
            'HeadYaw': np.random.normal(2, 18, n_frames_2),
            'Tail_Distance': np.random.normal(0.022, 0.007, n_frames_2),  # Higher speed
            'HeadX': np.random.normal(0.012, 0.003, n_frames_2),
            'HeadY': np.random.normal(0.011, 0.0025, n_frames_2),
            'Tail_Angle': np.random.normal(25, 10, n_frames_2),
            'TailAngle_0': np.random.normal(12, 6, n_frames_2),
            'TailAngle_1': np.random.normal(18, 7, n_frames_2),
        })
        
        # Fish 3: Missing some metrics (tests graceful handling)
        np.random.seed(456)
        n_frames_3 = 800
        
        self.fish3_df = pd.DataFrame({
            'Time': np.arange(n_frames_3),
            'LF_Angle': np.random.normal(40, 8, n_frames_3),
            'RF_Angle': np.random.normal(38, 9, n_frames_3),
            'HeadYaw': np.random.normal(-1, 12, n_frames_3),
            # Note: Missing Tail_Distance, HeadX, HeadY
            'Tail_Angle': np.random.normal(18, 6, n_frames_3),
            'TailAngle_0': np.random.normal(9, 4, n_frames_3),
            # Note: Missing TailAngle_1
        })
        
        # Empty DataFrame (edge case)
        self.empty_df = pd.DataFrame()
        
        # Single row DataFrame (edge case)
        self.single_row_df = pd.DataFrame({
            'Time': [0],
            'LF_Angle': [45.0],
            'RF_Angle': [42.0],
            'HeadYaw': [0.0],
            'Tail_Distance': [0.015]
        })
    
    def test_basic_two_dataset_comparison(self):
        """Test basic functionality with two normal datasets."""
        results = {
            'Fish1': self.fish1_df,
            'Fish2': self.fish2_df
        }
        
        comparison = compare_datasets(results)
        
        # Check structure
        assert 'summary' in comparison
        assert 'pairwise' in comparison
        assert 'dataset_summaries' in comparison
        
        # Check summary
        summary = comparison['summary']
        assert summary['dataset_count'] == 2
        assert set(summary['datasets']) == {'Fish1', 'Fish2'}
        assert summary['comparison_count'] == 1
        
        # Check pairwise comparison
        assert 'Fish1_vs_Fish2' in comparison['pairwise']
        pair_comp = comparison['pairwise']['Fish1_vs_Fish2']
        
        # Should have mean differences for common metrics
        assert 'mean_differences' in pair_comp
        assert 'LF_Angle' in pair_comp['mean_differences']
        assert 'RF_Angle' in pair_comp['mean_differences']
        assert 'HeadYaw' in pair_comp['mean_differences']
        
        # Check frame count difference
        expected_frame_diff = len(self.fish2_df) - len(self.fish1_df)
        assert pair_comp['frame_count_difference'] == expected_frame_diff
        
        # Check that differences are reasonable numbers
        lf_diff = pair_comp['mean_differences']['LF_Angle']
        assert isinstance(lf_diff, (int, float))
        assert not np.isnan(lf_diff)
    
    def test_three_dataset_comparison(self):
        """Test with three datasets (multiple pairwise comparisons)."""
        results = {
            'Fish1': self.fish1_df,
            'Fish2': self.fish2_df, 
            'Fish3': self.fish3_df
        }
        
        comparison = compare_datasets(results)
        
        # Should have 3 pairwise comparisons: 1v2, 1v3, 2v3
        assert comparison['summary']['dataset_count'] == 3
        assert comparison['summary']['comparison_count'] == 3
        
        expected_pairs = {'Fish1_vs_Fish2', 'Fish1_vs_Fish3', 'Fish2_vs_Fish3'}
        assert set(comparison['pairwise'].keys()) == expected_pairs
    
    def test_missing_metrics_handling(self):
        """Test graceful handling when datasets have different metrics."""
        results = {
            'Complete': self.fish1_df,
            'Incomplete': self.fish3_df  # Missing some columns
        }
        
        comparison = compare_datasets(results)
        pair_comp = comparison['pairwise']['Complete_vs_Incomplete']
        
        # Should identify metrics only in complete dataset
        assert 'Tail_Distance' in pair_comp['metrics_only_in_a']
        assert 'TailAngle_1' in pair_comp['metrics_only_in_a']
        
        # Should still compare common metrics
        assert 'LF_Angle' in pair_comp['common_metrics']
        assert 'RF_Angle' in pair_comp['common_metrics']
        assert 'HeadYaw' in pair_comp['common_metrics']
        
        # Mean differences should only include common metrics
        common_in_diffs = set(pair_comp['mean_differences'].keys())
        common_metrics = set(pair_comp['common_metrics'])
        assert common_in_diffs == common_metrics
    
    def test_single_dataset_error(self):
        """Test that single dataset raises appropriate error."""
        results = {'OnlyFish': self.fish1_df}
        
        with pytest.raises(ValueError, match="At least 2 datasets are required"):
            compare_datasets(results)
    
    def test_empty_results_dict_error(self):
        """Test that empty results dict raises appropriate error."""
        with pytest.raises(ValueError, match="results_dict cannot be empty"):
            compare_datasets({})
    
    def test_invalid_dataframe_type_error(self):
        """Test that non-DataFrame input raises appropriate error."""
        results = {
            'Fish1': self.fish1_df,
            'NotDataFrame': {'some': 'dict'}  # Invalid type
        }
        
        with pytest.raises(TypeError, match="must be a pandas DataFrame"):
            compare_datasets(results)
    
    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrames."""
        results = {
            'Fish1': self.fish1_df,
            'Empty': self.empty_df
        }
        
        # Should not crash, but might issue warnings
        comparison = compare_datasets(results)
        
        # Empty dataset should have zero frame count
        empty_summary = comparison['dataset_summaries']['Empty']
        assert empty_summary['frame_count'] == 0
        assert len(empty_summary['metrics']) == 0
    
    def test_single_row_dataframe(self):
        """Test handling of single-row DataFrames."""
        results = {
            'Fish1': self.fish1_df,
            'SingleRow': self.single_row_df
        }
        
        comparison = compare_datasets(results)
        
        # Should complete without error
        assert 'Fish1_vs_SingleRow' in comparison['pairwise']
        
        # Single row dataset should have frame count of 1
        single_summary = comparison['dataset_summaries']['SingleRow']
        assert single_summary['frame_count'] == 1
    
    def test_include_metrics_filter(self):
        """Test filtering to include only specific metrics."""
        results = {
            'Fish1': self.fish1_df,
            'Fish2': self.fish2_df
        }
        
        # Only compare fin angles
        comparison = compare_datasets(results, include_metrics=['LF_Angle', 'RF_Angle'])
        
        pair_comp = comparison['pairwise']['Fish1_vs_Fish2']
        
        # Should only have specified metrics
        expected_metrics = {'LF_Angle', 'RF_Angle'}
        assert set(pair_comp['mean_differences'].keys()) == expected_metrics
        assert set(pair_comp['common_metrics']) == expected_metrics
    
    def test_exclude_metrics_filter(self):
        """Test filtering to exclude specific metrics."""
        results = {
            'Fish1': self.fish1_df,
            'Fish2': self.fish2_df
        }
        
        # Exclude head-related metrics
        comparison = compare_datasets(results, exclude_metrics=['HeadYaw', 'HeadX', 'HeadY'])
        
        pair_comp = comparison['pairwise']['Fish1_vs_Fish2']
        
        # Should not have excluded metrics
        mean_diff_metrics = set(pair_comp['mean_differences'].keys())
        assert 'HeadYaw' not in mean_diff_metrics
        assert 'HeadX' not in mean_diff_metrics
        assert 'HeadY' not in mean_diff_metrics
        
        # Should still have other metrics
        assert 'LF_Angle' in mean_diff_metrics
        assert 'RF_Angle' in mean_diff_metrics
    
    def test_detailed_metric_comparisons(self):
        """Test that detailed metric comparisons contain expected fields."""
        results = {
            'Fish1': self.fish1_df,
            'Fish2': self.fish2_df
        }
        
        comparison = compare_datasets(results)
        pair_comp = comparison['pairwise']['Fish1_vs_Fish2']
        
        # Check detailed comparison structure
        detailed = pair_comp['detailed_comparisons']
        assert 'LF_Angle' in detailed
        
        lf_detail = detailed['LF_Angle']
        required_fields = ['Fish1', 'Fish2', 'mean_difference', 'std_difference', 'percent_change_mean', 'range_overlap']
        for field in required_fields:
            assert field in lf_detail
        
        # Check that statistics are reasonable
        fish1_stats = lf_detail['Fish1']
        assert all(stat in fish1_stats for stat in ['mean', 'std', 'min', 'max', 'count', 'median'])
        assert fish1_stats['count'] == len(self.fish1_df)
    
    def test_convenience_functions(self):
        """Test convenience functions work correctly."""
        # Test compare_two_fish
        comparison = compare_two_fish(self.fish1_df, self.fish2_df, "TestFish1", "TestFish2")
        
        assert comparison['summary']['dataset_count'] == 2
        assert 'TestFish1_vs_TestFish2' in comparison['pairwise']
        
        # Test get_speed_comparison (should find Tail_Distance)
        speed_comp = get_speed_comparison(comparison)
        assert len(speed_comp) > 0
        
        # Should find Tail_Distance as speed-related
        pair_speeds = speed_comp['TestFish1_vs_TestFish2']
        assert 'Tail_Distance' in pair_speeds
    
    def test_comparison_report_generation(self):
        """Test that comparison report generates without errors."""
        results = {
            'Fish1': self.fish1_df,
            'Fish2': self.fish2_df
        }
        
        comparison = compare_datasets(results)
        report = generate_comparison_report(comparison)
        
        # Should be a string
        assert isinstance(report, str)
        assert len(report) > 0
        
        # Should contain key information
        assert 'COMPARISON REPORT' in report
        assert 'Fish1' in report
        assert 'Fish2' in report
        assert 'Frame count difference:' in report


def test_module_imports():
    """Test that all public functions can be imported."""
    from comparison_engine import (
        compare_datasets,
        generate_comparison_report,
        compare_two_fish,
        get_speed_comparison
    )
    
    # If we get here without import errors, the module is properly structured
    assert callable(compare_datasets)
    assert callable(generate_comparison_report)
    assert callable(compare_two_fish)
    assert callable(get_speed_comparison)


if __name__ == "__main__":
    # Allow running tests directly: python test_comparison_engine.py
    pytest.main([__file__, "-v"])
