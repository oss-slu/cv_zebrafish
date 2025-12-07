# plotMovementHeatmap implementation plan

## Goal and legacy parity
- Replace legacy `plotMovementHeatmap` in `src/core/graphs/reference/outputDisplay.py` with a modular `plots/heatmap.py` plotter invoked by the runner.
- Preserve legacy intent: use head/tail pixel coordinates, load video frames, crop around the head using the max head–tail distance (with buffer), accumulate grayscale intensity into a centered heatmap, apply gamma (legacy 0.5), save HTML/PNG, and optionally open the plot.
- Fix known gaps: legacy flag marked nonfunctional, duplicated `open_plots` arg, hardcoded head scaling (`* 1.825`), and missing bounds/length checks that can crash when video/arrays disagree.

## Inputs and dependencies
- GraphDataBundle: `time_ranges`, `calculated_values["headPixelsX"]`, `"headPixelsY"`, `"tailPixelsX"`, `"tailPixelsY"`, plus `config`; no direct DataFrame access.
- Config contracts:
  - `shown_outputs.show_heatmap` (gating)
  - `file_inputs.video` (required to render), `video_parameters.pixel_scale_factor` (preferred over hardcoded 1.825), `open_plots` (global interactive toggle)
  - Proposed `heatmap_settings` block with defaults: `buffer_mult` (>=1, default 2.0), `gamma` (default 0.5), `smoothing_kernel` (odd int for optional blur), `normalization_epsilon`, `scale_override` (fallback to preserve legacy), `crop_padding` (extra pixels around radius), `open_plot` (override global).
- Dependencies: numpy, cv2 (VideoCapture), plotly (express/io). Avoid new heavy deps; if smoothing needed, use cv2.GaussianBlur on the accumulated array.

## Processing flow
1. Guards: verify required arrays exist and lengths cover all `time_ranges`; if video path missing/unreadable, return metadata with a warning and skip figure save.
2. Crop window: iterate ranges to find the max head–tail distance; set `radius = max_dist * buffer_mult` (min 1 px) and heatmap size `2*radius + padding`.
3. Frame access: open `VideoCapture`; seek to each bout start, read sequential frames; if a read fails, record a warning and continue.
4. Accumulation: for each frame index in bouts, map head pixel to center (using `pixel_scale_factor` or legacy override); crop grayscale frame around the center within bounds; accumulate into a float heatmap, aligning the crop inside the preallocated array even when clipped at edges.
5. Post-processing: normalize by max with epsilon guard, optional blur, apply gamma; build a Plotly heatmap (`px.imshow`) with fixed orientation/colorbar labels.
6. Saving/opening: when ctx provided, write HTML/PNG under `movement_heatmap` base; honor `open_plots` or `heatmap_settings.open_plot`; return dataclass metadata (figure, heatmap shape, max intensity, radius/bbox, frames_used, warnings, output paths).

## API shape
- New dataclass `MovementHeatmapResult` capturing the figure and metadata.
- Export `render_movement_heatmap(bundle: GraphDataBundle, ctx: Optional[OutputContext]) -> MovementHeatmapResult`.
- Keep helper functions (`compute_radius`, `accumulate_heatmap`, `load_frames`) private/pure for unit testing; no reliance on global state.

## Testing plan
- Unit tests for helpers using synthetic frames/coords to assert radius sizing, center alignment, normalization, and gamma application (no cv2 dependency by injecting frames).
- Negative tests for missing video path and mismatched array lengths to ensure graceful warnings instead of crashes.
- Integration smoke: run `render_movement_heatmap` against a tiny synthetic video or injected frames with the sample config to confirm HTML/PNG write and metadata population even when skipping plot open.

## Integration steps
- Wire the plotter into `runner.run_all_graphs` once implemented (e.g., include in the plotter list when `show_heatmap` is enabled).
- Document any behavior changes (e.g., `pixel_scale_factor` replacing hardcoded 1.825) back in `refactoring_plan.md` when the implementation lands.
