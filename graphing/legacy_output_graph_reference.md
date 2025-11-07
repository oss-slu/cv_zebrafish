# Legacy Output Graph Reference

## Purpose
`codes/bruce/codes/utils/outputDisplay.py` is the visualization hub of the Bruce legacy pipeline. It consumes the metrics produced by `mainCalculation.py`, emits numeric summaries, and generates interactive Plotly figures plus PNG snapshots. This note inventories every graph generated there and ties each one to the data that drives it so the new implementation in `cv_zebrafish` can reproduce the same behaviors.

## Data interface and mapping
The new stack currently exports `calculations/tests/calculated_data.csv`, where each row corresponds to a frame's derived metrics and some aggregate arrays are stored in the first row. The table below links the legacy variable names used inside `outputDisplay.py` to the CSV columns (or highlights gaps that must be filled).

| Legacy variable | Description | `calculations/tests/calculated_data.csv` |
| --- | --- | --- |
| `Time` / frame index | Loop index used across all plots. | `Time` column (integer frame number). |
| `leftFinAngles` | Left fin polar angle in degrees used for thresholds and peaks. | `LF_Angle`. |
| `rightFinAngles` | Right fin polar angle in degrees. | `RF_Angle`. |
| `tailDistances` | Tail tip displacement relative to capture point (meters). | `Tail_Distance` (meters) and `Tail_Distance_Pixels` (already scaled). |
| `tailDistances` (signed angles) | Per-link tail angles (`TailAngle_0` … `TailAngle_11`). | `TailAngle_0`-`TailAngle_11`. |
| `headYaw` | Absolute yaw of the head in degrees. | `HeadYaw`. |
| `headX`, `headY` | Head position in world units (meters) for distance/speed. | `HeadX`, `HeadY`. |
| `headPixelsX`, `headPixelsY` | Pixel-space head coordinates for movement/heatmap overlays. | **Not yet exported.** Derive by storing raw pixel coords or by re-scaling `HeadX/HeadY` with `pixel_scale_factor`. |
| `tailPixelsX`, `tailPixelsY` | Pixel-space tail coordinates used to size the heatmap crop. | **Not yet exported** (only distances exist). |
| `spine` | List of per-frame body segments (each point has `x`, `y`, `conf`). | **Not yet exported.** Needs to be serialized (e.g., columns per point or nested JSON). |
| `leftFinPeaks`, `rightFinPeaks` | Frame indices where each fin exceeds its cutoff. | `leftFinPeaks` and `rightFinPeaks` columns already exist but currently appear empty except on row 0; they should hold serialized index lists. |
| `timeRanges` | Swim-bout ranges selected for every plot. | `timeRangeStart_*` / `timeRangeEnd_*` columns (row 0 stores all ranges). |
| `headYaw` per bout | `curBoutHeadYaw` is saved for convenience. | `curBoutHeadYaw`. |
| `Tail_Side`, `Furthest_Tail_Point` | Frame-level categorical descriptors used downstream. | `Tail_Side`, `Furthest_Tail_Point`. |
| `videoFile` & `pixel_scale_factor` | Used by movement plots to fetch imagery and rescale. | From runtime config (`config["file_inputs"]["video"]`, `config["video_parameters"]["pixel_scale_factor"]`); not stored in CSV. |

### Time-range encoding
`outputDisplay.py` expects `timeRanges` shaped as `[[start_idx, end_idx], …]`. The legacy code stores those indices in the first row of the CSV using columns named `timeRangeStart_<n>` and `timeRangeEnd_<n>`. To reuse them you can read row 0, pair each `start` / `end`, and stop once you encounter blanks.

## Graph catalog

### 1. Spine snapshots (`plotSpines`)
**Goal.** Visualize the fish posture at representative frames so analysts can verify skeletal tracking quality and see how fins behave at specific events.

