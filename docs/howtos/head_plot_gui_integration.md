# Head Plot GUI Integration

## Overview
Head plots are now integrated into the GraphViewerScene and appear automatically in the GUI when calculations complete, following the same pattern as dot plots. Both use the DataFrame directly for optimal performance.

## Implementation Details

### Configuration Flag
Head plots are controlled by the `show_head_plot` flag in the config's `shown_outputs` section:

```json
{
  "shown_outputs": {
    "show_head_plot": true
  }
}
```

### Integration Points

#### GraphViewerScene.py
- **HEAD_PLOT_SPEC**: Configuration dict defining:
  - `flag`: Config key to enable head plots (`show_head_plot`)
  - `title_prefix`: Display name prefix for generated plots
  - `required_df_cols`: Required DataFrame columns (`HeadYaw`, `LF_Angle`, `RF_Angle`)
  - `settings_key`: Config section for head plot settings (`head_plot_settings`)
  - `default_settings`: Fallback values for plot parameters

- **build_head_plot_graphs()**: New function that:
  1. Checks if `show_head_plot` flag is enabled
  2. Validates required DataFrame columns are present
  3. Extracts data directly from DataFrame using `_as_numeric_array()` helper
  4. Gets time ranges from config (defaults to full dataset if not specified)
  5. Calls `plot_head()` with `ctx=None` (no file output in GUI mode)
  6. Returns dict of Plotly figures with descriptive names

- **set_data()**: Updated to:
  - Build both dot plots and head plots from the same DataFrame
  - Combine warnings from both builders
  - Display all graphs in the sidebar list

### Data Flow (Optimized)
1. **Calculation Scene** completes and emits payload:
   ```python
   {
       "results_df": pandas.DataFrame,  # Contains all necessary columns
       "config": dict
   }
   ```

2. **GraphViewerScene.set_data()** receives payload and:
   - Calls `build_dot_plot_graphs(results_df, config)`
   - Calls `build_head_plot_graphs(results_df, config)` ← **Optimized: uses DataFrame directly**
   - Merges results and populates graph list

3. **User selects graph** from sidebar → rendered as PNG via kaleido

### Performance Optimization
**Key improvement**: Head plots now extract data directly from the DataFrame instead of reloading the CSV file:
- ✅ **No redundant file I/O**: Eliminates CSV re-read
- ✅ **No redundant parsing**: Avoids re-creating GraphDataLoader/GraphDataBundle
- ✅ **Lower memory footprint**: No duplicate data structures
- ✅ **Faster GUI response**: Data already in memory from calculations
- ✅ **Consistent pattern**: Both plot types use DataFrame extraction

### Head Plot Behavior
- When `split_plots_by_bout=true` (default):
  - Multiple figures generated, one per time range
  - Named: "Head Plot: head_plot_range_[start,_end]"
- When `split_plots_by_bout=false`:
  - Single combined figure
  - Named: "Head Plot"

### Error Handling
Graceful degradation with warning messages:
- **Flag disabled**: Head plot not built (silent)
- **Missing DataFrame columns**: Warning tooltip listing missing columns (e.g., "HeadYaw")
- **Empty DataFrame**: Warning: "Head plot skipped: DataFrame is empty."
- **Plot generation failure**: Warning with exception message

### Settings Integration
Head plot settings from config are merged with defaults:
```python
{
    "head_plot_settings": {
        "plot_draw_offset": 15,
        "ignore_synchronized_fin_peaks": True,
        "sync_fin_peaks_range": 3,
        "fin_peaks_for_right_fin": False,
        "split_plots_by_bout": True
    },
    "graph_cutoffs": {
        "left_fin_angle": 10,
        "right_fin_angle": 10
    }
}
```

## Testing
Four test cases in `tests/unit/ui/test_graph_viewer_scene.py`:
1. **test_set_data_generates_requested_dot_plots**: Verifies dot plots still work
2. **test_set_data_skips_head_plot_when_flag_disabled**: Confirms head plots aren't generated when flag is false
3. **test_set_data_warns_when_head_plot_missing_required_columns**: Validates warning when DataFrame columns are missing
4. **test_set_data_generates_head_plot_when_all_data_present**: Confirms head plot generation with complete data

## Usage
1. Enable head plots in your config JSON:
   ```json
   "shown_outputs": { "show_head_plot": true }
   ```
2. Run calculations in the GUI
3. Head plots appear automatically in the graph viewer sidebar alongside dot plots
4. Click to view static PNG renderings

## Dependencies
- **plotly**: For figure generation
- **kaleido**: For PNG export (required for GUI rendering)
- **plot_head**: Core plotting function from `src.core.graphs.plots.headplot`
- **pandas/numpy**: For DataFrame manipulation and array operations

## Alignment with Dotplot Pattern
Following `dotplot_gui_plan.md`:
- ✅ Emit richer payloads (DataFrame contains all necessary data)
- ✅ Interpret config flags inside GraphViewerScene
- ✅ Extract data directly from DataFrame (no file I/O on GUI path)
- ✅ Call plotting function directly with `ctx=None`
- ✅ Populate scene with returned figures
- ✅ Surface runtime issues via tooltips and empty-state messages
- ✅ Keep responsive by avoiding redundant data loading

## Architecture Decision: DataFrame-Based Approach

### Why Extract from DataFrame?
The initial implementation reloaded the CSV file via `GraphDataLoader`, but this was redundant since:
- `leftFinAngles` = DataFrame column `LF_Angle`
- `rightFinAngles` = DataFrame column `RF_Angle`
- `headYaw` = DataFrame column `HeadYaw`

### Comparison

| Aspect | Old Approach (CSV Reload) | New Approach (DataFrame) |
|--------|---------------------------|--------------------------|
| Data Source | Reload CSV via GraphDataLoader | Extract from existing DataFrame |
| File I/O | Re-reads entire CSV | None - data in memory |
| Memory | Duplicate loader/bundle objects | Single DataFrame reference |
| Performance | Slower (disk I/O + parsing) | Faster (memory access only) |
| Coupling | Requires csv_path in payload | Only needs DataFrame |
| Consistency | Different from dot plots | Same pattern as dot plots |

### Benefits of Current Implementation
1. **Performance**: No redundant file I/O or parsing
2. **Simplicity**: Both plot types use same DataFrame extraction pattern
3. **Maintainability**: Less coupling to file system paths
4. **Memory efficiency**: No duplicate data structures
5. **GUI responsiveness**: Data already available from calculations

## Future Enhancements
- Add integration test with real calculation pipeline
- Support dynamic plot refresh on config change
- Add export-to-file button in GUI for saving plots manually
- Consider adding time range editor for interactive bout selection
