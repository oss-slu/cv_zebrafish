# Zebrafish Regression Testing Guide & Checklist

## Purpose
This document provides a repeatable regression testing protocol to ensure that changes to application entry points, multi-species navigation (e.g. species selection landing page, mouse analysis placeholder), and shell architecture do not regress the primary Zebrafish analysis workflow or modify calculation outputs.

The Zebrafish computer vision and kinematic analysis pipeline is used for active laboratory research; silent deviations or regressions in numerical outputs, calculations, or visualization pipelines are not acceptable.

---

## Standard Test Dataset
Use the canonical sample data maintained in the repository:
- **DLC Tracking CSV**: `data/samples/csv/correct_format.csv` (or `data/sessions/Test2/uploads/correct_format.csv`)
  - Description: Standard DeepLabCut tracking output containing 5,351 frames of tracked body parts (head, clp1, clp2, fins, tail points).
- **Configuration JSON**: `data/samples/jsons/BaseConfig.json` (or `data/samples/jsons/config_autogen.json`)
  - Description: Standard camera calibration parameters, body part mappings, bout detection thresholds, and cutoff buffers.
- **Reference Output Benchmark**:
  - `data/samples/csv/calculated_data_enriched.csv`
  - Automated calculation script: `python src/core/calculations/run_calculation_to_csv.py --csv data/samples/csv/correct_format.csv --config data/samples/jsons/BaseConfig.json --output results/benchmark_test.csv`

---

## Happy Path Workflow: Step-by-Step

### Step 1: Species Selection (Landing Page)
1. Launch the application:
   ```bash
   python app.py
   ```
2. **Verification**:
   - The application opens displaying the **Species Selection** landing panel (`SpeciesSelectPanel`).
   - The species dropdown defaults to **Zebrafish**.
   - The "Continue" button is enabled.
3. Click **Continue** with "Zebrafish" selected.
4. **Verification**:
   - Workspace transitions to the Zebrafish **Empty Session Panel** (`EmptySessionPanel`).
   - The large fish logo and "+ Load Session" text are visible.
   - Sidebar tools remain disabled/locked appropriately prior to loading a session.

*(Optional Alternative Path)*:
- Select **Mouse** from the dropdown and click **Continue**.
- Verify that the Mouse analysis placeholder page is displayed with the mouse icon and placeholder steps.
- Click the **← Back** button; verify it returns to the Species Selection landing page.

---

### Step 2: Session Creation / Selection
1. Click the main landing screen area or choose **File → Session Select…** from the top menu bar.
2. The Session Select dialog appears:
   - Click **+ Create New** and name the session (e.g., `Regression_Test`), or select an existing session (e.g. `Test2`).
   - Alternatively click **Upload New** to load a session configuration JSON.
3. Click **Open** (or double-click the session row).
4. **Verification**:
   - The window title updates to `CV Zebrafish — <Session Name>`.
   - The workspace advances to the **Verify Panel** (`VerifyPanel`).
   - The sidebar navigation updates, enabling the Data / Verify tab.

---

### Step 3: Verify Panel (Data & Configuration Input)
1. In the **Verify Panel**:
   - Click **Select CSV File** and choose `data/samples/csv/correct_format.csv`.
   - Verify that the CSV validation checks succeed with zero blocking errors.
   - Click **Select Config File** and choose `data/samples/jsons/BaseConfig.json` (or click **Generate Config** to auto-generate from the loaded CSV headers).
2. Click **Continue** (or click the **Select & Run** icon in the sidebar).
3. **Verification**:
   - Workspace advances to the **Select & Run Panel** (`SelectRunPanel`).

---

### Step 4: Select & Run Panel (Kinematic Calculations)
1. In the **Select & Run Panel**:
   - Verify that the CSV and Config files are properly associated in the session tree view.
   - Ensure the desired metric calculation checkboxes are selected.
   - Click **Run Calculations**.
2. **Verification**:
   - The progress bar advances progressively from 0% to 100% ("Ready").
   - No exceptions, unhandled crashes, or console error toasts occur.
   - Once complete, the application unlocks the **View Output** / Graph Viewer panel (automatically transitioning after a 1-second pause or via sidebar button).

---

