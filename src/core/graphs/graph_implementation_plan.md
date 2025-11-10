# Legacy Output Graph Reference

## Purpose
`codes/bruce/codes/utils/outputDisplay.py` is the visualization hub of the Bruce legacy pipeline. It consumes the metrics produced by `mainCalculation.py`, emits numeric summaries, and generates interactive Plotly figures plus PNG snapshots. This note inventories every graph generated there and ties each one to the data that drives it so the new implementation in `cv_zebrafish` can reproduce the same behaviors.

## Data interface and mapping
The new stack exports an enriched CSV file (e.g., `correct_format_results_enriched.csv`), where each row corresponds to a frame's derived metrics. The table below links the legacy variable names used inside `outputDisplay.py` to the new CSV columns (or highlights gaps that must be filled).

| Legacy variable | Description | `correct_format_results_enriched.csv` |
| --- | --- | --- |
| `Time` / frame index | Loop index used across all plots. | `Time` column (integer frame number). |
| `leftFinAngles` | Left fin polar angle in degrees used for thresholds and peaks. | `LF_Angle`. |
| `rightFinAngles` | Right fin polar angle in degrees. | `RF_Angle`. |
| `L_Eye_Angle` | Left eye angle in degrees. | `L_Eye_Angle`. |
| `R_Eye_Angle` | Right eye angle in degrees. | `R_Eye_Angle`. |
| `tailDistances` | Tail tip displacement relative to capture point (meters). | `Tail_Distance` (meters) and `Tail_Distance_Pixels` (already scaled). |
| `tailDistances` (signed angles) | Per-link tail angles (`TailAngle_0` … `TailAngle_11`). | `TailAngle_0`-`TailAngle_11`. |
| `headYaw` | Absolute yaw of the head in degrees. | `HeadYaw`. |
| `headX`, `headY` | Head position in world units (meters) for distance/speed. | `HeadX`, `HeadY`. |
| `headPixelsX`, `headPixelsY` | Pixel-space head coordinates for movement/heatmap overlays. | `HeadPX`, `HeadPY` (per-frame pixels exported alongside the metric columns). |
| `tailPixelsX`, `tailPixelsY` | Pixel-space tail coordinates used to size the heatmap crop. | `TailPX`, `TailPY`. |
| `spine` | List of per-frame body segments (each point has `x`, `y`, `conf`). | `spine_points_json` plus the flattened columns (`Spine_Head_x`, ..., `Tail_ET_conf`). |
| `timeRanges` | Swim-bout ranges selected for every plot. | `timeRangeStart_<n>` / `timeRangeEnd_<n>` (populated on the first row and repeated for convenience). |
| `headYaw` per bout | `curBoutHeadYaw` is saved for convenience. | `curBoutHeadYaw`. |
| `Tail_Side`, `Furthest_Tail_Point` | Frame-level categorical descriptors used downstream. | `Tail_Side`, `Furthest_Tail_Point`. |
| `videoFile` & `pixel_scale_factor` | Used by movement plots to fetch imagery and rescale. | `videoFile`, `pixel_scale_factor`. |

### Bout and Time-Range Encoding
The enriched CSV still uses the legacy header-style encoding for swim bouts: `timeRangeStart_<n>` and `timeRangeEnd_<n>` columns live on the first row (and are repeated for convenience). To recover `bout_num`, map each frame's `Time` value to the window whose start/end bounds contain it, then cache the matching `timeRangeStart_<n>` / `timeRangeEnd_<n>` pair as that bout's metadata. The per-frame columns `leftFinPeaks`, `rightFinPeaks`, and `curBoutHeadYaw` provide additional bout context without needing a sidecar file.

### Bout-level Aggregate Metrics
Aggregate bout statistics (duration, distances, fin/tail frequencies, etc.) are still computed at runtime and are not serialized to `correct_format_results_enriched.csv`. Add those columns later if higher-level analytics require them; the graphs outlined below only depend on the per-frame signals that are already present.


## Graph catalog

### 1. Spine snapshots (`plotSpines`)
**Goal.** Visualize the fish posture at representative frames so analysts can verify skeletal tracking quality and see how fins behave at specific events.

