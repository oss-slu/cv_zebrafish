from data_loader import GraphDataLoader
from outputDisplay import getOutputFile, runAllOutputs

def convert_spine_for_legacy(inputValues):
    """
    Converts inputValues['spine'] from
      [{'x': ndarray, 'y': ndarray, 'conf': ndarray}, ...]  # one per spine point
    to
      [[{'x', 'y', 'conf'}, ...], ...]  # [spinePoint][frame]
    """
    spine = inputValues['spine']
    n_points = len(spine)
    n_frames = len(spine[0]['x'])
    legacy_spine = []
    for pt_idx in range(n_points):
        pt = spine[pt_idx]
        pt_list = []
        for f in range(n_frames):
            pt_list.append({'x': float(pt['x'][f]), 'y': float(pt['y'][f]), 'conf': float(pt['conf'][f])})
        legacy_spine.append(pt_list)
    return legacy_spine


def run_full_pipeline(config_path=None):
    """
    Run the full graphing pipeline using the latest enriched CSV.
    
    This function expects that export_enriched_calculations.py has already been run
    to generate an enriched CSV and write its path to latest_enriched_csv_path.txt.
    
    Args:
        config_path: Optional path to config JSON. Defaults to BaseConfig.json.
    """
    try:
        loader = GraphDataLoader.from_latest_csv(config_path=config_path or "BaseConfig.json")
    except Exception as e:
        print(f"ERROR: Failed to load data: {e}", file=__import__('sys').stderr)
        print("\nTo generate an enriched CSV, run:", file=__import__('sys').stderr)
        print("  python src/core/calculations/export_enriched_calculations.py \\", file=__import__('sys').stderr)
        print("    --csv data/samples/csv/correct_format.csv \\", file=__import__('sys').stderr)
        print("    --config BaseConfig.json", file=__import__('sys').stderr)
        raise
    
    config = loader.get_config()
    df = loader.get_dataframe()
    timeRanges = loader.get_time_ranges()
    inputValues = loader.get_input_values()
    inputValues['spine'] = convert_spine_for_legacy(inputValues)  # << Convert structure here!
    calculatedValues = loader.get_calculated_values()
    resultsList = [{} for _ in range(len(timeRanges))]  # Placeholder for per-bout results

    getOutputFile(config) 

    runAllOutputs(timeRanges, config, resultsList, inputValues, calculatedValues, df)
    
    print(f"\n✓ Successfully generated graphs for {len(timeRanges)} time range(s)")
    print(f"✓ Output folder: {getattr(__import__('outputDisplay'), 'outputsDict', {}).get('outputFolder', 'results/')}")

if __name__ == "__main__":
    run_full_pipeline()