**Inputs.**
- `spine`: for each frame, an ordered list of skeleton points with `x`, `y`, and confidence. Low-confidence points are gap-filled along each polyline.
- `leftFinAngles`, `rightFinAngles`: drive both confidence filtering and the optional “select by peak/parallel” modes.
- `timeRanges`: restricts frame selection to bouts.
- `spine_plot_settings`: controls selection strategy (`select_by_bout`, `select_by_parallel_fins`, `select_by_peaks`), gradients, per-bout splitting, offsets, etc.
- `graph_cutoffs`: provides fin-angle thresholds when peaks are used.

**Behavior.**
- Frames can be sampled evenly across each bout (`spines_per_bout`), taken where fins move in parallel (angles ≈ 90°), or aligned to fin peaks (with optional suppression when both fins peak together).
- Every spine is translated so the head sits at the origin, rotated to face right, optionally mirrored, and offset horizontally so multiple frames can be stacked.
- The function records metadata about gaps/missing endpoints, prints the selected frame numbers, and writes interactive Plotly figures. When `split_plots_by_bout` is enabled it builds a tabbed HTML gallery (`spine_plots_tabbed.html`) plus PNG snapshots per bout; otherwise everything lands in `spine_plot_plotly.html` and `{imageTag}Spines.png`.

**Meaning.** Dense, color-coded polylines show bending along the spine during a swim bout. Large gaps or missing endpoints highlight where pose estimation failed. Comparing overlays reveals how posture evolves during a bout or near synchronized fin activity.

**CSV translation.**
- Use `LF_Angle` / `RF_Angle` arrays for fin thresholds.
- Extract bout windows from the `timeRangeStart_*` columns.
- **Spine coordinates are not present** in `calculations/tests/calculated_data.csv`; to rebuild this graph you must persist each point's `x`, `y`, and `conf` per frame (e.g., `spine_point_0_x`, etc.) or load them from an auxiliary artifact.

### 2. Fin + tail timeline (`plotFinAndTailCombined`)
**Goal.** Plot synchronized time-series to show how left/right fin beating, tail displacement, and head yaw align during bouts.

**Inputs.**
- `leftFinAngles`, `rightFinAngles`, `tailDistances`, `headYaw`.
- `timeRanges` to mask “None” separators between bouts.
- `angle_and_distance_plot_settings` toggles for which traces are shown.

**Behavior.**
- Builds a two-row Plotly subplot where row 1 contains both fin angles, and row 2 shows tail distance (primary y-axis) plus head yaw (secondary axis) if enabled.
- Inserts `None` separators between bouts so traces break cleanly.
- Saves `FinAndTailCombined_Subplots.html` and `.png`.

**Meaning.** Lets analysts correlate fin strokes with tail propulsion and head steering. Spikes above configured cutoffs indicate individual beats; phase offsets between fins or between fins and tail become visually apparent.

**CSV translation.**
- `LF_Angle`, `RF_Angle`, `Tail_Distance`, and `HeadYaw` columns already match the required arrays. Read them per frame, filter by `timeRanges`, and honor any new sampling cadence.

### 3. Movement track overlay (`plotMovement`)
**Goal.** Overlay the head trajectory on a representative video frame to confirm spatial calibration.

**Inputs.**
- `headPixelsX`, `headPixelsY`: pixel coordinates per frame.
- `timeRanges`: only the first range is used.
- `videoFile`: read via OpenCV to fetch the frame that anchors the plot.
- `pixel_scale_factor`: manual tweak to align CSV coordinates with raw footage.
- `open_plots`: decides whether to open the figure.

**Behavior.**
- Loads the video frame at the start of the first time range, converts it to RGB, and adds it as a background image in Plotly.
- Scales the head coordinates, flips the y-axis so the path draws correctly, and plots a red spline line following the swim path.
- Writes `Zebrafish_Movement_Plotly.html` and `.png`.

**Meaning.** Validates that the coordinate system from DeepLabCut aligns with the video and highlights gross movement direction or arena boundaries.