**Inputs.**
- `spine`: for each frame, an ordered list of skeleton points with `x`, `y`, and confidence. Low-confidence points are gap-filled along each polyline.
- `leftFinAngles`, `rightFinAngles`: drive both confidence filtering and the optional “select by peak/parallel” modes.
- `bout_num`, `bout_start`, `bout_end`: restricts frame selection to bouts.
- `spine_plot_settings`: controls selection strategy (`select_by_bout`, `select_by_parallel_fins`, `select_by_peaks`), gradients, per-bout splitting, offsets, etc.
- `graph_cutoffs`: provides fin-angle thresholds when peaks are used.

**Behavior.**
- Frames can be sampled evenly across each bout (`spines_per_bout`), taken where fins move in parallel (angles ≈ 90°), or aligned to fin peaks (with optional suppression when both fins peak together).
- Every spine is translated so the head sits at the origin, rotated to face right, optionally mirrored, and offset horizontally so multiple frames can be stacked.
- The function records metadata about gaps/missing endpoints, prints the selected frame numbers, and writes interactive Plotly figures. When `split_plots_by_bout` is enabled it builds a tabbed HTML gallery (`spine_plots_tabbed.html`) plus PNG snapshots per bout; otherwise everything lands in `spine_plot_plotly.html` and `{imageTag}Spines.png`.

**Meaning.** Dense, color-coded polylines show bending along the spine during a swim bout. Large gaps or missing endpoints highlight where pose estimation failed. Comparing overlays reveals how posture evolves during a bout or near synchronized fin activity.

**CSV translation.**
- Use `LF_Angle` / `RF_Angle` arrays for fin thresholds and optionally reuse the `leftFinPeaks` / `rightFinPeaks` annotations when you want to align with the defaults captured by the CSV.
- Derive bout membership by mapping `Time` into the `timeRangeStart_<n>` / `timeRangeEnd_<n>` windows from the first row before sampling frames per bout.
- Pull pose information directly from `spine_points_json` or the flattened keypoint columns (`Spine_*`, `LeftFin_*`, `RightFin_*`, `Tail_*`, plus `HeadPX`, `HeadPY`, `TailPX`, `TailPY`), which already store the per-frame `x`, `y`, and confidence values needed to recreate the polylines.

### 2. Fin + tail timeline (`plotFinAndTailCombined`)
**Goal.** Plot synchronized time-series to show how left/right fin beating, tail displacement, and head yaw align during bouts.

**Inputs.**
- `leftFinAngles`, `rightFinAngles`, `tailDistances`, `headYaw`.
- `bout_num` to mask “None” separators between bouts.
- `angle_and_distance_plot_settings` toggles for which traces are shown.

**Behavior.**
- Builds a two-row Plotly subplot where row 1 contains both fin angles, and row 2 shows tail distance (primary y-axis) plus head yaw (secondary axis) if enabled.
- Inserts `None` separators between bouts so traces break cleanly.
- Saves `FinAndTailCombined_Subplots.html` and `.png`.

**Meaning.** Lets analysts correlate fin strokes with tail propulsion and head steering. Spikes above configured cutoffs indicate individual beats; phase offsets between fins or between fins and tail become visually apparent.

**CSV translation.**
- `LF_Angle`, `RF_Angle`, `Tail_Distance`, and `HeadYaw` columns already match the required arrays. Read them per frame and insert `None` separators whenever `Time` crosses one of the `timeRangeStart_<n>` / `timeRangeEnd_<n>` windows from the header row.
- Leverage `leftFinPeaks` / `rightFinPeaks` to annotate the traces without recomputing extrema unless you need custom peak logic.

### 3. Movement track overlay (`plotMovement`)
**Goal.** Overlay the head trajectory on a representative video frame to confirm spatial calibration.

**Inputs.**
- `headPixelsX`, `headPixelsY`: pixel coordinates per frame.
- `bout_num`: used to select frames from a specific bout.
- `videoFile`: read via OpenCV to fetch the frame that anchors the plot.
- `pixel_scale_factor`: manual tweak to align CSV coordinates with raw footage.
- `open_plots`: decides whether to open the figure.

**Behavior.**
- Loads a video frame (e.g., at `bout_start`), converts it to RGB, and adds it as a background image in Plotly.
- Scales the head coordinates, flips the y-axis so the path draws correctly, and plots a red spline line following the swim path for that bout.
- Writes `Zebrafish_Movement_Plotly.html` and `.png`.

