from cvzebrafish.core.calculations.Driver import run_calculations
from cvzebrafish.core.config.configSetup import loadConfig
from cvzebrafish.core.graphs.outputDisplay import make_outputs
from cvzebrafish.core.parsing.Parser import parse_dlc_csv

def run_full_pipeline(csv_path, config_path=None):
    config = loadConfig(config_path) if config_path else loadConfig("LastConfig.json")
    parsed_points = parse_dlc_csv(csv_path, config)
    result_df = run_calculations(parsed_points, config)
    make_outputs(result_df, config)

# Now call this ONLY in your orchestrator, never on import.
if __name__ == "__main__":
    run_full_pipeline("correct_format.csv")


