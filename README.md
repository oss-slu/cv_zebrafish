# CV Zebrafish

Desktop toolkit for validating DeepLabCut zebrafish CSVs, generating JSON configs, running kinematic calculations, and rendering Plotly graphs through a PyQt UI.


## Quickstart


### Prereqs
- Python 3.10+
- Git
- System packages for Qt (Windows: included with PyQt5 wheels; macOS/Linux may need Qt libraries)


### Setup
### Conda (recommended)
```bash
conda env create -f environment.yml
conda activate cvzebrafish
```
> `environment.yml` declares Python 3.10 and all app/test dependencies; prefer this over ad-hoc pip installs.
### pip (alternative)
```bash
pip install -r requirements.txt
```


### Run the UI
```bash
python app.py
```
This opens the main windown and starts the step-by-step workflow. The progress indicator shows which scene you're in: the flow walks through CSV/JSON selection, validation, config generation calculations, and graph viewing.


### Run tests
```bash
pytest
```


## User Workflow
The app follows a 6-step linear workflow guided by a progress bar at the top of the window (green = completed, blue = current, gray = upcoming)
| 1 | **Verify Input** | Upload CSV file(s) or a folder + a JSON config; validation runs automatically and results appear in the console below |
| 2 | **Generate Config** | Set body points, video scale, and graph options across tabs, then save to include the new JSON in the current session |
| 3 | **Select Config** | In the session file tree, pick a CSV and a config JSON, then click Run Calculation; right-click rows for extra options |
| 4 | **Run Calculation** | Kinematic metrics computed in a background thread; a progress bar shows status; click Stop to cancel mid-run |
| 5 | **View Graphs** | Browse Plotly graphs by name; use the Compare tab for side-by-side views; use Cross-Correlation for lag analysis |
| 6 | **Export** | PNG figures and enriched CSVs are saved to the configured output directory for reports |




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
legacy/                        # Original pipeline for regression comparisons
src/
├── app_platform/paths.py      # Writable paths/utilities
├── core/
│   ├── calculations/          # Metrics, driver, enriched exports
│   ├── comparison/            # Dataset comparison engine
│   ├── config/configSetup.py  # Config discovery/merging
│   ├── graphs/                # Loader, runner, Plotly plotters (fin/tail, spines)
│   ├── parsing/Parser.py      # DLC CSV parser + body part detection
│   └── validation/            # CSV/JSON validators + config generator
├── data/                      # DB ingestion helpers
├── session/                   # Session persistence for the UI
└── ui/
   ├── components/            # Shared widgets: sliders, checkboxes, ProgressIndicator, etc.
   └── scenes/                # Landing, Verify, Config Generator, Calculation, Graph Viewer (Graphs / Compare / Cross-Correlation tabs)
