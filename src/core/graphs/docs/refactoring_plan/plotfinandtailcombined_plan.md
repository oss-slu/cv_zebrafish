# plotFinAndTailCombined implementation plan

## Goal and legacy parity
- Replace legacy `plotFinAndTailCombined` in `src/core/graphs/reference/outputDisplay.py` with a modular plotter under `plots/fin_tail.py`.
- Preserve legacy behavior: optionally combine fin angles + head yaw on primary y-axis and tail distance on secondary y-axis, or render a 2-row subplot version; honor per-series toggles and `combine_plots` setting.
- Fix gaps: make cutoffs/peaks configurable, avoid implicit globals, handle time range gaps cleanly, and skip output when inputs are missing instead of crashing.

## Inputs and config contracts
- GraphDataBundle fields: `time_ranges`, `calculated_values["leftFinAngles"]`, `"rightFinAngles"`, `"tailDistances"]`, `"tailAngles"]`, optional `"headYaw"]`, and `config`.
- Config keys:
  - Gate: `shown_outputs.show_angle_and_distance_plot`.
  - Settings: `angle_and_distance_plot_settings` with toggles `combine_plots`, `show_left_fin_angle`, `show_right_fin_angle`, `show_tail_distance`, `show_head_yaw`, line/legend options, colors (add defaults if missing).
  - Cutoffs: `graph_cutoffs.left_fin_angle`, `right_fin_angle`, `tail_angle` (used for peak detection/markers).
  - Interaction: `open_plots` (global) and optional per-plot override in settings.
- No video dependency.

## Processing flow
1. Guard: if the gate is false or required arrays are missing/length-mismatched with `time_ranges`, return metadata with warnings and no figures.
2. Slice series by bouts: build x,y with `None` separators per bout to mirror legacy continuity breaks; reuse a helper like `prepare_series`.
3. Peak detection (optional): use `metrics.getPeaks` or a light cutoff-based detector keyed off `graph_cutoffs`; return peak indices for metadata and optional marker traces.
4. Layout selection:
   - If `combine_plots`: make a single subplot with secondary y-axis; plot fin angles and head yaw on primary, tail distance on secondary.
   - Else: 2-row layout; row1 fin angles, row2 tail distance (primary) and head yaw (secondary) with shared x.
5. Styling: set axis titles, legends, hover labels, template `plotly_white`; support configurable colors/line styles and optional bout shading bands (using `time_ranges`).
6. Output: save HTML/PNG via `OutputContext` (filenames like `FinAndTailCombined` or `_Subplots`), respect `open_plots` or override; return metadata (figures, peaks, settings used, output paths, warnings).

## API shape
- Dataclass `FinTailPlotResult` with fields: `figures` (list of go.Figure), `mode` ("combined"|"split"), `peak_indices` per series, `time_ranges`, `output_paths`, `warnings`.
- Export `render_fin_tail(bundle: GraphDataBundle, ctx: Optional[OutputContext]) -> FinTailPlotResult` that reads config and dispatches to combined or split rendering; mirror dotplot.py structure (pure function, dataclass result, optional open_plot flag, sanitized filenames).
- Private helpers: `prepare_series`, `detect_peaks`, `build_combined_figure`, `build_split_figure`; keep side effects (saving/opening) only in the top-level render.

## Testing plan
- Unit tests for `prepare_series` (bouted slicing with None gaps), `detect_peaks` against synthetic data with cutoffs, and figure mode selection given `combine_plots` true/false.
- Validate that missing/short arrays yield warnings without exceptions.
- Smoke test: render with small synthetic arrays/time_ranges and confirm two saved files when ctx is provided and the correct number of traces per mode.

## Integration steps
- Add plotter wiring in the runner when `shown_outputs.show_angle_and_distance_plot` is true; pass bundle + ctx to `render_fin_tail`.
- Document any default choices (colors, line shapes, cutoff usage) back into `refactoring_plan.md` after implementation.
