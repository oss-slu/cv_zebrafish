# Graphing Module

Visualization pipeline for zebrafish movement analysis. Transforms enriched CSV metrics into interactive Plotly graphs and static PNG snapshots.

## Architecture

```
enriched CSV → GraphDataLoader → plotting functions → HTML/PNG outputs
```

- **[`data_loader.py`](data_loader.py)**: Loads and validates enriched CSV + config, exposes structured data accessors
- **[`modular_output_display.py`](modular_output_display.py)**: Modular plotting functions (spine snapshots, fin/tail timelines, head orientation, etc.)
- **[`outputDisplay.py`](outputDisplay.py)**: Legacy monolithic plotting code (maintained for compatibility)
- **[`generate_graphs.py`](generate_graphs.py)**: CLI entry point for graph generation

## Quick Start

### Generate Graphs from Enriched CSV

From the project root:

```bash
# Using modular plotting (recommended)
.venv/bin/python graphing/generate_graphs.py \
    test_enriched.csv \
    data_schema_validation/sample_inputs/jsons/BaseConfig.json \
    --modular

# Open plots interactively
.venv/bin/python graphing/generate_graphs.py \
    test_enriched.csv \
    data_schema_validation/sample_inputs/jsons/BaseConfig.json \
    --modular --open

# Using legacy plotting
.venv/bin/python graphing/generate_graphs.py \
    test_enriched.csv \
    data_schema_validation/sample_inputs/jsons/BaseConfig.json
```

Outputs land in `results/Results N/` with rotating folder numbers.

### Programmatic Usage

```python
from graphing.data_loader import GraphDataLoader
from graphing.modular_output_display import run_all_modular

# Load data
loader = GraphDataLoader("test_enriched.csv", "BaseConfig.json")

# Get structured data
bouts = loader.get_bouts()
time_ranges = loader.get_time_ranges()
input_values = loader.get_input_values()
calculated_values = loader.get_calculated_values()

# Generate graphs (modular)
meta = run_all_modular(
    time_ranges,
    loader.get_config(),
    input_values,
    calculated_values,
    loader.get_dataframe()
)

# Or use modern accessor methods
for bout in bouts:
    for frame in loader.iter_frames(bout):
        print(f"Frame {frame.idx}: HeadYaw={frame.metrics['HeadYaw']:.2f}°")
    
    left_peaks = loader.get_fin_peaks("left", bout)
    print(f"Left fin peaks in bout {bout.idx}: {left_peaks}")
```

## GraphDataLoader API

### Initialization

```python
loader = GraphDataLoader(
    csv_path="test_enriched.csv",
    config_path="BaseConfig.json",
    overrides={"custom_param": 42}  # Optional config overrides
)
```

### Modern Accessor Methods

```python
# Bout ranges
bouts = loader.get_bouts()  # Returns List[BoutRange]

# Iterate frames
for frame in loader.iter_frames():  # All frames
    print(frame.idx, frame.metrics["HeadYaw"])

for frame in loader.iter_frames(bouts[0]):  # Frames in specific bout
    print(frame.idx, frame.metrics["LF_Angle"])

# Fin peaks
left_peaks = loader.get_fin_peaks("left")  # All left fin peaks
right_peaks = loader.get_fin_peaks("right", bouts[0])  # Right fin peaks in bout 0

# Spine data
spines = loader.get_spines()  # Returns List[SpineFrame]
spines_bout = loader.get_spines(bouts[0])  # Spines in specific bout

# Pixel tracks (for heatmaps/movement plots)
tracks = loader.get_pixel_tracks()  # Returns List[PixelTrack]

# Configuration and raw data
config = loader.get_config()  # Returns defensive copy
df = loader.get_dataframe()  # Returns raw pandas DataFrame
```

### Legacy Bridge Methods

For compatibility with `outputDisplay.py`:

```python
# Legacy format expected by runAllOutputs()
time_ranges = loader.get_time_ranges()  # [[start, end], ...]
input_values = loader.get_input_values()  # Nested spine/fin/tail dicts
calculated_values = loader.get_calculated_values()  # Flat metric arrays
```

## Data Structures

### BoutRange

