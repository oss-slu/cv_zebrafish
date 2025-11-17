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

def run_full_pipeline(enriched_csv_path, config_path=None):
    loader = GraphDataLoader(
        csv_path=enriched_csv_path,
        config_path=config_path if config_path else "LastConfig.json"
    )
    config = loader.get_config()
    df = loader.get_dataframe()
    timeRanges = loader.get_time_ranges()
    inputValues = loader.get_input_values()
    inputValues['spine'] = convert_spine_for_legacy(inputValues)  # << Convert structure here!
    calculatedValues = loader.get_calculated_values()
    resultsList = [{} for _ in range(len(timeRanges))]  # Placeholder for per-bout results

    getOutputFile(config) 

    runAllOutputs(timeRanges, config, resultsList, inputValues, calculatedValues, df)

if __name__ == "__main__":
    run_full_pipeline("test_enriched.csv")