tests/
└── unit/                      # Core + UI unit tests (pytest)
```


## Feature Highlights
- **Validation:** CSV/JSON verifiers with structural and likelihood checks; pass/fail output
- **Config generation:** UI scene auto-detects body parts from any CSV and saves a JSON config; fields pre-filled when a path is already loaded.
- **Calculations:** Fin/tail angles, yaw, spine metrics, bout/peak detection, custom angle calc, enriched CSV exports.
- **Background Processing:** All calculations run via `QThread` so the UI stays fully responsive; Stop button available mid-run.
- **Graphs:** Modular Plotly plotters (fin-tail timelines, spine snapshots, head orientation) with Kaleido PNG rendering.
- **Interactive Graphs:** Zoom, pan, hover tooltips, and PNG export controls on all Plotly figures.
- **Compare tab:** Side-by-side graph comparison; pick dataset(s) and a graph type for each side (same or different files).
- **Progress Indicator:** Horizontal step bar (green = done, blue = current, gray = upcoming); implemented in `ProgressIndicator.py`
- **Session save/load:** Save the full session (file paths, config, results) at any point; reload to resume exactly where you left off
- **Verify scence:** Single CSV upload, multi-CSV/folder upload, JSON upload, or Generate JSON flow; results shown in console
- **Custom angle calc:** User-defined angle calculations beyond the default fin/tail metrics
- **New CSV format support:** Accepts enriched output CSVs (`Spine_Head_x`, `LeftFin_LF1_x`) alongside raw DLC format
- **Front Size Improvements** Enlarged and standardized UI text for readability across screen sizes
- **UI polish:** Multi-scene PyQt flow  with consistent layout, spacing, and widget sizing across all scenes
- **Dynamic Body Part Detection:** Auto-detects and groups body parts from any DLC CSV file, supporting variable tracking configurations across different labs without hardcoded assumptions.
- **Dataset Comparison:** Backend comparison engine for analyzing differences across multiple zebrafish datasets, supporting pairwise metric comparison and extensible summary statistics.
- **Cross-Correlation Analysis (backend):** Computes cross-correlation between movement signals (coordinates or derived angles) for synchronization and lead/lag analysis.
- **Cross-Correlation UI:** Dedicated Graph Viewer **Cross-Correlation** tab with lag vs correlation plots; pick two signals (e.g. LF_Angle vs RF_Angle) and compute.
- **Multi-CSV navigation:** Graph Viewer Prev/Next plus dataset dropdown for batch runs, with graph titles labeled by source CSV filename.
- **Headplot GUI integration:** Head orientation plots accessible directly from the Graph Viewer
- **In-app Help & Console:** Help icon on every scene explains that scene's controls; Help menu → Console shows recent log/toast text for debugging
- **Legacy parity:** Original console pipeline kept under `legacy/` for regression comparison.


---


## UI Walkthrough
### Help System
Every scene has a **Help icon (?)** that describes exactly what that scene does and what each button is for. When something looks wrong, open **Help menu → Console**, click **Refresh** to load the latest log buffer, select and copy the text, then click **Close**. Most runs don't need this — it's for debugging.

### Scene-by-Scene Guide
**Verify Input**
Click **Upload CSV** to pick one file, or **Upload Multiple CSV** to point at a whole folder (use this for batch runs). Click **Upload JSON** to pick an existing config, or **Generate JSON** to open the config builder if you need a new one. The console below the buttons shows pass/fail and validation messages for every file.
   Tip: Use **Upload Multiple CSV** when you want Select & Run to auto-process every CSV in that folder.

**Generate Config**
Click through the tabs to set body points, video scale, and graph options, then save so the new JSON becomes part of the current session. Select & Run will use that file automatically after you finish. Scroll the window to reach every section.
   Note: If the app opened this dialog with a path already filled in, some fields may be pre-populated from that file.


**Select Configuration**
The session file tree shows your CSV(s) in the first column and their associated config JSONs in the second. Click a CSV row to select it, then click a `.json` in the second column and press **Run Calculation**. Double-clicking a `.json` selects it and starts a run immediately. Right-click a `.json` for options: delete, Generate copy, or View output (when graphs are saved). Right-click a CSV row to delete it. The progress bar shows roughly how much analysis has completed.
   Tip: while a session is in progress the main button reads **Stop** — click it to cancel, then start a different run.


**Graph Viewer**
On the **Graphs tab**, click a name in the list on the left to display that plot on the right. If the session has a folder of CSVs, use the dropdown and **Prev/Next** buttons to choose which file you are viewing.

Open the **Compare tab** to place two standard graphs side by side; pick dataset(s) and a graph type for each side (same or different files).

Open the **Cross-Correlation tab** when you need lag analysis; this is a separate tool from Compare.
   Tip: in Select & Run, when a CSV has more than one config, the tree icon can open View Output for a specific CSV/config pair


### Session Save/Load
At any point you can save the full session (file paths, config, and calculation results) and reload it in a future run to continue from where you stopped; via **File** in the menu bar.

## Configuration
The app uses a JSON config file that describes which body parts to track and which calculations to run. Config files are auto-generated by the UI but are human-readable and editable.


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
```

## Cross-Correlation Analysis
The cross-correlation module enables analysis of temporal relationships
between any two movement signals in the zebrafish dataset: coordinates, angles, or any derived metric.

