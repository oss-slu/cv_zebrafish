import json
import sys
from pathlib import Path

import pandas as pd


LEGACY_ROOT = Path(__file__).resolve().parent
LEGACY_CODE_DIR = LEGACY_ROOT / "bruce" / "codes"
CONFIG_FILE = LEGACY_CODE_DIR / "configs" / "BaseConfig.json"
OUTPUT_CSV = LEGACY_ROOT / "legacy_results.csv"


def _ensure_legacy_imports() -> None:
    if not LEGACY_CODE_DIR.exists():
        raise FileNotFoundError(f"Legacy code directory missing: {LEGACY_CODE_DIR}")
    sys.path.insert(0, str(LEGACY_CODE_DIR))


def _load_config() -> dict:
    with CONFIG_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve_input_csv(config: dict) -> Path:
    configured = Path(config["file_inputs"]["data"])
    if configured.exists():
        return configured

    local_input_dir = LEGACY_CODE_DIR.parent / "input_data"
    fallback = local_input_dir / configured.name
    if fallback.exists():
        config["file_inputs"]["data"] = str(fallback)
        return fallback

    raise FileNotFoundError(
        "Unable to locate input CSV referenced in configuration; "
        f"checked {configured} and {fallback}"
    )


def run() -> Path:
    _ensure_legacy_imports()
    from utils.mainCalculation import getCalculated, setupValueStructs

    config = _load_config()
    if config.get("bulk_input"):
        raise ValueError("Bulk input mode is not supported by this helper script.")

    data_path = _resolve_input_csv(config)
    df = pd.read_csv(data_path, header=1)

    calculated_values, input_values = setupValueStructs(config, df)
    results_list, _ = getCalculated(input_values, calculated_values, config, df)

    results_df = pd.DataFrame(results_list)
    results_df.to_csv(OUTPUT_CSV, index=False)
    print(f"Saved legacy calculation results to {OUTPUT_CSV}")
    return OUTPUT_CSV


if __name__ == "__main__":
    run()
