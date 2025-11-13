# Legacy Zebrafish Analysis Pipeline

## High-Level Flow
- `codes/main.py` loads `BaseConfig.json`, creates a new run folder via `utils.outputDisplay.getOutputFile`, and reads the DeepLabCut CSV defined in `file_inputs.data`.
- `utils.mainCalculation.setupValueStructs` converts all configured point labels into per-frame numeric series (x, y, confidence) for later calculations and plotting.
- `utils.mainCalculation.getCalculated` iterates through the recording frame-by-frame to compute fin angles, tail displacement, head pose, and spine segment angles. It also derives swim bouts either automatically or from the provided ranges.
- `utils.outputDisplay.runAllOutputs` writes textual summaries, time-series tables, and the configured figures. The results are saved alongside `log.txt` and `output_data.xlsx` in the freshly created `results/Results N` folder.
- When `bulk_input` is enabled the same pipeline is executed for every CSV in the configured directory, producing a subfolder per file under `bulk_results/Results N`.

## Inputs and Configuration

### Configuration files
- `configs/BaseConfig.json` defines default settings; `LastConfig.json` can persist edits when the interactive loader in `configSetup.getConfig()` is used.
- Key sections:
  - `file_inputs`: absolute paths for the tracking CSV, the raw video, and optional bulk-input directory.
  - `points`: mapping from semantic body parts to the DLC column names. Every entry is resolved into `(x, y, confidence)` columns inside the CSV.
  - `shown_outputs`, `angle_and_distance_plot_settings`, `spine_plot_settings`, and `head_plot_settings`: feature toggles for textual output and figure behaviour.
  - `video_parameters`: real-world scale information. The code derives `scaleFactor = pixel_scale_factor * dish_diameter_m / pixel_diameter` to convert pixel distances to metres.
  - `graph_cutoffs`: thresholds (degrees or metres) that drive peak detection, swim bout segmentation, and plot highlighting.
  - `auto_find_time_ranges`, `time_ranges`: choose between automatic bout detection and explicit frame windows.
  - `open_plots` and `bulk_input`: control interactive display and batch processing.

### Input tracking data
- Expects a DeepLabCut-style CSV where row 0 stores metadata, row 1 contains headers such as `Head`, `Head.1`, `Head.2`, and subsequent rows contain numeric data.
- For each configured label `L`, the code reads three columns: `L` (x), `L.1` (y), `L.2` (confidence score). Data is cast to numeric with `pandas.to_numeric`, and confidence values are later used to filter unreliable segments.
- The CSV must contain all labels referenced in `config["points"]`, including the ordered spine list and tail points.

### Video asset and scaling
- `file_inputs.video` supplies the corresponding recording. It is sampled by OpenCV (`cv2.VideoCapture`) to grab a background frame for the track overlay and to assemble the heatmap.
- `video_parameters.recorded_framerate` drives conversion between frame counts and swimming frequency / velocity readouts.

### Bulk mode
- When `config["bulk_input"]` is true, every `.csv` inside `file_inputs.bulk_input_path` is processed. Output for each file is written into `bulk_results/Results N/<trimmed filename>` with its own `log.txt`, figures, and spreadsheet.

## Data Preparation and Internal Structures
- `setupValueStructs` allocates zero-filled NumPy arrays for metrics such as `rightFinAngles`, `tailDistances`, `headYaw`, plus string arrays for categorical outputs like `furthestTailPoint`.
- The function also builds an `inputValues` dictionary where each key maps to a list of per-frame dictionaries:
  - `spine`, `rightFin`, `leftFin`, and `tail` are lists of point series preserving the configured ordering.
  - `clp1`/`clp2` represent the two centerline anchor points used to orient the fish.
  - `head` and `tp` supply the head reference point and terminal tail point.
- These structures allow later stages to sample any frame simply by indexing `[row]` on the stored lists.

## Per-Frame Calculations (`utils/mainCalculation.getCalculated`)
For every frame (row) in the tracking CSV:
- Fit a straight line through the two centerline points (head reference and swim bladder) using `np.polyfit`. This defines the instantaneous midline of the fish.
- Compute fin angles with `utils.mainFuncs.getFinAngle`, which creates vectors from the head axis to each fin segment and measures the signed angle between them. Left fins retain their sign, right fins are mirrored so that outward deflections have consistent polarity.
- If three points per fin are provided, `getAngleBetweenPoints` is applied to obtain an explicit elbow angle.
- Determine the shortest signed distance between the tail endpoint and the midline; multiply by the scale factor to express the result in metres. The sign is preserved to track whether the tail deflects left or right of the midline.
- Record whether the tail is on the left, right, or exactly on the center line, and store the identity of the tail point with the largest absolute deflection in the configured tail chain.
- Convert head coordinates from pixels to metres (using the same scale factor) while retaining the raw pixel positions for later overlays.
- Copy tail pixel coordinates for movement plots and heatmaps.
- Compute head yaw via `getYawDeg`, measuring the angle of the centerline relative to the image x-axis.
- Append a result row containing: frame index, left/right fin angles, three-point fin angles (if available), scaled tail distance, left/right classification, furthest deflected tail landmark, and a spine bend value for every consecutive triple along the configured spine list.