**Usage:**
```python
from src.core.analysis import (
   compute_cross_correlation_from_dataframe,
   get_available_signals,
   compute_all_pairwise_correlations
)

# Dynamically detect available signals
signals = get_available_signals(results_df)

# Compare two specific signals
result = compute_cross_correlation_from_dataframe(
   results_df, 'LF_Angle', 'RF_Angle'
)
print(f"Peak lag: {result.peak_lag} frames")
print(f"Peak correlation: {result.peak_correlation:.3f}")
print(f"Interpretation: {result._interpret()}")

# Export structured result for UI/visualization
result_dict = result.to_dict()

# Compare all signal pairs at once
all_results = compute_all_pairwise_correlations(results_df)
```


**Features:**
- Works with any numeric column (angles, distances, coordinates)
- Dynamically detects available signals (no hardcoded names)
- Handles missing/NaN values gracefully
- Returns structured output ready for visualization or export
- Includes plain-English interpretation of lead/lag relationships
- Supports pairwise comparison across all available signals


**Output structure:**
```json
{
   "signal_a": "LF_Angle",
   "signal_b": "RF_Angle",
   "lags": [...],           # Frame lag values
   "correlations": [...],   # Correlation at each lag
   "peak_lag": 5,           # Lag with highest correlation
   "peak_correlation": 0.95,
   "n_frames": 1000,
   "warnings": [],
   "interpretation": "LF_Angle leads RF_Angle by 5 frame(s)."
}
```


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

print(result.all_body_parts) # ['BF', 'ET', 'Head', 'LF1', 'LF2', 'LE', 'RE', ...]

print(result.grouped) # {'spine': ['Head', 'BF', ...], 'left_fin': ['LF1', 'LF2'], ...}

# Convenience functions
names = get_body_part_names('correct_format.csv')
groups = get_grouped_body_parts('correct_format.csv')

