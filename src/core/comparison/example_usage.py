"""
Example usage of the dataset comparison engine.

This script demonstrates how to use the comparison engine with simulated
zebrafish analysis data that matches the actual Driver.py output structure.
"""

import pandas as pd
import numpy as np
from comparison_engine import compare_datasets, generate_comparison_report, get_speed_comparison


def create_sample_zebrafish_data(name: str, base_seed: int = 42) -> pd.DataFrame:
    """
    Create sample zebrafish analysis data that matches Driver.py output structure.
    
    Args:
        name: Name identifier for the dataset (affects the random characteristics)
        base_seed: Base seed for reproducible random data
        
    Returns:
        DataFrame with columns matching those produced by Driver.run_calculations()
    """
    # Use name hash to create different characteristics per fish
    name_seed = base_seed + hash(name) % 1000
    np.random.seed(name_seed)
    
    # Different fish have different activity levels and frame counts
    if "active" in name.lower():
        n_frames = np.random.randint(1200, 1500)
        activity_multiplier = 1.5
    elif "calm" in name.lower():
        n_frames = np.random.randint(800, 1000) 
        activity_multiplier = 0.7
    else:
        n_frames = np.random.randint(1000, 1200)
        activity_multiplier = 1.0
    
    # Generate realistic zebrafish kinematics data
    df = pd.DataFrame({
        # Basic time series
        'Time': np.arange(n_frames),
        
        # Fin angles (degrees) - main behavioral indicators
        'LF_Angle': np.random.normal(45 * activity_multiplier, 10 + activity_multiplier * 5, n_frames),
        'RF_Angle': np.random.normal(42 * activity_multiplier, 12 + activity_multiplier * 3, n_frames),
        
        # Head orientation and position
        'HeadYaw': np.random.normal(0, 15 * activity_multiplier, n_frames),
        'HeadX': np.random.normal(0.01, 0.002 * activity_multiplier, n_frames),
        'HeadY': np.random.normal(0.01, 0.002 * activity_multiplier, n_frames),
        
        # Tail metrics - key for speed/movement analysis
        'Tail_Angle': np.random.normal(20 * activity_multiplier, 8, n_frames),
        'Tail_Distance': np.random.normal(0.015 * activity_multiplier, 0.005, n_frames),
        'Tail_Distance_Pixels': np.random.normal(150 * activity_multiplier, 50, n_frames),
        
        # Tail side and furthest point
        'Tail_Side': np.random.choice([-1, 1], n_frames),
        'Furthest_Tail_Point': np.random.randint(0, 10, n_frames),
        
        # Spine segment angles (from calc_spine_angles)
        'TailAngle_0': np.random.normal(10 * activity_multiplier, 5, n_frames),
        'TailAngle_1': np.random.normal(15 * activity_multiplier, 6, n_frames),
        'TailAngle_2': np.random.normal(12 * activity_multiplier, 4, n_frames),
        
        # Peak detection results (boolean-like)
        'leftFinPeaks': np.random.choice([0, 1], n_frames, p=[0.95, 0.05]),
        'rightFinPeaks': np.random.choice([0, 1], n_frames, p=[0.95, 0.05]),
        
        # Bout-relative head yaw (often empty strings, sometimes numeric)
        'curBoutHeadYaw': [''] * n_frames,  # Simplified for this example
    })
    
    # Add some time range columns (bout detection results)
    df['timeRangeStart_0'] = [0] + [''] * (n_frames - 1)
    df['timeRangeEnd_0'] = [n_frames - 1] + [''] * (n_frames - 1)
    
    return df


def main():
    """Demonstrate the comparison engine with realistic zebrafish data."""
    
    print("🐠 Zebrafish Dataset Comparison Engine Demo")
    print("=" * 50)
    
    # Create sample datasets with different characteristics
    datasets = {
        'ActiveFish_A': create_sample_zebrafish_data('ActiveFish_A', 42),
        'CalmFish_B': create_sample_zebrafish_data('CalmFish_B', 123), 
        'NormalFish_C': create_sample_zebrafish_data('NormalFish_C', 456)
    }
    
    print(f"Created {len(datasets)} sample datasets:")
    for name, df in datasets.items():
        print(f"  - {name}: {len(df)} frames, {len(df.columns)} metrics")
    
    print("\n🔍 Running comparison analysis...")
    
    # Run the comparison
    try:
        comparison_results = compare_datasets(datasets)
        print("✅ Comparison completed successfully!")
        
        # Display summary information
        summary = comparison_results['summary']
        print(f"\n📊 Comparison Summary:")
        print(f"   Datasets: {', '.join(summary['datasets'])}")
        print(f"   Pairwise comparisons: {summary['comparison_count']}")
        print(f"   Common metrics: {len(summary['common_metrics'])}")
        print(f"   Available metrics: {len(summary['available_metrics'])}")
        
        # Show a few key comparisons
        print(f"\n🔬 Key Metric Differences:")
        for pair_name, pair_data in comparison_results['pairwise'].items():
            print(f"\n  {pair_name}:")
            print(f"    Frame count difference: {pair_data['frame_count_difference']:+d}")
            
            # Show differences for key behavioral metrics
            key_metrics = ['LF_Angle', 'RF_Angle', 'Tail_Distance', 'HeadYaw']
            for metric in key_metrics:
                if metric in pair_data['mean_differences']:
                    diff = pair_data['mean_differences'][metric]
                    print(f"    {metric} mean difference: {diff:+.3f}")
        
        # Demonstrate speed-focused analysis
        print(f"\n🏃 Speed-Related Comparisons:")
        speed_comparisons = get_speed_comparison(comparison_results)
        for pair_name, speed_diffs in speed_comparisons.items():
            print(f"  {pair_name}:")
            for metric, diff in speed_diffs.items():
                print(f"    {metric}: {diff:+.6f}")
        
        # Generate and display a portion of the text report
        print(f"\n📄 Sample Text Report (first 500 characters):")
        report = generate_comparison_report(comparison_results)
        print(report[:500] + "..." if len(report) > 500 else report)
        
        print(f"\n✨ Demo completed successfully!")
        print(f"   The comparison engine is working correctly and ready for integration.")
        
    except Exception as e:
        print(f"❌ Error during comparison: {e}")
        raise


if __name__ == "__main__":
    main()
