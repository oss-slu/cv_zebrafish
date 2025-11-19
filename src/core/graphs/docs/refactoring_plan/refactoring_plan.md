# Graph Refactor Implementation Guide

Goal: break the monolithic graph generation in `src/core/graphs/outputDisplay.py` into composable,
testable modules that pull all data from `src/core/graphs/data_loader.py` (using
`data/samples/csv/calculated_data_enriched.csv` as the baseline input) and keep parity with the
current outputs and configuration flags.

## Required Inputs and Contracts
- CSV: `data/samples/csv/calculated_data_enriched.csv` (use `GraphDataLoader(csv_path=..., config_path=...)`).
- Config: same JSON structure currently passed into `runAllOutputs` (keys like
  `shown_outputs`, `graph_cutoffs`, `spine_plot_settings`, `open_plots`, and `bulk_input` are required).
- Loader API to rely on:
  - `loader.get_time_ranges()` for legacy `[start, end]` pairs (or `loader.get_bouts()` for richer objects).
  - `loader.get_input_values()` for legacy nested dicts (spine, fins, tail, head/tp).
  - `loader.get_calculated_values()` for derived series (`headX`, `headY`, `headYaw`, `tailDistances`,
    `tailAngles`, `headPixelsX/Y`, `tailPixelsX/Y`, etc.).
  - `loader.get_config()` for plotting flags and file paths.
  - `loader.get_dataframe()` only when a full DataFrame slice is truly needed.

## Target Architecture
- `loader` stage: a slim adapter that calls `GraphDataLoader` and returns a dataclass/typed bundle the
  plotting layer consumes (avoid passing raw DataFrames outside this boundary).
- `metrics` utilities: pure functions for peak detection, bout slicing, travel distance/speed, and
  frequency calculations (currently embedded in `outputDisplay.py`).
- `plots` package: one module per plot family (spines; fin/tail timelines; head orientation; movement
  trace; movement heatmap; dot/scatter comparison). Each module should expose a `render(...)` function
  that returns both a Plotly Figure and metadata (selected frames, peaks, warnings).
- `io` utilities: output folder creation, logging, and figure/image export (replacement for
  `getOutputFile`, `printToOutput`, `saveResultstoExcelFile`).
- `runner` or `pipeline` module: orchestrates calling the individual plot modules based on config flags
  (replacement for `runAllOutputs`), and collects per-bout results in a structured payload.
- Legacy reference only: keep `output_adapter.py` and `outputDisplay.py` in a reference/legacy folder;
  the new implementation must be fully independent (no imports/calls into those files).

## Module Structure (proposed)
- `graphs/loader_bundle.py`: wrapper that pulls once from `GraphDataLoader` and returns a typed bundle
  (time ranges, inputValues, calculatedValues, config).
- `graphs/io.py`: output folder creation, logging, figure/image export (replaces `getOutputFile`,
  `printToOutput`, `saveResultstoExcelFile`).
- `graphs/metrics.py`: pure helpers (`getPeaks`, `getFrequencyAndPeakNum`, `getTimeRanges`,
  `rotateAroundOrigin`, `flipAcrossOriginX`, `checkConfidence`, distance/speed).
- `graphs/plots/spines.py`, `plots/fin_tail.py`, `plots/head.py`, `plots/movement.py`,
  `plots/heatmap.py`, `plots/dotplot.py`.
- `graphs/runner.py`: orchestrator that reads config flags, calls plot modules, aggregates results.

### Package Skeleton
```
src/
└── core/
    └── graphs/
        ├── __init__.py
        ├── loader_bundle.py
        ├── io.py
        ├── metrics.py
        ├── runner.py
        └── plots/
            ├── __init__.py
            ├── spines.py
            ├── fin_tail.py
            ├── head.py
            ├── movement.py
            ├── heatmap.py
            └── dotplot.py
```

## Functions to Split Out of `outputDisplay.py` (checklist-ready)
- [ ] File/output management (`io.py`)
  - [ ] Port `getOutputFile`, `printToOutput`, `saveResultstoExcelFile`.
  - [ ] Keep signatures compatible with current `results/Results N` rotation.
  - [ ] Ensure logging/exports accept path inputs from runner (no globals).
- [ ] Metrics helpers (`metrics.py`)
  - [ ] Move `getPeaks`, `getFrequencyAndPeakNum`, `getTimeRanges`, `rotateAroundOrigin`,
        `flipAcrossOriginX`, `checkConfidence`, `printTotalDistance`, `printTotalSpeed`.
  - [ ] Refactor to pure functions on numpy arrays; no global state.
  - [ ] Write unit tests for peak detection and distance/speed.