**Meaning.** Validates that the coordinate system from DeepLabCut aligns with the video and highlights gross movement direction or arena boundaries.

**CSV translation.**
- `HeadPX`, `HeadPY` already carry per-frame pixel coordinates, and `TailPX`, `TailPY` give you the bounding reference when you need the crop extents. No reverse-scaling is required.
- `videoFile` and `pixel_scale_factor` are embedded in every row of the CSV, so the plotting helper can load the same footage and reuse the calibration constant without additional config plumbing.

### 4. Movement heatmap (`plotMovementHeatmap`)
**Goal.** Produce an intensity map showing where the head (and implicitly the fish body) spends time within its local neighborhood.

**Inputs.**
- `headPixelsX`, `headPixelsY`, `tailPixelsX`, `tailPixelsY` to determine crop bounds and positions.
- `bout_num`: iterated in sequence, pulling every relevant frame.
- `videoFile`: used to read all frames inside the selected bouts.

**Behavior.**
- Determines the maximum head–tail distance to size a square crop with a safety buffer.
- Reads all frames across the bouts, converts them to grayscale, crops around the head for each frame, and accumulates pixel intensities into a floating-point heatmap.
- Normalizes and gamma-corrects the heatmap before displaying via `px.imshow`, then writes `heatmap_plotly.html` and `Heatmap_Plotly.png`.

**Meaning.** Highlights spatial occupancy—bright regions correspond to positions/orientations the fish visited often during the chosen bouts.

**CSV translation.**
- `HeadPX`, `HeadPY`, `TailPX`, and `TailPY` provide the pixel trajectories needed to size crops and accumulate the intensity volume, so no supplemental artifact is required.
- Continue pulling the `videoFile` column to stream frames; it already points to the source clip used during calculation.

### 5. Head orientation tabs (`plotHead`)
**Goal.** Visualize head yaw at successive fin peaks to inspect turning behavior inside each bout.

**Inputs.**
- `headYaw` array.
- `leftFinAngles` and `rightFinAngles` to detect fin peaks (respecting `head_plot_settings` such as `fin_peaks_for_right_fin`, `ignore_synchronized_fin_peaks`, and `sync_fin_peaks_range`).
- `bout_num` to split into bouts when requested.
- `head_plot_settings`: includes a horizontal offset so multiple heads can be stacked.

**Behavior.**
- For each bout, records the first frame plus every frame where the selected fin exceeds its cutoff (after synchronization checks).
- Generates a parametric outline of a stylized head (defined by `headXPoints/headYPoints`), rotates it by the negative yaw, and offsets each successive outline to the right.
- When `split_plots_by_bout` is true it produces multiple Plotly figures embedded in a custom tabbed HTML shell (`head_plots_tabbed.html`) and PNG snapshots; otherwise everything is drawn onto a single figure.
- Also prints the frame numbers used so they can be audited.

**Meaning.** The stack of head outlines makes it easy to see if the fish consistently yaws toward one side during fin beats, or whether head motion is synchronized with fin usage.

**CSV translation.**
- Pull `HeadYaw`, `LF_Angle`, and `RF_Angle` directly from the CSV and partition the time-series by mapping each frame into the `timeRangeStart_<n>` / `timeRangeEnd_<n>` bounds.
- `leftFinPeaks` and `rightFinPeaks` already tag frames as `min`/`max` strokes when you want the same peak selection that the Bruce pipeline used; you can still recompute custom peaks from the angles if you need different smoothing or thresholds.

## Implications for the new implementation
1. **Pose + pixel data ship with the CSV.** `HeadPX`, `HeadPY`, `TailPX`, `TailPY`, `spine_points_json`, and the flattened fin/tail keypoint columns provide everything the spine, movement, and heatmap plots need without additional exports.
2. **Normalize bout handling.** Until a dedicated `bout_num` column lands, add a small helper that expands the `timeRangeStart_<n>` / `timeRangeEnd_<n>` header windows into per-frame bout IDs so every graph can rely on the same grouping logic.
3. **Optional aggregate metrics.** Bout-level summaries are still computed in memory; only add them to the CSV if a future visualization needs those pre-baked numbers.
4. **Maintain consistent outputs.** When building new Plotly components, reuse the same filenames (HTML + PNG) if you want drop-in compatibility with downstream automation that expects artifacts in the legacy `results/Results N` directories.
