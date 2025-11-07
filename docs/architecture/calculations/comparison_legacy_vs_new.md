# Legacy vs New Calculation Validation

python calculations/compare_calculations.py --csv data_schema_validation/sample_inputs/csv/correct_format.csv --config data_schema_validation/sample_inputs/jsons/BaseConfig.json

## Quick Start: Use the Comparison Script

- Run the packaged helper to execute both pipelines and see discrepancies in one step:
  ```bash
  python calculations/compare_calculations.py --csv ../codes/bruce/codes/input_data/sample.csv --config ../codes/bruce/codes/configs/BaseConfig.json
  ```
- Optional flags:
  - `--export-dir path/to/output` saves the normalized CSVs for deeper inspection.
  - `--atol` / `--rtol` tweak numeric tolerances if small floating-point drift is expected.
- The script prints a summary of matching columns, highlights mismatches, and lists metrics unique to either pipeline so you can interpret differences quickly.

## Manual Prerequisites

- Use the repository root `/mnt/c/Users/Finn/Downloads/SLU/Fall_2025/CSCI_4961/cv_zebrafish` as your working directory.
- Ensure Python 3.9+ is available and that `../codes/bruce/codes` remains untouched aside from imports.
- Decide which sample CSV to use from `../codes/bruce/codes/input_data/` and load a matching config JSON from `../codes/bruce/codes/configs/`.

## Running Both Pipelines Manually

1. Add both codebases to `sys.path` in a comparison script or notebook:
   - `repo_root` for the new implementation (`calculations/utils`).
   - `repo_root/../codes/bruce/codes` for the legacy modules.
2. Parse the CSV and config once:

   ```python
   from calculations.utils.Parser import parse_dlc_csv
   from calculations.utils.Driver import run_calculations
   from utils.mainCalculation import setupValueStructs, getCalculated

   parsed_points = parse_dlc_csv(csv_path, config)
   new_df = run_calculations(parsed_points, config)

   df = pandas.read_csv(csv_path, header=1)  # legacy expects raw frame table
   legacy_calculated, legacy_inputs = setupValueStructs(config, df)
   legacy_rows, time_ranges = getCalculated(legacy_inputs, legacy_calculated, config, df)
   legacy_df = pandas.DataFrame(legacy_rows)
   ```

3. Normalize legacy column names to match the new schema (e.g., `"TailAngle {i}"` → `"TailAngle_{i}"`, `"ET_DistancefromCenterline"` → `"Tail_Distance"`, `"ET_Side"` → `"Tail_Side"`) and append bout metadata from `time_ranges` if desired.
4. Trim the new DataFrame to `new_df_aligned = new_df.iloc[:-1].reset_index(drop=True)` because `getCalculated` omits the final frame.

## Comparing Results

- Identify shared columns before diffing:
  ```python
  shared = sorted(set(new_df_aligned.columns) & set(legacy_df.columns))
  ```
- For numeric columns use a tolerance-aware comparison:

  ```python
  import numpy as np
  import pandas as pd

  for col in shared:
      if pd.api.types.is_numeric_dtype(new_df_aligned[col]):
          mismatched = ~np.isclose(new_df_aligned[col], legacy_df[col], equal_nan=True, atol=1e-6)
          print(col, mismatched.sum())
      else:
          print(col, (new_df_aligned[col] != legacy_df[col]).sum())
  ```

- Investigate any reported differences. Known sources include:
  - The legacy table stores unscaled `"tailRelativePos"` instead of the converted `"Tail_Distance"` unless you rename the field.
  - The new pipeline adds columns such as `"HeadYaw"`, fin peak markers, and numbered bout boundaries that did not exist previously—omit these when focusing on the shared metrics.
