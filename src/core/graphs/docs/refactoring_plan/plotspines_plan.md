# plotSpines implementation plan

## Goal and legacy parity
- Replace legacy `plotSpines` in `src/core/graphs/reference/outputDisplay.py` with a modular plotter under `plots/spines.py`.
- Preserve legacy intent: choose spine frames per bout using selection modes (by bout start/end, parallel fins, fin peaks), apply confidence filtering/repair, draw stylized spine gradients, and save per-bout images/HTML without relying on globals.
- Address legacy gaps: remove global state, handle missing/conflicting config keys gracefully, avoid silent failures when confidence data/peaks are missing, and support both split-by-bout and combined outputs.

## Inputs and config contracts
- GraphDataBundle fields: `time_ranges`, `input_values["spine"]` (list of frame -> list of dicts with x/y/conf), `calculated_values["leftFinAngles"]`, `"rightFinAngles"]`, optional peak arrays, and `config`.
- Config keys:
  - Gate: `shown_outputs.show_spines`.
  - Settings: `spine_plot_settings` including `select_by_bout`, `select_by_parallel_fins`, `select_by_peaks`, `spines_per_bout`, `parallel_error_range`, `fin_peaks_for_right_fin`, `ignore_synchronized_fin_peaks`, `sync_fin_peaks_range`, `min_accepted_confidence`, `accepted_broken_points`, `min_confidence_replace_from_surrounding_points`, `draw_with_gradient`, `mult_spine_gradient`, `plot_draw_offset`, `split_plots_by_bout`.
  - Cutoffs: `graph_cutoffs.left_fin_angle`, `right_fin_angle` (for peak detection if peak arrays aren’t provided).
  - Interaction: `open_plots` (global) and optional per-plot override.
- No video dependency; all geometry comes from loader arrays.

## Processing flow
1. Guards: ensure required series (`spine`, fin angles) and time_ranges exist; return warnings-only metadata if missing.
2. Frame selection per mode:
   - By bout: pick `spines_per_bout` evenly spaced frames within each time range.
   - By parallel fins: find frames where left/right fin angles within `parallel_error_range`.
   - By peaks: detect peaks on configured fin side; optionally drop synchronized peaks within `sync_fin_peaks_range` of the opposite fin if `ignore_synchronized_fin_peaks`; fall back gracefully if `graph_cutoffs` missing by emitting a warning and skipping peak mode.
   - Combine modes per config: union of frames, de-duplicate, sort, then enforce a per-bout budget (`spines_per_bout` or a mode-specific cap) with deterministic priority (peaks > parallel > even spacing) and consistent tie-breaking (earlier frame wins).
3. Confidence handling: for each selected frame, evaluate `min_accepted_confidence` / `accepted_broken_points`; optionally repair low-confidence points using surrounding points when `min_confidence_replace_from_surrounding_points` is set (linear interpolation between nearest valid neighbors; endpoints use nearest valid point; cap max consecutive low-confidence run to avoid over-smoothing). Mark frames that still fail confidence as warnings/skipped and record which points were repaired.
4. Drawing: build Plotly figures for each bout (if `split_plots_by_bout`) or a combined figure with subplots per bout. Draw spine as connected lines; apply gradient coloring when enabled (`mult_spine_gradient` multiplier). Optionally offset successive spines horizontally (`plot_draw_offset`) to avoid overlap; warn if offset still causes overlap.
5. Metadata: collect selected frame indices per bout, confidence warnings, missing endpoints/gaps, repaired point counts, and peak/parallel selection details for debugging.
6. Output: save HTML/PNG per bout (or a combined file) via `OutputContext`; filenames follow `spines_bout-{i}.{ext}` or `spines_combined.{ext}`; respect `open_plot` override falling back to global `open_plots`; return dataclass result with figures, selections, warnings, and file paths.

## API shape
- Dataclass `SpinePlotResult` with fields: `figures` (list aligned to bouts when split, singleton list when combined), `mode` ("by_bout"/"combined"), `frames_by_bout`, `warnings`, `output_paths` (one path per figure, same order as `figures`).
- Export `render_spines(bundle: GraphDataBundle, ctx: Optional[OutputContext]) -> SpinePlotResult`.
- Helpers: `_select_frames_by_bout`, `_select_frames_by_parallel`, `_select_frames_by_peaks`, `_filter_confidence`, `_build_spine_figure`; keep IO only in the top-level render.

## Testing plan
- Unit tests for frame selection helpers (even spacing, parallel tolerance, peak detection with/without sync filtering), including enforcement of per-bout frame budgets and priority ordering across combined modes.
- Confidence filter tests using synthetic spine points with varying `conf` values, covering interpolation edge cases (endpoints, long low-confidence runs).
- Smoke test rendering a small synthetic spine set with split vs combined modes to ensure figures are produced without external IO when ctx=None; include gradient + offset overlap cases and multi-bout sync-peak filtering scenarios.

## Current limitations / gaps
- GUI viewer only shows multiple bout spine plots if the payload includes multiple time ranges; ensure config supplies multiple `time_ranges` or the calculation DataFrame carries `timeRangeStart_*`/`timeRangeEnd_*` columns for every bout.
- Graph viewer rebuilds bundles from the calculation output and parsed points; if parsed points are missing from the payload, spines are skipped entirely.
- Runner wiring includes spines, but head/tail/other plots still rely on legacy pathways; parity/QA with legacy outputDisplay is still pending.
- Remaining failing tests in `test_data_loader.py` (`BoutRange.start` missing, missing `LeftFin_Peaks` column) are unrelated to spine rendering but block full suite passes.

## Integration steps
- Add plotter wiring in the runner when `shown_outputs.show_spines` is true.
- Optionally surface a GUI hook similar to the dot plot/fin-tail viewer once the plotter is stable.
- Document any deviations from legacy behavior (e.g., clearer warnings on missing confidence or peaks) back into the refactoring guide.
