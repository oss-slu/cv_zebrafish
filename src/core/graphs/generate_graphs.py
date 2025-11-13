#!/usr/bin/env python3
"""Generate all graphs from enriched CSV.

Usage:
    python src/core/graphs/generate_graphs.py \
        \data\samples\csv\calculated_data_enriched.csv \
        \data\samples\jsons\BaseConfig.json
"""

import argparse
import sys
from pathlib import Path

# Add repo to path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphs.data_loader import GraphDataLoader
from graphs.outputDisplay import runAllOutputs, getOutputFile


def main(csv_path: str, config_path: str):
    """Generate all graphs from enriched CSV."""
    
    print(f"\n{'='*60}")
    print("Loading data...")
    print(f"{'='*60}\n")
    
    # Load data
    loader = GraphDataLoader(csv_path, config_path)
    
    print(f"✓ Loaded CSV with {len(loader.df)} frames")
    print(f"✓ Found {len(loader.time_ranges)} time ranges: {loader.time_ranges}")
    
    # Get structures for outputDisplay.py
    inputValues = loader.get_input_values()
    calculatedValues = loader.get_calculated_values()
    timeRanges = loader.get_time_ranges()
    df = loader.get_dataframe()
    config = loader.get_config()
    
    print(f"✓ Reconstructed {len(inputValues['spine'])} spine points")
    
    # Initialize output folder
    print(f"\n{'='*60}")
    print("Initializing output folder...")
    print(f"{'='*60}\n")
    getOutputFile(config)
    
    # Create results list
    resultsList = [{} for _ in timeRanges]
    
    # Generate all graphs!
    print(f"\n{'='*60}")
    print("Generating graphs...")
    print(f"{'='*60}\n")
    
    runAllOutputs(
        timeRanges=timeRanges,
        config=config,
        resultsList=resultsList,
        inputValues=inputValues,
        calculatedValues=calculatedValues,
        df=df
    )
    
    print(f"\n{'='*60}")
    print("✓ All graphs generated successfully!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate graphs from enriched CSV"
    )
    parser.add_argument(
        "csv_file",
        help="Path to enriched CSV from export_enriched_results.py"
    )
    parser.add_argument(
        "config",
        help="Path to configuration JSON file"
    )
    args = parser.parse_args()
    
    try:
        main(args.csv_file, args.config)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)