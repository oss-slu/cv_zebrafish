# Zebrafish Movement Metrics — Sprint 2 Refactor

## Overview
This sprint focused on modularizing and simplifying the zebrafish movement metrics pipeline.  
The original implementation contained all computation logic (head yaw, fin angles, tail distances, peak detection, etc.) inside one large function.  
To improve maintainability, we refactored this into smaller, reusable components that can be easily extended.

---

## Objectives
- Restructure the monolithic calculation logic into modular, testable functions.  
- Implement a clean and reusable `run_calculations()` orchestrator that outputs key kinematic metrics.  
- Add unit tests using a small DLC-style CSV to verify correctness and NaN handling.  
- Lay the foundation for future extensions such as tail distance, bout detection, and curvature.

---

## Implemented Components

### 1. `run_calculations(parsed_points, config)`
A simplified, modular version of the original metrics function.

#### Inputs
- `parsed_points` — a dictionary mapping body part labels to `(x_array, y_array, conf_array)` tuples.
  ```python
  {
      "head_pt1": (x, y, conf),
      "head_pt2": (x, y, conf),
      "rfin_base": (x, y, conf),
      "rfin_tip":  (x, y, conf),
      "lfin_base": (x, y, conf),
      "lfin_tip":  (x, y, conf),
  }

  ## Outputs

- Time: Frame number / FPS
- RF_Angle: Right fin angle relative to head centerline 
- LF_Angle: Right fin angle relative to head centerline 
- HeadYaw: Orientation of the head centerline relative to the +X axis 

## Features 

- Vectorized computation using NumPy (fast and concise)
- Handles missing or invalid points gracefully using NaN masking
- Modular structure — new metrics can be added later as new columns

## -------- TESTING -------- ##

A pytest-based test suite validating numerical correctness, schema, and NaN handling.

## Test 1 — test_run_calculations_basic
- Builds a tiny synthetic DLC-style CSV with two frames:
- Frame 0: fish aligned along +X → yaw ≈ 0°, fin angles ≈ 0°
- Frame 1: fish aligned along +Y → yaw ≈ +90°, left fin ≈ -90°

Parses the CSV into the expected parsed_points dictionary
Confirms:
- Correct column structure
- Expected angles within numerical tolerance
- Proper time scaling (fps = 10 → Δt = 0.1s)

## Test 2 — test_zero_centerline_gives_nan
- Modifies frame 0 so the head centerline length = 0
- Ensures all angles become NaN for that frame (valid error handling)
- Validates that later frames remain valid (finite numbers)

Running the test: 
pip install pytest pandas numpy
pytest -q

## Future Implementations 

- Add more metrics (easily done in this modular setup)
- DB and frontend integration 