### Step 5: View Output Panel (Visualization & Export)
1. In the **View Output Panel**:
   - Verify the graph selector dropdown contains all generated graphs:
     - *Fin Angles & Tail Distance*
     - *Head Orientation*
     - *Spines Bout*
     - *Tail Distance vs Left/Right Fin Angle*
   - Verify that interactive Plotly web views render properly and smoothly.
2. **Interactive Range & Zoom**:
   - Use the range selector or zoom box on the timeline.
   - Verify range statistics calculate correctly for the visible subset.
3. **Export Verification**:
   - Click **Export Data** / **Export Range**; save the output CSV to disk.
   - Verify that the exported CSV contains valid numeric rows and matching headers.
   - Verify figure export (HTML/PNG) generates complete files.

---

## Output Comparison & Numeric Diff Protocol

Whenever modifications are made to navigation, session handling, or core code:

1. **Run Headless Calculation Pipeline**:
   ```bash
   python src/core/calculations/run_calculation_to_csv.py \
     --csv data/samples/csv/correct_format.csv \
     --config data/samples/jsons/BaseConfig.json \
     --output results/test_output.csv
   ```
2. **Compare Against Baseline**:
   ```python
   import pandas as pd
   import numpy as np

   baseline = pd.read_csv("results/baseline_output.csv")
   current = pd.read_csv("results/test_output.csv")

   # Check shape and column alignment
   assert baseline.shape == current.shape, f"Shape mismatch: {baseline.shape} vs {current.shape}"
   assert list(baseline.columns) == list(current.columns), "Column names mismatch"

   # Numeric diff
   numeric_cols = baseline.select_dtypes(include=[np.number]).columns
   diffs = {}
   for col in numeric_cols:
       max_diff = np.max(np.abs(baseline[col].fillna(0) - current[col].fillna(0)))
       if max_diff > 1e-6:
           diffs[col] = max_diff

   assert not diffs, f"Numeric differences detected: {diffs}"
   print("PASSED: Numeric outputs are identical within tolerance (1e-6).")
   ```
3. **Visual Inspection**:
   - Open generated Plotly HTML files in a browser or compare rendered PNG snapshots to verify traces, axis labels, peak markers, and bout shading match pixel/layout expectations.

---

## Automated Regression Suite

Automated navigation and species-selection routing tests are located in:
- `tests/unit/ui/test_species_select_panel.py`:
  - `test_defaults_to_zebrafish`
  - `test_continue_emits_zebrafish_by_default`
  - `test_selecting_mouse_emits_mouse_on_continue`
  - `test_workspace_starts_on_species_panel`
  - `test_shell_navigation_landing_to_zebrafish_workflow`
  - `test_shell_navigation_landing_to_mouse_and_back`
- `tests/unit/ui/test_mouse_analysis_page.py`:
  - Tests step navigation, back signal, and placeholder layout.

To run the entire automated test suite:
```bash
pytest
```
Expected result: **100% passing tests** (194+ passed).

---

## Manual Test Checklist

Before merging any PR affecting navigation or core shell widgets, execute this checklist:

- [ ] **Species Landing Page**
  - [ ] App launches into Species Selection screen.
  - [ ] "Zebrafish" is selected by default; "Continue" button is enabled.
  - [ ] Clicking "Continue" directly opens the Zebrafish Empty Session screen (`EmptySessionPanel`).
  - [ ] Switching dropdown to "Mouse" and clicking "Continue" opens Mouse analysis page.
  - [ ] Clicking "← Back" on Mouse page returns to Species Selection without error.
- [ ] **Session & Data Loading**
  - [ ] Session can be created or loaded via File menu or clicking the empty screen fish logo.
  - [ ] Verify panel loads `data/samples/csv/correct_format.csv` with 0 blocking errors.
  - [ ] Config file `data/samples/jsons/BaseConfig.json` loads and validates successfully.
- [ ] **Calculation Execution**
  - [ ] Select & Run panel initiates calculation without unhandled exceptions.
  - [ ] Progress bar reaches 100% ("Ready").
  - [ ] Transitions to View Output panel automatically or via unlocked sidebar button.
- [ ] **Graph Display & Export**
  - [ ] All expected graphs populate the dropdown and render interactive traces.
  - [ ] Zooming and range stats function without error toasts.
  - [ ] CSV/figure export saves non-empty files with correct numerical values.
- [ ] **Automated CI**
  - [ ] `pytest` passes 100% locally.
  - [ ] GitHub Actions CI workflow (`Tests`) is green.