```python
@dataclass(frozen=True)
class BoutRange:
    idx: int        # Bout index (0-based)
    start: int      # Start frame
    end: int        # End frame (inclusive)
```

### TimeSeriesFrame

```python
@dataclass(frozen=True)
class TimeSeriesFrame:
    idx: int                    # Frame index
    metrics: Dict[str, float]   # All calculated metrics (HeadYaw, LF_Angle, etc.)
```

### SpineFrame

```python
@dataclass(frozen=True)
class SpineFrame:
    frame: int                              # Frame index
    points: List[Tuple[float, float, float]]  # [(x, y, conf), ...]
```

### PixelTrack

```python
@dataclass(frozen=True)
class PixelTrack:
    frame: int                              # Frame index
    points: Dict[str, Tuple[float, float]]  # {"head": (x, y), "tail": (x, y), ...}
```

## Schema Constants

The `Schema` class centralizes column name constants:

```python
from graphing.data_loader import Schema

# Core metrics
print(Schema.LF_ANGLE)      # "LF_Angle"
print(Schema.HEAD_YAW)      # "HeadYaw"
print(Schema.TAIL_DISTANCE) # "Tail_Distance"

# Prefixes for iteration
print(Schema.SPINE_PREFIX)      # "Spine_"
print(Schema.TAIL_ANGLE_PREFIX) # "TailAngle_"

# Helper methods
x, y, conf = Schema.get_spine_columns("0")
# Returns: ("Spine_0_x", "Spine_0_y", "Spine_0_conf")
```

## Configuration

The loader expects a JSON config with these keys:

```json
{
  "points": {
    "spine": ["0", "1", "2", ..., "13"],
    "left_fin": ["0", "1"],
    "right_fin": ["0", "1"],
    "tail": ["0", "1", "2", ..., "12"],
    "head": {"pt1": "0", "pt2": "1"}
  },
  "video_parameters": {
    "recorded_framerate": 30,
    "pixel_scale_factor": 1.0
  },
  "graph_cutoffs": {
    "left_fin_angle": 45.0,
    "right_fin_angle": 45.0
  },
  "shown_outputs": {
    "show_spines": true,
    "show_angle_and_distance_plot": true,
    "show_head_plot": true,
    "show_movement_track": false,
    "show_heatmap": false
  },
  "spine_plot_settings": {
    "select_by_bout": true,
    "select_by_parallel_fins": false,
    "select_by_peaks": false,
    "spines_per_bout": 5,
    "min_accepted_confidence": 0.5,
    "plot_draw_offset": 15,
    "split_plots_by_bout": false
  }
}
```

### Configuration Overrides

Pass runtime overrides via the `overrides` parameter:

```python
loader = GraphDataLoader(
    csv_path="data.csv",
    config_path="BaseConfig.json",
    overrides={
        "video_parameters": {"recorded_framerate": 60},
        "open_plots": True
    }
)
```

## Graph Types

### 1. Spine Snapshots (`plotSpines`)
Visualizes fish posture at representative frames. Selection strategies:
- **By bout**: Evenly spaced frames per bout
- **By parallel fins**: When left and right fins are approximately parallel
- **By peaks**: When one fin peaks while the other is down

Configure via `spine_plot_settings` in config.

### 2. Fin + Tail Timeline (`plotFinAndTailCombined`)
Synchronized time-series of:
- Left fin angle
- Right fin angle
- Tail distance from midline
- Head yaw (optional secondary axis)

### 3. Head Orientation (`plotHead`)
Stylized head outlines rotated by yaw angle at fin peaks. Shows turning behavior during swim bouts.

### 4. Movement Track (`plotMovement`)
Head trajectory overlaid on video frame. Requires:
- Pixel coordinates (`HeadPX`, `HeadPY`)
- Video file path in config

### 5. Movement Heatmap (`plotMovementHeatmap`)
Intensity map showing spatial occupancy. Requires:
- Pixel coordinates for head and tail
- Video file path

### 6. Dot Plots (`showDotPlot`)
Scatter plots for correlations:
- Tail distance vs. left/right fin angles
- Tail distance movement vs. fin angle movement

## Testing

Run the test suite:

```bash
# From project root
pytest graphing/tests/test_data_loader.py -v

# With coverage
pytest graphing/tests/test_data_loader.py --cov=graphing.data_loader --cov-report=html
```

Test coverage includes:
- Initialization and validation
- Column missing/malformed detection
- Bout range parsing
- Frame iteration and filtering
- Fin peak detection
- Legacy bridge methods
- Configuration overrides

## Error Handling

Custom exceptions for debugging:

```python
from graphing.data_loader import (
    LoaderError,             # Base exception
    MissingColumnError,      # Required columns absent
    MalformedBoutRangeError, # Invalid time range metadata
    InconsistentLengthError  # Array length mismatches
)

try:
    loader = GraphDataLoader("bad.csv", "config.json")
except MissingColumnError as e:
    print(f"Missing columns: {e}")
    # Error message includes which columns are missing
```

## Performance Notes

- **Memory**: Entire CSV loaded into pandas DataFrame. For large files (>100k frames), consider chunked processing.
- **Caching**: Data structures (bouts, spines, tracks) are built on-demand, not cached. Repeated calls re-compute.
- **Parallelization**: Not currently implemented. Graph generation is sequential.

## Migration from Legacy

If you're migrating from `outputDisplay.py`:

### Before (Legacy)
```python
from graphing.outputDisplay import runAllOutputs, getOutputFile

# Complex manual data preparation...
getOutputFile(config)
runAllOutputs(timeRanges, config, resultsList, inputValues, calculatedValues, df)
```

### After (Modular)
```python
from graphing.data_loader import GraphDataLoader
from graphing.modular_output_display import run_all_modular

loader = GraphDataLoader("enriched.csv", "config.json")
meta = run_all_modular(
    loader.get_time_ranges(),
    loader.get_config(),
    loader.get_input_values(),
    loader.get_calculated_values(),
    loader.get_dataframe()
)
```

### After (Modern API)
```python
from graphing.data_loader import GraphDataLoader
from graphing.modular_output_display import plot_spines, plot_fin_tail_combined

loader = GraphDataLoader("enriched.csv", "config.json")

# Fine-grained control over individual plots
for bout in loader.get_bouts():
    frames_in_bout = list(loader.iter_frames(bout))
    # Custom analysis...
```

## File Structure

```
graphing/
├── __init__.py                      # Package marker
├── README.md                        # This file
├── data_loader.py                   # Data loading and validation
├── modular_output_display.py        # Modular plotting functions
├── outputDisplay.py                 # Legacy plotting (monolithic)
├── generate_graphs.py               # CLI entry point
├── output_adapter.py                # Full pipeline adapter
├── legacy_output_graph_reference.md # Documentation of legacy behavior
├── graph_data_loader_plan.md        # Design document
└── tests/
    ├── __init__.py
    └── test_data_loader.py          # Unit tests
```

## Troubleshooting

### Import Errors
```bash
# Ensure you're running from project root
cd /path/to/cv_zebrafish

# Or use module form
PYTHONPATH=. python -m graphing.generate_graphs ...
```

### Missing Dependencies
```bash
source .venv/bin/activate
pip install pandas numpy plotly kaleido opencv-python pillow matplotlib
```

### Config Key Errors
Enable safe key access in plotting code:
```python
# Bad (raises KeyError if missing)
value = config["spine_plot_settings"]["mult_spine_gradient"]

# Good (provides default)
value = config.get("spine_plot_settings", {}).get("mult_spine_gradient", True)
```

### Movement/Heatmap Plots Skipped
These require pixel coordinates. Ensure your enriched CSV has:
- `HeadPX`, `HeadPY`, `TailPX`, `TailPY` columns
- Video file path in config: `config["file_inputs"]["video"]`

## Contributing

When adding new metrics or plots:
1. Update [`Schema`](data_loader.py) class with new column constants
2. Add to `REQUIRED_COLUMNS` if mandatory
3. Update `test_data_loader.py` fixtures
4. Document in this README

## References

- Design plan: [`graph_data_loader_plan.md`](graph_data_loader_plan.md)
- Legacy behavior: [`legacy_output_graph_reference.md`](legacy_output_graph_reference.md)
- Calculations: [`../calculations/README.md`](../calculations/README.md)
