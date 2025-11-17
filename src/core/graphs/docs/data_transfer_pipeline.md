# Graphing Pipeline: Enriched CSV → GraphDataLoader → output_adapter → outputDisplay

This document dives into the exact data flow that turns an "enriched" CSV into the inputs consumed by the plotting layer. It focuses on:

- What the enriched CSV must contain and how key fields are interpreted
- How `GraphDataLoader` parses and validates the data
- How `output_adapter.py` orchestrates loading and adapts structures for the legacy plotting code
- What `outputDisplay.py` expects and why the adapter converts the spine structure

If you are building new plots or debugging legacy ones, this is the contract you should rely on.

---

## Big picture

```
Enriched CSV (+ Config JSON)
        |
        v
GraphDataLoader(csv_path, config_path)
        |  ├─ Validates required columns
        |  ├─ Parses time ranges from row 0
        |  ├─ Exposes data via accessor methods
        v
output_adapter.run_full_pipeline(enriched_csv_path, config_path)
        |  ├─ loader.get_time_ranges()        → [[start, end], ...]
        |  ├─ loader.get_input_values()       → nested dicts (spine/fin/tail/head/tp)
        |  ├─ loader.get_calculated_values()  → flat arrays (angles, distances, pixels)
        |  ├─ convert_spine_for_legacy(...)   → per-frame spine dicts
        |  └─ runAllOutputs(...)              → legacy plotting entry
        v
outputDisplay.py (legacy plotting)
```

---

## The enriched CSV

The enriched CSV is the output of the calculations pipeline. A few conventions matter for graphing:

- Columns for core metrics (examples):
  - `Time`, `LF_Angle`, `RF_Angle`, `HeadYaw`, `Tail_Distance`, `Tail_Angle`
- Position columns (pixel space) as available:
  - `HeadPX`, `HeadPY`, `TailPX`, `TailPY`
  - Raw DLC outputs (optional): `DLC_HeadPX`, `DLC_HeadPY`, `DLC_HeadPConf`, `DLC_TailPX`, `DLC_TailPY`, `DLC_TailPConf`
- Per-point positions for anatomy:
  - Spine: `Spine_{label}_x`, `Spine_{label}_y`, `Spine_{label}_conf`
  - Left fin: `LeftFin_{label}_x`, `LeftFin_{label}_y`, `LeftFin_{label}_conf`
  - Right fin: `RightFin_{label}_x`, `RightFin_{label}_y`, `RightFin_{label}_conf`
  - Tail: `Tail_{label}_x`, `Tail_{label}_y`, `Tail_{label}_conf`
- Bout/time-range markers live in row 0:
  - `timeRangeStart_0`, `timeRangeEnd_0`, `timeRangeStart_1`, `timeRangeEnd_1`, ...

Minimum required columns are tracked in `graphing/data_loader.py` under `REQUIRED_COLUMNS`.

---

## GraphDataLoader: responsibilities and contracts

Defined in `graphing/data_loader.py`, the `GraphDataLoader` is the single source of truth for parsing and exposing graph-ready data.

### Initialization

```python
loader = GraphDataLoader(csv_path="enriched.csv", config_path="BaseConfig.json")
```

- Loads CSV into a pandas DataFrame
- Loads config JSON (see below for required keys)
- Validates required columns and parses time ranges from row 0

### Accessor methods used by the adapter

- `get_time_ranges() -> List[List[int]]`
  - Returns `[[start_frame, end_frame], ...]` derived from row 0 markers
  - If no markers exist, falls back to the full range: `[[0, len(df) - 1]]`

- `get_input_values() -> Dict[str, Any]`
  - Reconstructs nested structures for anatomy points, each as arrays over frames
  - Example keys:
    - `spine`: list of dicts (one per spine point) with `'x'`, `'y'`, `'conf'` arrays
    - `left_fin`, `right_fin`, `tail`: same pattern by structure
    - `tailPoints`: list of tail labels
    - `head`: single dict with `'x'`, `'y'`, `'conf'` arrays (from DLC head)
    - `tp`: tail base with `'x'`, `'y'`, `'conf'` arrays (from DLC tail)
    - `clp1`, `clp2`: references to the spine points used for head centerline
  - All labels are driven by `config["points"]` to remain schema-agnostic

- `get_calculated_values() -> Dict[str, np.ndarray]`
  - Flat arrays of calculated metrics and positions required by legacy plots
  - Example keys: `headX`, `headY`, `leftFinAngles`, `rightFinAngles`, `tailAngles`, `tailDistances`, `headYaw`, `headPixelsX`, `headPixelsY`, `tailPixelsX`, `tailPixelsY`

- `get_config() -> Dict[str, Any]`, `get_dataframe() -> pd.DataFrame`
  - Provide the config (defensive copy) and the raw DataFrame for plotting modules

### Configuration expectations

Config JSON must include at least:

```json
{
  "points": {
    "spine": ["0", "1", "2", "3", ...],
    "left_fin": ["0", "1"],
    "right_fin": ["0", "1"],
    "tail": ["0", "1", ...],
    "head": {"pt1": "0", "pt2": "1"}
  },
  "video_parameters": {
    "recorded_framerate": 30,
    "pixel_scale_factor": 1.0
  },
  "shown_outputs": { ... },
  "spine_plot_settings": { ... }
}
```

---

## Why the adapter converts the spine structure

`outputDisplay.py` (legacy) expects the `spine` array in a per-frame format:

```python
# Legacy expectation (outputDisplay.py):
spine[spinePoint][frame]['conf']  # index by frame inside each spine point
```

But `GraphDataLoader.get_input_values()` returns spine as arrays over frames for each point:

```python
# Loader format (modern): one dict per spine point holding arrays
spine = [
  { 'x': np.ndarray(shape=(N,)), 'y': ..., 'conf': ... },  # point 0 across N frames
  { 'x': np.ndarray(shape=(N,)), 'y': ..., 'conf': ... },  # point 1 across N frames
  ...
]
```

To bridge this difference, the adapter performs a one-time conversion to a per-frame list of dicts per spine point.

---

## output_adapter.py: execution path

`graphing/output_adapter.py` wires the pieces together. Current implementation:

```python
from graphing.data_loader import GraphDataLoader
from graphing.outputDisplay import getOutputFile, runAllOutputs

# Converts loader-style spine (arrays per point) to legacy spine (per-frame dicts)
def convert_spine_for_legacy(inputValues):
    spine = inputValues['spine']
    n_points = len(spine)
    n_frames = len(spine[0]['x'])
    legacy_spine = []
    for pt_idx in range(n_points):
        pt = spine[pt_idx]
        pt_list = []
        for f in range(n_frames):
            pt_list.append({
                'x': float(pt['x'][f]),
                'y': float(pt['y'][f]),
                'conf': float(pt['conf'][f])
            })
        legacy_spine.append(pt_list)
    return legacy_spine

# Orchestrates loader → legacy plotting
def run_full_pipeline(enriched_csv_path, config_path=None):
    loader = GraphDataLoader(
        csv_path=enriched_csv_path,
        config_path=config_path if config_path else "LastConfig.json"
    )
    config = loader.get_config()
    df = loader.get_dataframe()
    timeRanges = loader.get_time_ranges()
    inputValues = loader.get_input_values()
    inputValues['spine'] = convert_spine_for_legacy(inputValues)  # critical conversion
    calculatedValues = loader.get_calculated_values()
    resultsList = [{} for _ in range(len(timeRanges))]

    getOutputFile(config)  # sets up results folder and log
    runAllOutputs(timeRanges, config, resultsList, inputValues, calculatedValues, df)
```

### Key points

- `GraphDataLoader` is the source of truth for parsing; `output_adapter` does no CSV reading itself.
- `convert_spine_for_legacy` is required because legacy code indexes spine data by frame first.
- All other structures from the loader (`left_fin`, `right_fin`, `tail`, `head`, `tp`, calculated arrays) already match legacy expectations.
- The adapter calls `getOutputFile(config)` to create a numbered results folder and then invokes `runAllOutputs`.

---

## Sequence diagram

```
User code
  |
  | run_full_pipeline("test_enriched.csv", "LastConfig.json")
  v
output_adapter.run_full_pipeline
  |
  |  GraphDataLoader(csv, config)
  |    - read CSV
  |    - read config
  |    - validate columns
  |    - parse time ranges
  |    - prepare structures
  |
  |  loader.get_time_ranges()         → [[s,e], ...]
  |  loader.get_input_values()        → dict with arrays
  |  convert_spine_for_legacy(...)    → per-frame dicts for spine
  |  loader.get_calculated_values()   → flat arrays
  |  getOutputFile(config)            → results/Results N/
  |  runAllOutputs(...)               → render plots + write files
  v
results/Results N/
  - spine_plots_tabbed.html / .png
  - FinAndTailCombined.html / .png
  - head_plot.png
  - log.txt
  - etc.
```

---

## Error handling and edge cases

- Missing columns: `GraphDataLoader` raises `MissingColumnError` with names of required columns.
- Malformed time ranges: If `timeRangeStart_i` / `timeRangeEnd_i` row 0 values can’t be parsed, `MalformedBoutRangeError` is raised.
- No time ranges: Falls back to a single `[0, len(df)-1]` range.
- Missing confidence columns: Loader defaults confidence to `1.0` when not present.
- NaNs: Numeric series may include `NaN`. The legacy plots do not crash on `NaN` but visuals may have gaps.

---

## Practical usage

```python
from graphing.output_adapter import run_full_pipeline

# Generate graphs from an enriched CSV
aaa = run_full_pipeline("test_enriched.csv", "LastConfig.json")
```

If you prefer to use the loader directly for custom plotting:

```python
from graphing.data_loader import GraphDataLoader

loader = GraphDataLoader("test_enriched.csv", "LastConfig.json")
tr = loader.get_time_ranges()
inputs = loader.get_input_values()
calcs = loader.get_calculated_values()
df = loader.get_dataframe()
# Your plotting code here
```

---

## Checklist for adding new metrics

1. Add new column names to `Schema` if they are part of the exported CSV.
2. Include new columns in `REQUIRED_COLUMNS` only if they are mandatory for all runs.
3. Extend `get_calculated_values()` or `get_input_values()` to surface new arrays/structures.
4. Update `outputDisplay.py` or modern plotting code to consume the new fields.
5. Document expected units and shapes in this doc.

---

## Appendix: relevant files

- `graphing/data_loader.py` — GraphDataLoader core (parsing and accessors)
- `graphing/output_adapter.py` — Orchestrates loader → legacy plotting (conversion included)
- `graphing/outputDisplay.py` — Legacy plotting implementation
- `graphing/README.md` — High-level overview and quick start