- [ ] `plotSpines` → `plots/spines.py`
  - [ ] Inputs: `inputValues["spine"]`, `calculatedValues["leftFinAngles"]`, `calculatedValues["rightFinAngles"]`,
        `timeRanges`, config sections `spine_plot_settings`, `graph_cutoffs`, `open_plots`.
  - [ ] Preserve selection toggles (`select_by_bout`, `select_by_parallel_fins`, `select_by_peaks`),
        confidence thresholds (`min_accepted_confidence`, `accepted_broken_points`,
        `min_confidence_replace_from_surrounding_points`), gradient flags (`draw_with_gradient`,
        `mult_spine_gradient`), `spines_per_bout`, and synchronized-peak filtering.
  - [ ] Return: Plotly figure(s), selected frame indices, gaps/missing endpoints, warnings.
- [ ] `plotFinAndTailCombined` → `plots/fin_tail.py`
  - [ ] Inputs: `calculatedValues["leftFinAngles"]`, `["rightFinAngles"]`, `["tailDistances"]`,
        `["tailAngles"]`, `["headYaw"]`; `timeRanges`; config `graph_cutoffs` (e.g., `left_fin_angle`,
        `right_fin_angle`, `tail_angle`), display toggles (`combinePlots`, legends), `open_plots`.
  - [ ] Behavior: aligned time-series overlays, peak detection via cutoffs, bout highlighting, optional
        combined subplot.
  - [ ] Return: figure(s), peak indices, per-bout summaries.
- [ ] `plotHead` → `plots/head.py`
  - [ ] Inputs: `calculatedValues["headYaw"]`, fin angles, `timeRanges`; config (head plot settings under
        `shown_outputs` or dedicated section) and `graph_cutoffs`.
  - [ ] Behavior: head yaw vs time with bout shading; overlay fin peaks/angles to show phase offsets.
  - [ ] Return: figure(s), annotations/peaks, per-bout stats.
- [ ] `plotMovement` → `plots/movement.py`
  - [ ] Inputs: `calculatedValues["headPixelsX"]`, `["headPixelsY"]`, `timeRanges`; video path
        `config["file_inputs"]["video"]`; optional scale factor (e.g., `config["scale_factor"]`).
  - [ ] Behavior: 2D trajectory trace, optional background frame, bout segmentation. Use only loader arrays.
  - [ ] Return: figure(s), segment metadata.
- [ ] `plotMovementHeatmap` → `plots/heatmap.py`
  - [ ] Inputs: `calculatedValues["headPixelsX"]`, `["headPixelsY"]`, `["tailPixelsX"]`, `["tailPixelsY"]`,
        `timeRanges`; binning/smoothing from config if present.
  - [ ] Behavior: density heatmaps per bout or global; return bin metadata and figure.
- [ ] `showDotPlot` → `plots/dotplot.py`
  - [ ] Inputs: two numeric series (caller-supplied), labels/units, `openPlots` flag.
  - [ ] Behavior: reusable scatter with optional annotations; supports save/interactive modes.
- [ ] Interactive/manual tools (`manual_tools.py`)
  - [ ] Move `getPeaksManual`; keep optional and isolated so headless runs skip it cleanly.
  - [ ] Signature: accept a series (e.g., `calculatedValues["tailDistances"]`) and return selected indices.

## Implementation Tasks
1. **Create module skeletons** under `src/core/graphs/` (or `src/core/graphs/plots/`) that mirror the
   categories above; move the corresponding logic and trim each function to a single concern.
2. **Define a shared data bundle** (e.g., a dataclass) that encapsulates the outputs of
   `GraphDataLoader` needed for plotting; forbid direct CSV column access in the plotting layer.
3. **Normalize configuration access**: centralize `get_config_flag`-style helpers so missing keys
   fall back to safe defaults and warnings are emitted once.
4. **Add persistence hooks**: shared helpers for saving Plotly HTML/PNG, writing log.txt, and exporting
   the consolidated results table.
5. **Rebuild the orchestrator**: new `run_all_graphs()` calls each plot module based on config flags,
   aggregates returned metadata (peaks selected, frames used, warnings), and mirrors the old
   `resultsList` shape for compatibility.
6. **Wire up the sample data path**: default the runner to
   `data/samples/csv/calculated_data_enriched.csv` (with the chosen config) for quick manual testing.
7. **Tests**: add unit tests for metrics utilities (peak detection, travel distance/speed), smoke tests
   that each plot module runs on a small slice of the sample CSV, and an integration test that the
   orchestrator completes without writing outside `results/`.

## Acceptance Criteria
- All legacy plot types generated by `runAllOutputs` have modular counterparts producing equivalent
  visuals/metadata when fed the same loader outputs.
- Plot modules consume only the structured loader data (no ad-hoc column lookups).
- Non-interactive runs succeed headless (manual peak tool optional), and outputs land in a predictable
  folder created by the new io utilities.
- Documentation kept in this file is updated as modules land, with any deviations from legacy behavior
  called out.
