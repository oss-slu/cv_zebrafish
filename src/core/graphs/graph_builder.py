"""Build Plotly graphs from calculation payloads (CPU-heavy; safe off the UI thread)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objs as go
import plotly.io as pio

from core.calculations.cancelled import CalculationAborted
from core.graphs.loader_bundle import GraphDataBundle
from core.graphs.plots import render_dot_plot, render_fin_tail, render_headplot, render_spines

GraphSource = Any  # go.Figure or a saved image path (str/Path)

DOT_PLOT_SPECS: Tuple[Dict[str, Any], ...] = (
    {
        "flag": "show_tail_left_fin_angle_dot_plot",
        "title": "Tail Distance vs Left Fin Angle",
        "x_col": "Tail_Distance",
        "y_col": "LF_Angle",
        "name_x": "tailDist",
        "name_y": "leftFinAng",
        "units_x": "m",
        "units_y": "deg",
        "moving": False,
    },
    {
        "flag": "show_tail_right_fin_angle_dot_plot",
        "title": "Tail Distance vs Right Fin Angle",
        "x_col": "Tail_Distance",
        "y_col": "RF_Angle",
        "name_x": "tailDist",
        "name_y": "rightFinAng",
        "units_x": "m",
        "units_y": "deg",
        "moving": False,
    },
    {
        "flag": "show_tail_left_fin_moving_dot_plot",
        "title": "Tail Distance vs Left Fin Angle (Moving)",
        "x_col": "Tail_Distance",
        "y_col": "LF_Angle",
        "name_x": "tailDistMov",
        "name_y": "leftFinAngMov",
        "units_x": "m/s",
        "units_y": "deg/s",
        "moving": True,
    },
    {
        "flag": "show_tail_right_fin_moving_dot_plot",
        "title": "Tail Distance vs Right Fin Angle (Moving)",
        "x_col": "Tail_Distance",
        "y_col": "RF_Angle",
        "name_x": "tailDistMov",
        "name_y": "rightFinAngMov",
        "units_x": "m/s",
        "units_y": "deg/s",
        "moving": True,
    },
)


def _as_numeric_array(series: pd.Series) -> np.ndarray:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.to_numpy()


def safe_filename(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", title).strip("_")


def safe_dirname(name: str) -> str:
    return safe_filename(name) or "item"


def is_kaleido_available() -> bool:
    try:
        import kaleido  # noqa: F401
    except Exception:
        return False
    return True


def get_graph_names_to_build(data: Optional[Dict[str, Any]]) -> List[str]:
    if not data or not isinstance(data, dict):
        return []
    results_df = data.get("results_df")
    config = data.get("config")
    if not isinstance(results_df, pd.DataFrame) or not isinstance(config, dict):
        return []
    parsed_points = data.get("parsed_points")
    names: List[str] = []
    shown_outputs = (config or {}).get("shown_outputs") or {}
    video_params = (config or {}).get("video_parameters") or {}

    if results_df.shape[0] > 0:
        for spec in DOT_PLOT_SPECS:
            if not shown_outputs.get(spec["flag"], False):
                continue
            missing_cols = [
                c for c in (spec["x_col"], spec["y_col"])
                if c not in results_df.columns
            ]
            if missing_cols:
                continue
            if spec["moving"] and video_params.get("recorded_framerate") is None:
                continue
            names.append(spec["title"])

    if shown_outputs.get("show_angle_and_distance_plot"):
        required = ["LF_Angle", "RF_Angle", "Tail_Distance"]
        if all(c in results_df.columns for c in required):
            names.append("Fin Angles + Tail Distance")

    if shown_outputs.get("show_spines") and parsed_points and "spine" in parsed_points:
        if "LF_Angle" in results_df.columns and "RF_Angle" in results_df.columns:
            time_ranges = extract_time_ranges(config, results_df)
            spine_settings = (config or {}).get("spine_plot_settings") or {}
            split_by_bout = bool(spine_settings.get("split_plots_by_bout", True))
            if split_by_bout and time_ranges:
                names.extend(f"Spines Bout {i}" for i in range(len(time_ranges)))
            elif not split_by_bout or not time_ranges:
                names.append("Spines Combined")

    if shown_outputs.get("show_head_plot") and "HeadYaw" in results_df.columns:
        names.append("Head Orientation")

    tpa = ((config or {}).get("custom_calculations") or {}).get("three_point_angle") or {}
    out_col = str(tpa.get("output_column") or "ThreePointAngle")
    if tpa.get("enabled", False) and out_col in results_df.columns:
        names.append(f"Custom Angle: {out_col}")

    return names


def _iter_dot_plot_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any], warnings: List[str]
):
    shown_outputs = (config or {}).get("shown_outputs") or {}
    video_params = (config or {}).get("video_parameters") or {}
    framerate = video_params.get("recorded_framerate")

    if results_df.shape[0] == 0:
        warnings.append("The calculation DataFrame is empty; nothing to plot.")
        return

    any_flag_enabled = any(
        shown_outputs.get(spec["flag"], False) for spec in DOT_PLOT_SPECS
    )
    if not any_flag_enabled:
        warnings.append("No dot plot flags are enabled in the config.")
        return

    for spec in DOT_PLOT_SPECS:
        if not shown_outputs.get(spec["flag"], False):
            continue
        missing_cols = [
            col for col in (spec["x_col"], spec["y_col"])
            if col not in results_df.columns
        ]
        if missing_cols:
            warnings.append(
                f"Skipping '{spec['title']}' because columns "
                f"{', '.join(missing_cols)} are missing."
            )
            continue
        values_x = _as_numeric_array(results_df[spec["x_col"]])
        values_y = _as_numeric_array(results_df[spec["y_col"]])
        if spec["moving"]:
            if framerate is None:
                warnings.append(
                    f"Skipping '{spec['title']}' because "
                    "'video_parameters.recorded_framerate' is missing."
                )
                continue
            if len(values_x) < 2 or len(values_y) < 2:
                warnings.append(
                    f"Skipping '{spec['title']}' because at least "
                    "two frames are required."
                )
                continue
            values_x = np.diff(values_x) * framerate
            values_y = np.diff(values_y) * framerate
        try:
            result = render_dot_plot(
                values_x, values_y,
                name_x=spec["name_x"], name_y=spec["name_y"],
                units_x=spec["units_x"], units_y=spec["units_y"],
            )
        except Exception as exc:
            warnings.append(f"Failed to render '{spec['title']}': {exc}")
            continue
        yield (spec["title"], result.figure)


def _iter_custom_angle_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any], warnings: List[str]
):
    custom = (config or {}).get("custom_calculations") or {}
    tpa = custom.get("three_point_angle") or {}
    output_col = str(tpa.get("output_column") or "ThreePointAngle")
    enabled = bool(tpa.get("enabled", False))

    if not enabled:
        return

    if output_col not in results_df.columns:
        warnings.append(f"Custom angle enabled but column missing: {output_col}")
        return

    y = pd.to_numeric(results_df[output_col], errors="coerce").to_numpy()
    x = list(range(len(y)))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", name=output_col))
    fig.update_layout(
        title=f"Custom Angle: {output_col}",
        xaxis_title="Frame",
        yaxis_title="Angle (deg)",
        template="plotly_white",
    )

    yield (f"Custom Angle: {output_col}", fig)


def _iter_fin_tail_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any], warnings: List[str]
):
    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_angle_and_distance_plot"):
        return
    required_cols = {
        "leftFinAngles": "LF_Angle",
        "rightFinAngles": "RF_Angle",
        "tailDistances": "Tail_Distance",
    }
    missing_cols = [
        col for col in required_cols.values()
        if col not in results_df.columns
    ]
    if missing_cols:
        warnings.append(
            f"Fin/tail plot skipped; missing columns: {', '.join(missing_cols)}."
        )
        return
    settings = dict(cfg.get("angle_and_distance_plot_settings") or {})
    settings["open_plot"] = False
    cfg["angle_and_distance_plot_settings"] = settings
    cfg["open_plots"] = False
    time_ranges = cfg.get("time_ranges") or []
    if not time_ranges and len(results_df) > 0:
        time_ranges = [(0, len(results_df) - 1)]
    calculated_values = {
        "leftFinAngles": results_df[required_cols["leftFinAngles"]].to_numpy(),
        "rightFinAngles": results_df[required_cols["rightFinAngles"]].to_numpy(),
        "tailDistances": results_df[required_cols["tailDistances"]].to_numpy(),
    }
    if "HeadYaw" in results_df.columns:
        calculated_values["headYaw"] = results_df["HeadYaw"].to_numpy()
    bundle = GraphDataBundle(
        time_ranges=[list(tr) for tr in time_ranges],
        input_values={},
        calculated_values=calculated_values,
        config=cfg,
        dataframe=results_df,
    )
    try:
        result = render_fin_tail(bundle, ctx=None)
    except Exception as exc:
        warnings.append(f"Fin/tail plot failed: {exc}")
        return
    warnings.extend(result.warnings)
    if result.figures:
        yield ("Fin Angles + Tail Distance", result.figures[0])
    else:
        warnings.append("Fin/tail plot produced no figures.")


def _iter_spine_graphs(
    results_df: pd.DataFrame,
    config: Dict[str, Any],
    parsed_points: Optional[Dict[str, Any]],
    warnings: List[str],
):
    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_spines"):
        return
    if parsed_points is None or "spine" not in parsed_points:
        warnings.append(
            "Spine plots skipped: parsed point coordinates are unavailable."
        )
        return
    if (
        "LF_Angle" not in results_df.columns
        or "RF_Angle" not in results_df.columns
    ):
        warnings.append("Spine plots skipped: missing LF_Angle/RF_Angle columns.")
        return
    spine_settings = dict(cfg.get("spine_plot_settings") or {})
    spine_settings["open_plot"] = False
    cfg["spine_plot_settings"] = spine_settings
    cfg["open_plots"] = False
    time_ranges = extract_time_ranges(cfg, results_df)
    bundle = GraphDataBundle(
        time_ranges=[list(tr) for tr in time_ranges],
        input_values={"spine": parsed_points["spine"]},
        calculated_values={
            "leftFinAngles": results_df["LF_Angle"].to_numpy(),
            "rightFinAngles": results_df["RF_Angle"].to_numpy(),
        },
        config=cfg,
        dataframe=results_df,
    )
    try:
        result = render_spines(bundle, ctx=None)
    except Exception as exc:
        warnings.append(f"Spine plot failed: {exc}")
        return
    warnings.extend(result.warnings)
    if not result.figures:
        warnings.append("Spine plot produced no figures.")
        return
    if result.mode == "by_bout":
        for idx, fig in enumerate(result.figures):
            yield (f"Spines Bout {idx}", fig)
    else:
        yield ("Spines Combined", result.figures[0])


def build_dot_plot_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    warnings: List[str] = []
    graphs: Dict[str, GraphSource] = {}
    for name, fig in _iter_dot_plot_graphs(results_df, config, warnings):
        graphs[name] = fig
    return graphs, warnings


def build_fin_tail_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    warnings: List[str] = []
    graphs: Dict[str, GraphSource] = {}
    for name, fig in _iter_fin_tail_graphs(results_df, config, warnings):
        graphs[name] = fig
    return graphs, warnings


def extract_time_ranges(config: Dict[str, Any], results_df: pd.DataFrame) -> List[List[int]]:
    cfg_ranges = (config or {}).get("time_ranges") or []
    if cfg_ranges:
        return [list(map(int, tr)) for tr in cfg_ranges]

    start_cols = [
        c for c in results_df.columns if c.startswith("timeRangeStart_")
    ]
    ranges: List[List[int]] = []
    for start_col in sorted(start_cols):
        suffix = start_col.split("timeRangeStart_", 1)[-1]
        end_col = f"timeRangeEnd_{suffix}"
        if end_col not in results_df.columns:
            continue
        start_val = pd.to_numeric(results_df[start_col].iloc[0], errors="coerce")
        end_val = pd.to_numeric(results_df[end_col].iloc[0], errors="coerce")
        if pd.isna(start_val) or pd.isna(end_val):
            continue
        start_idx = int(start_val)
        end_idx = int(end_val)
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx
        ranges.append([max(0, start_idx), max(0, end_idx)])

    if ranges:
        return ranges
    if len(results_df) > 0:
        return [[0, len(results_df) - 1]]
    return []


def build_spine_graphs(
    results_df: pd.DataFrame,
    config: Dict[str, Any],
    parsed_points: Optional[Dict[str, Any]],
) -> Tuple[Dict[str, GraphSource], List[str]]:
    warnings: List[str] = []
    graphs: Dict[str, GraphSource] = {}
    for name, fig in _iter_spine_graphs(
        results_df, config, parsed_points, warnings
    ):
        graphs[name] = fig
    return graphs, warnings


def build_head_plot_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    graphs: Dict[str, GraphSource] = {}
    warnings: List[str] = []

    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_head_plot"):
        return graphs, warnings

    if "HeadYaw" not in results_df.columns:
        warnings.append("Head plot skipped: missing HeadYaw column.")
        return graphs, warnings

    head_settings = dict(cfg.get("head_plot_settings") or {})
    head_settings["open_plot"] = False
    cfg["head_plot_settings"] = head_settings
    cfg["open_plots"] = False

    time_ranges = extract_time_ranges(cfg, results_df)

    calculated_values: Dict[str, Any] = {
        "headYaw": results_df["HeadYaw"].to_numpy(),
    }

    bundle = GraphDataBundle(
        time_ranges=[list(tr) for tr in time_ranges],
        input_values={},
        calculated_values=calculated_values,
        config=cfg,
        dataframe=results_df,
    )

    try:
        result = render_headplot(bundle, ctx=None)
    except Exception as exc:
        warnings.append(f"Head plot failed: {exc}")
        return graphs, warnings

    warnings.extend(result.warnings)
    if result.figures:
        graphs["Head Orientation"] = result.figures[0]
    else:
        warnings.append("Head plot produced no figures.")

    return graphs, warnings


def build_graphs_from_data(
    data: Optional[Dict[str, Any]],
    progress_callback: Callable[[int, int, str], None],
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> Tuple[Optional[Dict[str, GraphSource]], Optional[Dict[str, Any]]]:
    """
    Build Plotly/graph outputs from a calculation payload.
    Calls ``progress_callback(n, total, graph_name)`` for each graph.
    Returns (None, None) if invalid / empty.
    """
    if not data or not isinstance(data, dict):
        return None, None
    results_df = data.get("results_df")
    config = data.get("config")
    if not isinstance(results_df, pd.DataFrame) or not isinstance(config, dict):
        return None, None
    parsed_points = data.get("parsed_points")
    names = get_graph_names_to_build(data)
    total = len(names)
    if total == 0:
        return None, None
    warnings: List[str] = []
    graphs: Dict[str, GraphSource] = {}
    index = 0
    for name, fig in _iter_dot_plot_graphs(results_df, config, warnings):
        if is_cancelled is not None and is_cancelled():
            raise CalculationAborted()
        index += 1
        progress_callback(index, total, name)
        graphs[name] = fig
    for name, fig in _iter_fin_tail_graphs(results_df, config, warnings):
        if is_cancelled is not None and is_cancelled():
            raise CalculationAborted()
        index += 1
        progress_callback(index, total, name)
        graphs[name] = fig
    for name, fig in _iter_spine_graphs(
        results_df, config, parsed_points, warnings
    ):
        if is_cancelled is not None and is_cancelled():
            raise CalculationAborted()
        index += 1
        progress_callback(index, total, name)
        graphs[name] = fig
    head_graphs, head_warnings = build_head_plot_graphs(results_df, config)
    warnings.extend(head_warnings)
    for name, fig in head_graphs.items():
        if is_cancelled is not None and is_cancelled():
            raise CalculationAborted()
        index += 1
        progress_callback(index, total, name)
        graphs[name] = fig
    for name, fig in _iter_custom_angle_graphs(results_df, config, warnings):
        if is_cancelled is not None and is_cancelled():
            raise CalculationAborted()
        index += 1
        progress_callback(index, total, name)
        graphs[name] = fig

    return graphs, config


def save_to_html(
    fig: go.Figure,
    title: str,
    out_dir: Path,
    config: Dict[str, Any],
    session=None,
) -> None:
    try:
        fname = safe_filename(title) or "graph"
        html_path = out_dir / f"{fname}.html"
        png_path = out_dir / f"{fname}.png"

        pio.write_html(fig, file=str(html_path), include_plotlyjs=True, auto_open=False)

        try:
            png_bytes = pio.to_image(fig, format="png", scale=2)
            png_path.write_bytes(png_bytes)
        except Exception:
            png_path = None

        if session is not None:
            graph_asset = None
            if png_path is not None and png_path.exists():
                graph_asset = str(png_path)
            elif html_path.exists():
                graph_asset = str(html_path)
            if graph_asset is not None:
                session.addGraphToConfig(config["config_path"], graph_asset)
            session.save()
    except Exception as e:
        print(f"Could not save '{title}' as HTML: {e}")