# Detect from already-loaded DataFrame
import pandas as pd
df = pd.read_csv('correct_format.csv', header=1)
result = detect_body_parts_from_dataframe(df)
```


**Supported input formats:**
- Raw DLC CSV (scorer / bodyparts / coords header rows)
- Enriched output CSV (Spine_Head_x, LeftFin_LF1_x column pattern)


**Output structure:**
- Automatically detects CSV format (raw DLC or enriched output)
- Dynamically discovers all body parts without hardcoded names
- Groups body parts by category (spine, left_fin, right_fin, eyes)
- Handles unknown/custom body parts gracefully (unknown group)
- Works with any number of body parts across different labs
- Returns column map for downstream pipeline consumption
- Does not crash when body part counts vary across datasets


```json
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
```


## Multi-CSV Workflow
The Graph Viewer supports batch processing and comparison of multiple CSV datasets in a single session.

**How to use:**
1. In **Verify**, click **Upload Multiple CSV** and upload a folder
2. Add a config file and proceed to **Select Configuration**
3. Click **Run Calculation** — all CSVs are processed automatically in the background
4. Open **View Output** and use the **Graphs** tab; use the dataset dropdown plus **◀ Prev** / **Next ▶** to navigate between files
5. For cross-correlation on a folder run, use the **CSV file** dropdown in the Cross-Correlation tab to select which dataset's signals to use

**Features:**
- Dataset dropdown lists all processed CSV files by name
- **◀ Prev** and **Next ▶** for sequential navigation (disabled at ends)
- Graph titles prefixed with the source CSV filename (e.g. `fish1.csv — Head Orientation`)
- Single-CSV mode unchanged; navigation controls appear only for batch runs



## Cross-Correlation (Graph Viewer tab)
The Graph Viewer includes a **Cross-Correlation** tab for temporal relationships between movement signals.

### How to Use
1. Run calculations on a CSV (or folder of CSVs) via **Select & Run**
2. Open **View Output** → **Graphs** tab (for context); switch to **Cross-Correlation**
3. For folder runs, pick **CSV file** from the dropdown
4. Select **Signal A** and **Signal B**, then click **Compute Cross-Correlation**

### What the Plot Shows
- **X-axis (Lag):** Frame offset: Positive lag means A leads B; negative means B leads A.
- **Y-axis (Correlation):** Strength at each lag (-1 to +1)
- **Red X marker:** Peak correlation point
- **Gray dashed line:** Zero lag reference

### Example Use Cases
- **Fin coordination:** Left vs right fin synchronization
- **Body wave:** Head vs tail propagation timing
- **Reflex timing:** Stimulus–response lag estimation

### Technical Details
- **Algorithm:** Normalized cross-correlation (FFT-based)
- **Missing data:** NaN frames excluded before computation
- **Lag range:** Defaults to +-25% of signal length (capped)


---


## Testing
All tests use [pytest](https://docs.pytest.org/) and live under `tests/unit/`.
```bash
# Run all tests
pytest
# Verbose output
pytest -v
# Run a specific file
pytest tests/unit/test_validation.py
# Run tests matching a keyword
pytest -k "csv"
```
       Tests cover core modules (validation, parsing, calculations, comparison, cross-correlation) and selected UI components. The test suite was fixed and stabilized as part of PR #58 (Issue #57).



## Common Issues & Fixes
**Qt libraries missing (macOS/Linux)**
```
qt.qpa.plugin: Could not load the Qt platform plugin "xcb"
```
Install the required system Qt libraries. On Ubuntu/Debian:
```bash
sudo apt-get install libxcb-xinerama0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
```
On macOS with Homebrew:
```bash
brew install qt
```

**`conda env create` fails — package conflict**
Make sure you're using Conda ≥ 22.x and that no other environment is activated:
```bash
conda deactivate
conda env create -f environment.yml
```

**CSV fails validation unexpectedly**
- Confirm the file is a raw DLC CSV (scorer / bodyparts / coords header rows) or an enriched output CSV (`Spine_Head_x` column pattern).
- Check the in-app console (Help → Console) for the specific validation error message.
- Verify the `likelihood_threshold` in your config isn't too high — reducing it to `0.5` will include more frames.


**Graphs are blank after running calculations**
- Confirm the run completed (progress bar reached 100% and the Stop button returned to Run Calculation)
- Check the console for any calculation errors
- Make sure the selected config JSON includes the graph types you want under `calculations`


**Session won't load**
- Session files reference absolute paths: if you moved your CSV or JSON files after saving, update those paths or re-upload the files in Verify.

---

## Deployment
CV Zebrafish is a local desktop application — there is no server or cloud deployment. Distribution is done by sharing the repository and having the recipient set up the Conda environment.
**To share with a new lab member or collaborator:**
1. Clone the repository:
  ```bash
  git clone https://github.com/oss-slu/cv_zebrafish.git
  cd cv_zebrafish
  ```
2. Create the environment:
  ```bash
  conda env create -f environment.yml
  conda activate cvzebrafish
  ```
3. Launch the app:
  ```bash
  python app.py
  ```


**Sample data for a first run:**
The `data/samples/` directory contains example DLC CSVs and config JSONs you can use to walk through the full workflow without needing your own data files.

---

## Value Delivered
- **Time reduction** Analysis compressed from 2–3 hours down to ~5 minutes per dataset
- **Accessibility** Non-technical lab members can run full analyses independently —> no coding required


## Future Roadmap
- **1. Broader animal support** — Generalize naming conventions, defaults, and metrics so labs can reuse the pipeline for species beyond zebrafish.
- **2. Richer / custom analysis** — Add more built-in metrics and let users define extra analyses (custom columns, rules, or small plug-ins) via the config file (no source code changes needed).
- **3. Labeling in the pipeline** — Build a frame-by-frame video labeling step for any animal directly inside the app, replacing the separate DLC pre-processing step and consolidating the entire workflow in one place


## Known Gaps / Next Steps
- No dependency lockfile; add `requirements.txt`/`conda-lock` for fully reproducible installs
- No CI pipeline:  add GitHub Actions to run `pytest` automatically on push/PR
- No lint or type tooling: consider adding `ruff` (linting) and `mypy` (type checking)


---

## Development Process
The team follows an agile-style workflow:
- **GitHub** — Central repository for all code, history, and collaboration. All changes go through pull requests with at least one reviewer
- **Sprints** — Short planning cycles so the team ships small increments and adjusts often based on client and user feedback
- **Work splitting** — Each feature is owned by one developer and reviewed by another, keeping accountability clear and code quality high


## Contributors
- Madhuritha Alle **Tech Lead** 
- Sahana Gujja - Developer
- Kwabena Gyimah - Developer
- Bruce Miller - Developer