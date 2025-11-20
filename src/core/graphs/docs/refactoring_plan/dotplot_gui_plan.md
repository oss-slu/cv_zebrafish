# Dot Plot GUI Integration Plan

## Overview
- Show dot plots directly in the PyQt GraphViewerScene right after calculations finish.
- Reuse the existing `render_dot_plot` helper; no extra builder classes.
- Keep file IO off the GUI path so previewing plots stays responsive.

## Steps
1. **Emit richer payloads**
   - Update both calculation scenes to emit a dict containing at least: the pandas DataFrame of results, the loaded config dict, and the CSV path.
   - MainWindow keeps passing that payload to `GraphViewerScene.set_data`.

2. **Interpret config flags inside GraphViewerScene**
   - Inside `set_data`, validate the payload and pull `config["shown_outputs"]`.
   - Mirror the legacy feature flags (`show_tail_left_fin_angle_dot_plot`, etc.) so only requested dot plots are built.

3. **Call `render_dot_plot` directly**
   - Use the DataFrame columns (`Tail_Distance`, `LF_Angle`, `RF_Angle`, etc.) to feed `render_dot_plot`.
   - For the "moving" plots, compute `np.diff(series) * framerate` using `config["video_parameters"]["recorded_framerate"]`.
   - Pass `ctx=None` so no HTML/PNG files are created when running inside the GUI.

4. **Populate the scene**
   - Take each returned `DotPlotResult.figure` and feed it into `set_graphs` so the list on the left gains entries automatically.
   - Reuse the existing empty-state messaging when no plots were requested or a required column is missing.

5. **Surface runtime issues**
   - If kaleido is missing (Plotly can’t export PNGs), keep the existing `_show_empty_state` error message visible.
   - Optionally bubble lightweight warnings (e.g., missing config keys) to the status label so the user knows why a plot didn’t appear.

## Validation
- Manual smoke test: run a calculation, ensure the dot plots appear when the matching config flags are enabled.
- Lightweight unit test for `set_data` to confirm it creates the expected number of figures for a dummy payload.
- Document the kaleido dependency in the README so developers enable PNG export for the GUI.
