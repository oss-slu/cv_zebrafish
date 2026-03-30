# CV Zebrafish

Desktop toolkit for validating DeepLabCut zebrafish CSVs, generating JSON configs, running kinematic calculations, and rendering Plotly graphs through a PyQt UI.

## Quickstart

### Prereqs
- Python 3.10+
- Git
- System packages for Qt (Windows: included with PyQt5 wheels; macOS/Linux may need Qt libraries)

### Setup (Conda)
```bash
conda env create -f environment.yml
conda activate cvzebrafish
```
> `environment.yml` declares Python 3.10 and all app/test dependencies; prefer this over ad-hoc pip installs.

### Run the UI
```bash
python app.py
```
The flow walks through CSV/JSON selection, validation, config generation, calculations, and graph viewing.

### Run tests
```bash
pytest
```

## Project Layout (current)
```text
app.py                         # PyQt entry point (adds src/ to sys.path)
assets/
├── images/                    # UI icons / art
└── sample_data/               # Example configs/CSVs (paired with data/samples)
data/
└── samples/
    ├── csv/                   # DLC CSV fixtures used by UI/tests
    └── jsons/                 # BaseConfig + generated config examples
docs/
├── architecture/              # Calculation/graph design notes
├── howtos/                    # UI + validation how-tos
└── product/                   # Product summary, presentations, meeting minutes
legacy/                        # Bruce pipeline for regression comparisons
src/
├── app_platform/paths.py      # Writable paths/utilities
├── core/
│   ├── calculations/          # Metrics, driver, exports
│   ├── config/configSetup.py  # Config discovery/merging
│   ├── graphs/                # Loader, runner, Plotly plotters (fin/tail, spines)
│   ├── parsing/Parser.py      # DLC CSV parser
│   └── validation/            # CSV/JSON validators + config generator
├── data/                      # DB ingestion helpers
├── session/                   # Session persistence for the UI
└── ui/
    ├── components/            # Shared widgets (sliders, checks, etc.)
    └── scenes/                # Landing, CSV/JSON input, Config Generator, Calculation, Graph Viewer, Verify
tests/
└── unit/                      # Core + UI unit tests (pytest)
```

## Feature Highlights
- **Validation:** CSV/JSON verifiers with structural and likelihood checks.
- **Config generation:** UI scene builds configs from detected body parts and saves JSON.
- **Calculations:** Fin/tail angles, yaw, spine metrics, bout/peak detection, enriched exports.
- **Graphs:** Modular Plotly plotters (fin-tail timelines, spine snapshots) with Kaleido PNG rendering.
- **UI:** Multi-scene PyQt flow with session save/load to resume work.
- **Legacy parity:** Legacy pipeline kept under `legacy/` for comparison.
- - **Dataset Comparison:** Backend comparison engine for analyzing differences across multiple zebrafish datasets, supporting pairwise metric comparison and extensible summary statistics.
  - **Dynamic Body Part Detection:** Automatically detects and groups body parts from any DLC CSV file, supporting variable tracking configurations across different labs without hardcoded assumptions.



## Dataset Comparison Engine

The comparison engine enables analysis of differences between multiple zebrafish datasets.

**Usage:**
```python
from src.core.comparison import compare_datasets

# Compare multiple analysis results
results = {
    "Fish1": dataframe1,  # Output from Driver.run_calculations
    "Fish2": dataframe2,
    "Fish3": dataframe3
}

comparison = compare_datasets(results)
print(comparison['summary'])  # Overview statistics
print(comparison['pairwise']['Fish1_vs_Fish2'])  # Specific comparison



## Dynamic Body Part Detection

The body part detector automatically identifies body parts from any
DLC CSV file, eliminating hardcoded assumptions about tracking configuration.

**Usage:**
```python
from src.core.parsing import (
    detect_body_parts,
    get_body_part_names,
    get_grouped_body_parts,
    detect_body_parts_from_dataframe,
)

# Detect from file (auto-detects format)
result = detect_body_parts('data/samples/csv/correct_format.csv')

print(result.all_body_parts)
# ['BF', 'ET', 'Head', 'LF1', 'LF2', 'LE', 'RE', ...]

print(result.grouped)
# {'spine': ['Head', 'BF', ...], 'left_fin': ['LF1', 'LF2'], ...}

# Convenience functions
names = get_body_part_names('correct_format.csv')
groups = get_grouped_body_parts('correct_format.csv')

# Detect from already-loaded DataFrame
import pandas as pd
df = pd.read_csv('correct_format.csv', header=1)
result = detect_body_parts_from_dataframe(df)

Supported formats:

Raw DLC CSV (scorer / bodyparts / coords header rows)
Enriched output CSV (Spine_Head_x, LeftFin_LF1_x column pattern)
Features:

Automatically detects CSV format (raw DLC or enriched output)
Dynamically discovers all body parts without hardcoded names
Groups body parts by category (spine, left_fin, right_fin, eyes)
Handles unknown/custom body parts gracefully (unknown group)
Works with any number of body parts across different labs
Returns column map for downstream pipeline consumption
Does not crash when body part counts vary across datasets

{
    "all_body_parts": ["BF", "ET", "Head", "LF1", ...],
    "grouped": {
        "spine": ["Head", "BF", "SB", "T1", ...],
        "left_fin": ["LF1", "LF2"],
        "right_fin": ["RF1", "RF2"],
        "eyes": ["LE", "RE"]
    },
    "source_type": "dlc_raw",
    "column_map": {
        "Head": {"x": 1, "y": 2, "conf": 3},
        "BF":   {"x": 4, "y": 5, "conf": 6},
        ...
    },
    "skipped_columns": [],
    "warnings": [],
    "body_part_count": 20
}


## Known Gaps / Next Steps
- No dependency lockfile; add `requirements.txt`/`conda-lock` if needed.
- No CI or lint/type tooling; add GitHub Actions to run pytest.
