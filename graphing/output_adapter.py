from calculations.utils.Driver import run_calculations
from calculations.utils.Parser import parse_dlc_csv
from calculations.utils.configSetup import loadConfig
from graphing.outputDisplay import make_outputs
#from data_schema_validation.sample_inputs.jsons import BaseConfig 

def run_full_pipeline(csv_path, config_path=None):
    config = loadConfig(config_path) if config_path else loadConfig("LastConfig.json")
    parsed_points = parse_dlc_csv(csv_path, config)
    result_df = run_calculations(parsed_points, config)
    make_outputs(result_df, config)

# Now call this ONLY in your orchestrator, never on import.
if __name__ == "__main__":
    run_full_pipeline("correct_format.csv")
