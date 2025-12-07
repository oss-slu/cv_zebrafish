#!/usr/bin/env python3
"""
Simple script to generate head plots (HTML + PNG) from enriched CSV data.

Usage (from repo root):
    python -m src.core.graphs.tests.test_generate_headplot

Common options:
    --csv PATH          Enriched CSV (default: data/samples/csv/calculated_data_enriched.csv)
    --config PATH       Config JSON (default: data/samples/jsons/BaseConfig.json)
    --out-dir DIR       Output directory (default: results)
    --output-dir DIR    Alias for --out-dir
    --open              Open resulting HTML in a browser

Example:
    python -m src.core.graphs.tests.test_generate_headplot \
        --csv data/samples/csv/calculated_data_enriched.csv \
        --config data/samples/jsons/BaseConfig.json \
        --output-dir results/test_headplot_run
"""

import os
import sys
from pathlib import Path


def _find_repo_root(start: Path) -> Path:
    # Walk parents looking for sentinel files that identify project root
    for p in [start] + list(start.parents):
        if (p / "README.md").exists() and (p / "app.py").exists():
            return p
    # Fallback: ascend until we hit directory named 'src'
    for p in start.parents:
        if p.name == "src":
            return p.parent
    # Last resort: four levels up
    return start.parents[4]


REPO_ROOT = _find_repo_root(Path(__file__).resolve())
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.graphs.data_loader import GraphDataLoader
from core.graphs.loader_bundle import GraphDataBundle
from core.graphs.io import get_output_context
from core.graphs.plots.headplot import plot_head


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate head plot (HTML + PNG) from enriched CSV data")
    parser.add_argument("--csv", default="data/samples/csv/calculated_data_enriched.csv",
                        help="Path to enriched CSV (default: data/samples/csv/calculated_data_enriched.csv)")
    parser.add_argument("--config", default="data/samples/jsons/BaseConfig.json",
                        help="Path to config JSON (default: data/samples/jsons/BaseConfig.json)")
    parser.add_argument("--out-dir", dest="out_dir", default="results",
                        help="Output directory (default: results)")
    parser.add_argument("--output-dir", dest="out_dir",
                        help="Alias for --out-dir")
    parser.add_argument("--open", action="store_true",
                        help="Open the plot in browser after generation")
    
    args = parser.parse_args()
    
    # Make paths absolute if they're relative
    csv_path = args.csv if os.path.isabs(args.csv) else os.path.join(REPO_ROOT, args.csv)
    config_path = args.config if os.path.isabs(args.config) else os.path.join(REPO_ROOT, args.config)
    
    print(f"Repository root: {REPO_ROOT}")
    print(f"Loading data from: {csv_path}")
    print(f"Using config: {config_path}")
    
    # Check files exist
    if not os.path.exists(csv_path):
        # Fallback attempt: use canonical sample path
        alt = REPO_ROOT / "data/samples/csv/calculated_data_enriched.csv"
        if alt.exists():
            print(f"CSV not found at provided path; falling back to {alt}")
            csv_path = str(alt)
        else:
            print(f"ERROR: CSV file not found: {csv_path}")
            sys.exit(1)
    if not os.path.exists(config_path):
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)
    
    # Load data through GraphDataLoader
    try:
        loader = GraphDataLoader(csv_path, config_path)
        bundle = GraphDataBundle.from_loader(loader)
    except Exception as e:
        print(f"ERROR loading data: {e}")
        sys.exit(1)
    
    # Extract data needed for head plot
    input_vals = bundle.input_values
    calc_vals = bundle.calculated_values
    
    head_yaw = calc_vals.get("headYaw")
    left_fin_angles = calc_vals.get("leftFinAngles")
    right_fin_angles = calc_vals.get("rightFinAngles")
    time_ranges = input_vals.get("timeRanges")
    
    if head_yaw is None:
        print("ERROR: 'headYaw' not found in calculated values")
        print(f"Available keys: {list(calc_vals.keys())}")
        sys.exit(1)
    if left_fin_angles is None or right_fin_angles is None:
        print("ERROR: Fin angle data not found")
        print(f"Available keys: {list(calc_vals.keys())}")
        sys.exit(1)
    if not time_ranges:
        print("WARNING: No time ranges found, using full dataset")
        time_ranges = [(0, len(head_yaw) - 1)]
    
    # Get output context
    ctx = get_output_context(bundle.config, base_path=args.out_dir)
    
    # Get config settings for head plot
    config = bundle.config
    head_settings = config.get("head_settings", {})
    cutoffs = config.get("graph_cutoffs", {})
    
    # Set defaults if missing
    if "left_fin_angle" not in cutoffs:
        cutoffs["left_fin_angle"] = 10
    if "right_fin_angle" not in cutoffs:
        cutoffs["right_fin_angle"] = 10
    
    default_head_settings = {
        "plot_draw_offset": 15,
        "ignore_synchronized_fin_peaks": True,
        "sync_fin_peaks_range": 3,
        "fin_peaks_for_right_fin": False,
        "split_plots_by_bout": True
    }
    head_settings = {**default_head_settings, **head_settings}
    
    print(f"\nGenerating head plot...")
    print(f"Output directory: {ctx.output_folder}")
    print(f"Note: PNG generation requires compatible kaleido/plotly versions.")
    print(f"      HTML files will be generated regardless.")
    
    # Generate the plot
    try:
        result = plot_head(
            head_yaw=head_yaw,
            left_fin_values=left_fin_angles,
            right_fin_values=right_fin_angles,
            time_ranges=time_ranges,
            head_settings=head_settings,
            cutoffs=cutoffs,
            ctx=ctx,
            open_plot=args.open
        )
        
        print(f"\n✓ Head plot generated successfully!")
        print(f"  Output folder: {ctx.output_folder}")
        print(f"  Number of figures: {len(result.figures)}")
        if result.labels:
            print(f"  Figure labels: {', '.join(result.labels)}")
        print(f"\nFiles created:")
        if head_settings.get("split_plots_by_bout"):
            print(f"  - head_plots_tabbed.html (interactive tabbed view)")
            for label in result.labels:
                print(f"  - {label}.html")
                print(f"  - {label}.png")
        else:
            print(f"  - head_plot_plotly.html")
            print(f"  - head_plot.png")
            
    except Exception as e:
        print(f"ERROR generating plot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
