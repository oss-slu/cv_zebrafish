# Calculations Utilities Overview

The modules under `calculations/utils/` provide the core data ingestion and computation building blocks for the zebrafish kinematics pipeline. They translate DeepLabCut pose outputs into structured arrays, execute geometric metrics, and assemble frame-by-frame summaries that downstream visualizations consume.

## Driver.py

`Driver.py` houses the high-level orchestration logic for analytics.

- **`run_calculations(parsed_points, config)`**  
  - Accepts the parsed pose dictionary from `Parser.py` plus the experiment configuration.  
  - Applies video scaling factors and decomposes the point dictionary into named limb/head structures.  
  - Executes the metric helpers from `Metrics.py` to derive fin angles (left/right), head yaw, head coordinates, tail angles, tail displacement, furthest tail point, and per-segment spine angles.  
  - Detects fin movement peaks and either computes swim bout ranges automatically (`get_time_ranges`) or respects user-specified intervals.  
  - Builds a tidy `pandas.DataFrame` capturing kinematic outputs for each frame, augmenting it with bout-relative yaw offsets and dedicated start/end columns for each detected range.  
  - Returns the DataFrame that powers reporting, graph exports, and any downstream analytics.

## Parser.py

`Parser.py` transforms DeepLabCut CSV exports into the structured format expected by the calculation layer.

- Loads CSVs with `header=1` to skip DLC metadata rows.
- Locates each `(x, y, likelihood)` triplet column associated with configured body-part names.
- Converts numeric columns into NumPy arrays and builds dictionaries with `x`, `y`, and `conf` vectors for every tracked point.
- Aggregates those dictionaries into `parsed_points`, organizing head anchors (`clp1`, `clp2`), tail points, fin control points, spine segments, and any raw configuration-defined tail metadata.
- The resulting structure feeds directly into `run_calculations`.

## Metrics.py

`Metrics.py` contains the geometric and signal-processing primitives that produce time-series metrics.

- **Fin and Head Geometry:**  
  - `calc_fin_angle` computes signed fin angles relative to head orientation, handling left/right conventions.  
  - `calc_yaw` derives head heading angles using arctangent of caudal peduncle points.
- **Tail and Spine Dynamics:**  
  - `calc_tail_angle` measures the angle between the caudal peduncle and tail tip.  
  - `calc_tail_side_and_distance` reports lateral displacement, signed side classification, and raw pixel distances for the tail tip.  
  - `calc_furthest_tail_point` inspects the tail polyline to identify the segment furthest from the head baseline.  
  - `calc_spine_angles` and the helper `get_angle_between_points` compute per-segment bending angles along the spine.
- **Fin Beat Detection:**  
  - `detect_fin_peaks` combines smoothing (`moving_average`) with threshold-based peak finding to locate fin beat extremes; it supports configurable horizontal buffers.
- **Swim Bout Identification:**  
  - `get_time_ranges` uses peak timing from fins (and optionally tail displacement) alongside user-provided thresholds (movement span, buffers, shifts) to segment continuous bouts, merging overlapping ranges as needed.
- Additional helpers support normalization, peak detection (`_get_peaks`), distance utilities, and array sanitation routines.

## configSetup.py

`configSetup.py` provides lightweight utilities for sourcing configuration files.

- **`loadConfig(src="LastConfig.json")`** attempts to load the most recent configuration snapshot. If absent, it falls back to `BaseConfig.json` and writes a copy to `LastConfig.json`, ensuring subsequent runs reuse the latest settings.

## \_\_init\_\_.py

The package initializer is intentionally minimal, simply marking `calculations/utils` as an importable namespace without exposing additional symbols. This keeps integrations explicit and discourages broad `import *` usage.

## Data Flow Summary

1. **Configuration** is loaded (historical or base) via `configSetup.py`.
2. **Pose CSVs** are parsed by `Parser.py` into structured NumPy-backed dictionaries.
3. **Metric computations** in `Metrics.py` transform coordinates into biomechanical signals.
4. **`run_calculations`** stitches those signals into a DataFrame, adds swim-bout annotations, and returns the canonical analytics table consumed by graphing and validation layers.

Together these modules isolate calculation responsibilities, making the pipeline easier to test, extend, and integrate with visualization outputs.