**CSV translation.**
- Today the CSV only stores `HeadX`/`HeadY` in meters. To reproduce the overlay you either need to export `headPixelsX/Y` directly or convert the metric coordinates back to pixels using the same `pixel_scale_factor` and any origin offsets you applied during calculation.
- Ensure the new calculation exports or rediscover the underlying `videoFile` path so this function can pull a frame.

### 4. Movement heatmap (`plotMovementHeatmap`)
**Goal.** Produce an intensity map showing where the head (and implicitly the fish body) spends time within its local neighborhood.

**Inputs.**
- `headPixelsX`, `headPixelsY`, `tailPixelsX`, `tailPixelsY` to determine crop bounds and positions.
- `timeRanges`: iterated in sequence, pulling every relevant frame.
- `videoFile`: used to read all frames inside the selected bouts.

**Behavior.**
- Determines the maximum head–tail distance to size a square crop with a safety buffer.
- Reads all frames across the bouts, converts them to grayscale, crops around the head for each frame, and accumulates pixel intensities into a floating-point heatmap.
- Normalizes and gamma-corrects the heatmap before displaying via `px.imshow`, then writes `heatmap_plotly.html` and `Heatmap_Plotly.png`.

**Meaning.** Highlights spatial occupancy—bright regions correspond to positions/orientations the fish visited often during the chosen bouts.

**CSV translation.**
- Requires full pixel-space trajectories for head and tail; `Tail_Distance_Pixels` alone is insufficient because it contains only magnitudes. Extending `calculated_data.csv` with `HeadPX`, `HeadPY`, `TailPX`, `TailPY` (or storing a separate JSON) is necessary.
- Access to the raw video file remains a requirement.

### 5. Head orientation tabs (`plotHead`)
**Goal.** Visualize head yaw at successive fin peaks to inspect turning behavior inside each bout.

**Inputs.**
- `headYaw` array.
- `leftFinAngles` and `rightFinAngles` to detect fin peaks (respecting `head_plot_settings` such as `fin_peaks_for_right_fin`, `ignore_synchronized_fin_peaks`, and `sync_fin_peaks_range`).
- `timeRanges` to split into bouts when requested.
- `head_plot_settings`: includes a horizontal offset so multiple heads can be stacked.

**Behavior.**
- For each bout, records the first frame plus every frame where the selected fin exceeds its cutoff (after synchronization checks).
- Generates a parametric outline of a stylized head (defined by `headXPoints/headYPoints`), rotates it by the negative yaw, and offsets each successive outline to the right.
- When `split_plots_by_bout` is true it produces multiple Plotly figures embedded in a custom tabbed HTML shell (`head_plots_tabbed.html`) and PNG snapshots; otherwise everything is drawn onto a single figure.
- Also prints the frame numbers used so they can be audited.

**Meaning.** The stack of head outlines makes it easy to see if the fish consistently yaws toward one side during fin beats, or whether head motion is synchronized with fin usage.

**CSV translation.**
- Pull `HeadYaw`, `LF_Angle`, `RF_Angle`, and `timeRanges` directly from the CSV.
- Ensure the CSV’s `leftFinPeaks/rightFinPeaks` columns actually store the computed peak indices if you want to skip recomputation—otherwise recompute peaks from `LF_Angle`/`RF_Angle` just like the legacy routine.

## Implications for the new implementation
1. Persist spine point coordinates (x, y, confidence per segment) and pixel-space trajectories (head & tail) if you want to match the movement, heatmap, and spine plots exactly; they are currently absent from `calculations/tests/calculated_data.csv`.
2. Treat the `timeRangeStart_*` / `timeRangeEnd_*` columns in `calculations/tests/calculated_data.csv` as the canonical bout definitions; every graph in `outputDisplay.py` filters on those ranges, so reusing them ensures parity.
3. When building new Plotly components, reuse the same filenames (HTML + PNG) if you want drop-in compatibility with downstream automation that expects artifacts in the legacy `results/Results N` directories.