## Swim Bout Detection
- `utils.outputDisplay.getPeaks` scans the fin- and tail-angle traces for threshold crossings defined in `graph_cutoffs`. Positive and negative tail excursions are tracked separately.
- `getTimeRanges` walks the timeline looking for windows where the most recent fin (and optionally tail) peaks fall within `movement_bout_width` frames. Detected bouts are expanded by `swim_bout_buffer` on each side and shifted by `swim_bout_right_shift` before being merged to avoid overlaps.
- When `use_tail_angle` is true the tail peak must also be recent; otherwise only the fin angles gate the bout.
- If `auto_find_time_ranges` is false, the code skips detection and reuses the explicit ranges from `config["time_ranges"]`.

## Bout Normalization and Result Assembly
- Head yaw is recentered per bout by subtracting the yaw at the start frame from every sample in the same range. This makes head-plot overlays comparable.
- `resultsList` is padded so that frames outside any bout have blank `curBoutHeadYaw` values, preventing lines from crossing gaps in the exported spreadsheet.
- Each detected (or provided) bout writes its start and end frame back into the first rows of `resultsList` so that the spreadsheet captures the chosen windows.

## Textual Summaries and Spreadsheet Export
- Toggleable printers (`printLeftFinFreq`, `printRightFinFreq`, `printTailFreq`) reuse `getFrequencyAndPeakNum` to measure peak-to-peak distances (converted with `recorded_framerate`) and log frequencies.
- `printTotalDistance` and `printTotalSpeed` calculate displacement and mean velocity between the first and last frame of every bout based on the metre-scaled head positions.
- Every text snippet is funnelled through `printToOutput`, which echoes to stdout and appends to `Results N/log.txt`.
- `saveResultstoExcelFile` serializes `resultsList` to `Results N/output_data.xlsx`, giving downstream tools access to all per-frame metrics.

## Visual Outputs
All figure writers live in `utils/outputDisplay.py` and honour the `shown_outputs` flags.

### Spine plot (`plotSpines`)
- Candidate frames are selected by one of three strategies: evenly spaced within each bout (`select_by_bout`), fin-peak driven (`select_by_peaks`), or parallel-fin alignment (`select_by_parallel_fins`). Each candidate frame must satisfy the confidence thresholds from `spine_plot_settings`, otherwise it is dropped.
- For every retained frame the code normalizes coordinates so the head anchor sits at the origin, rotates the spine using `rotateAroundOrigin` so the head-to-third-spine segment points left-to-right, mirrors it so dorsal is up, and offsets successive frames along the x-axis (`plot_draw_offset`) to prevent overlap.
- Segments inherit either a smooth colour gradient (if `draw_with_gradient`) or cycle through preset colours. Diagnostic warnings list frames with large gaps or missing end points.
- Each bout becomes a tab in an HTML report (`spine_plots_tabbed.html`) and a corresponding PNG snapshot is saved.

### Head orientation plot (`plotHead`)
- Uses peak detection (respecting synchronization rules and minimum confidence) to choose frames within each bout. A stylized six-point head silhouette is rotated by the normalized head yaw for each selected frame.
- Frames are offset horizontally to form a ribbon that shows how the head reorients across fin beats. Output mirrors the spine plot: tabbed HTML plus PNG exports.

### Combined fin/tail time series (`plotFinAndTailCombined`)
- Builds Plotly subplots that align fin angles, head yaw, and tail distance over frame indices. Bouts are separated by inserting `None` breaks so traces are segmented visually.
- Secondary y-axes keep angles and distances readable, and the resulting figure is written to both HTML and PNG.

### Movement track overlay (`plotMovement`)
- Grabs the video frame at the final index of the first bout, converts it to RGB, and scales DLC coordinates using the same `scaleFactor` as the calculations.
- Draws the head trajectory (frame order) as a spline on top of the video frame, producing an HTML view and a high-resolution PNG (`Zebrafish_Movement_Plotly.png`).

### Movement heatmap (`plotMovementHeatmap`)
- Crops every frame in each bout to a square window centred on the head (twice the max observed head–tail separation multiplied by `bufferMult`).
- Converts each crop to grayscale and accumulates the intensities into a single heatmap array, normalizes it, applies gamma correction, and renders the density field with Plotly Express. Outputs include `heatmap_plotly.html` and `Heatmap_Plotly.png`.

## Output Directory Layout
- Each run resides in `results/Results N/` (or, in bulk mode, `bulk_results/Results N/<input>/`). Contents include:
  - `log.txt` – textual summaries and warnings.
  - `output_data.xlsx` – per-frame table with all computed metrics.
  - One HTML + PNG pair per enabled plot (spine, head, movement, heatmap, combined fin/tail).
  - Any auxiliary HTML reports (tabbed plot viewers) created by the plotting helpers.

## Bulk Run Behaviour
- The pipeline reuses the same configuration for every CSV in the bulk directory. Before processing a file it trims the basename to 35 characters (adding `_short` when necessary) to construct the output folder name.
- Shared state in `utils.outputDisplay.outputsDict` is reassigned for each bulk file to make sure logs and figures land in the proper subfolder.

## Key Modules at a Glance
- `utils/mainFuncs.py`: helper math (column lookup, fin angles, yaw, generic angle calculation) and CSV extraction utilities.
- `utils/mainCalculation.py`: orchestrates numeric derivations and prepares the table consumed by downstream outputs.
- `utils/outputDisplay.py`: handles bout detection, logging, figure generation, video sampling, and file I/O.
- `utils/configSetup.py`: optional interactive config loader that keeps `LastConfig.json` in sync with manual edits.

With these pieces together, the legacy code ingests labeled tracking data, computes kinematic descriptors for the zebrafish, segments meaningful swimming bouts, and produces both tabular summaries and visualization artefacts that highlight fin motion, spine curvature, and movement trajectories.
