from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import re
import numpy as np
import pandas as pd
from pathlib import Path
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import plotly.graph_objs as go
import plotly.io as pio

from src.core.graphs.loader_bundle import GraphDataBundle
from src.core.graphs.plots import render_dot_plot, render_fin_tail, render_spines

from src.session import session
from src.app_platform.paths import sessions_dir

GraphSource = go.Figure

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

class GraphViewerScene(QWidget):
    """
    Simple static graph viewer:
      - Left: list of graph names
      - Right: image area (QLabel) that displays the selected graph

    Public functions:
      set_graphs({ name: figure })
      add_graph(name, figure)
      set_data({ results of calculations }) will be called at button press

    Accepted source:
      - plotly.graph_objs.Figure  (converted to PNG via kaleido)
    """

    def __init__(self):
        super().__init__()

        self._graphs: Dict[str, GraphSource] = {}
        self._out_dir: Optional[Path] = None
        self._current_name: Optional[str] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._data = None
        self.current_session = None

        # Sidebar
        self.list = QListWidget()
        self.list.setMinimumWidth(240)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)

        # Image area (inside a scroll area for large images)
        self.image_label = QLabel("Select a graph on the left")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setWordWrap(True)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.image_label)

        # Layout
        
        right = QVBoxLayout()
        right.addWidget(self.scroll)

        layout = QHBoxLayout()
        layout.addWidget(self.list)
        layout.addLayout(right)
        self.setLayout(layout)

        # Start in an empty state
        self._show_empty_state("No graphs available.")

    # Public functions to call to construct the viewer
    def set_graphs(self, graphs: Dict[str, GraphSource], config: Dict[str, Any] = None):
        """Replace all graphs."""
        self._graphs.clear()
        self._graphs.update(graphs)
        self.list.clear()
        self.list.addItems(list(self._graphs.keys()))
        if self.list.count() > 0:
            self.list.setEnabled(True)
            self.list.setCurrentRow(0)
        else:
            self._show_empty_state("No graphs available.")

        # saves graphs to session
        if config and self.current_session is not None and self._out_dir is not None:
            for name, fig in self._graphs.items():
                save_to_html(fig, name, self._out_dir, config, self.current_session)

    def add_graph(self, name: str, graph: GraphSource):
        """Add or replace a single graph."""
        new_item = name not in self._graphs
        self._graphs[name] = graph
        if new_item:
            self.list.addItem(name)
            if self.list.count() == 1:
                self.list.setEnabled(True)
                self.list.setCurrentRow(0)

    def set_data(self, data):
        """Consume calculation payload and build the requested dot plots."""
        self._data = data
        self._graphs.clear()
        self.list.clear()

        if not data:
            self._show_empty_state("No calculation output to visualize.")
            return

        if not isinstance(data, dict):
            self._show_empty_state("Unexpected data payload; expected a dict.")
            return

        results_df = data.get("results_df")
        config = data.get("config")

        if not isinstance(results_df, pd.DataFrame):
            self._show_empty_state("Dot plots require a pandas DataFrame payload.")
            return
        if not isinstance(config, dict):
            self._show_empty_state("Missing config dictionary; cannot determine requested plots.")
            return

        graphs: Dict[str, GraphSource] = {}
        warnings: List[str] = []

        dot_graphs, dot_warnings = build_dot_plot_graphs(results_df, config)
        graphs.update(dot_graphs)
        warnings.extend(dot_warnings)

        fin_graphs, fin_warnings = build_fin_tail_graphs(results_df, config)
        graphs.update(fin_graphs)
        warnings.extend(fin_warnings)

        spine_graphs, spine_warnings = build_spine_graphs(results_df, config, data.get("parsed_points"))
        graphs.update(spine_graphs)
        warnings.extend(spine_warnings)

        head_graphs, head_warnings = build_head_plot_graphs(results_df, config)
        graphs.update(head_graphs)
        warnings.extend(head_warnings)

        tooltip = "\n".join(warnings) if warnings else ""
        self.list.setToolTip(tooltip)
        self.image_label.setToolTip(tooltip)

        if not graphs:
            message = warnings[0] if warnings else "No dot plots were requested in the config."
            self._show_empty_state(message)
            return

        self.set_graphs(graphs, config=config)

    # Internal functions
    def _on_selection_changed(self):
        items = self.list.selectedItems()
        if not items:
            # If nothing is selected but we have items, pick the first; otherwise show empty state
            if self.list.count() > 0:
                self.list.setCurrentRow(0)
            else:
                self._show_empty_state("No graphs available.")
            return
        self._current_name = items[0].text()
        self._show_graph(self._current_name)

    def _show_graph(self, name: str):
        fig = self._graphs.get(name)
        if fig is None:
            self._show_empty_state(f"Missing graph: {name}")
            return

        pix = self._figure_to_pixmap(fig)
        if pix is None or pix.isNull():
            self._show_empty_state("Unable to render this graph as a static image.")
            return

        self._original_pixmap = pix
        self._update_scaled_pixmap()
        self.image_label.setText("")   # ensure no message overlays
        self.list.setEnabled(True)     # we have something to show

    def _set_message(self, text: str):
        self._original_pixmap = None
        self.image_label.setText(text)
        self.image_label.setPixmap(QPixmap())

    def _show_empty_state(self, text: str = "No graphs available."):
        """Unified empty/error state: clear image, center message, disable list."""
        self._set_message(text)
        self.list.setEnabled(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._original_pixmap:
            self._update_scaled_pixmap()

    def load_session(self, session):
        """Load previous session data."""
        self.current_session = session

        # creates directory for saving graphs if it doesn't exist
        self._out_dir = sessions_dir() / (self.current_session.getName())
        self._out_dir.mkdir(parents=True, exist_ok=True)

        # Restore previously saved HTML graphs
        restored_graphs = self._load_html_graphs_from_session()
        if restored_graphs:
            self.set_graphs(restored_graphs)
        else:
            self._show_empty_state("No saved graphs yet for this session.")

    def _update_scaled_pixmap(self):
        """Scale the original pixmap to fit the viewport width while keeping aspect ratio."""
        if not self._original_pixmap:
            return

        # Fit to scroll viewport size (minus a small margin)
        viewport_size: QSize = self.scroll.viewport().size()
        target_w = max(50, viewport_size.width() - 16)
        scaled = self._original_pixmap.scaledToWidth(target_w, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")  # ensure no text overlays

    def _figure_to_pixmap(self, fig: go.Figure) -> Optional[QPixmap]:
        """
        Convert a Plotly Figure into a QPixmap (static PNG).
        Requires kaleido for PNG export.
        """
        try:
            png_bytes = pio.to_image(fig, format="png", scale=2)
            pix = QPixmap()
            pix.loadFromData(png_bytes)
            return pix
        except Exception as e:
            self._show_empty_state(
                "Failed to render Plotly Figure as a static image.\n"
                "Ensure 'kaleido' is installed (pip install kaleido).\n"
                f"Error: {e}"
            )
            return None
        
    def _load_html_graphs_from_session(self):
        """Load previously saved HTML graphs from the session directory (placeholder)."""
        if not self.current_session:
            return {}

        graphs = {}
        session_dir = sessions_dir() / self.current_session.getName()
        if not session_dir.exists():
            return graphs

        # Recursive glob for all .html files
        for html_file in session_dir.rglob("*.html"):
            try:
                # Use relative path from session dir for uniqueness
                relative_name = html_file.relative_to(session_dir).with_suffix("").as_posix()
                
                # graphs[relative_name] = str(html_file) 
                # just store path as placeholder. this should be replaced with actual loading logic when pyqt webengine is used
                # and the app is capable of rendering html files directly.
            except Exception as e:
                print(f"Could not load graph {html_file}: {e}")

        return graphs

def _as_numeric_array(series: pd.Series) -> np.ndarray:
    """Convert a pandas Series to a numeric numpy array, coercing failures to NaN."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.to_numpy()

def _safe_filename(title: str) -> str:
    """Make a filesystem-safe filename from a title (keeps extension to add later)."""
    # Replace any character not in this set with underscore
    return re.sub(r"[^A-Za-z0-9._-]", "_", title).strip("_")

def build_dot_plot_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    """
    Build all requested dot plot figures based on the config flags.

    Returns the generated figures and any warnings explaining skipped plots.
    """
    graphs: Dict[str, GraphSource] = {}
    warnings: List[str] = []

    shown_outputs = (config or {}).get("shown_outputs") or {}
    video_params = (config or {}).get("video_parameters") or {}
    framerate = video_params.get("recorded_framerate")

    if results_df.shape[0] == 0:
        warnings.append("The calculation DataFrame is empty; nothing to plot.")
        return graphs, warnings

    any_flag_enabled = any(shown_outputs.get(spec["flag"], False) for spec in DOT_PLOT_SPECS)
    if not any_flag_enabled:
        warnings.append("No dot plot flags are enabled in the config.")
        return graphs, warnings

    for spec in DOT_PLOT_SPECS:
        if not shown_outputs.get(spec["flag"], False):
            continue

        missing_cols = [col for col in (spec["x_col"], spec["y_col"]) if col not in results_df.columns]
        if missing_cols:
            warnings.append(
                f"Skipping '{spec['title']}' because columns {', '.join(missing_cols)} are missing."
            )
            continue

        values_x = _as_numeric_array(results_df[spec["x_col"]])
        values_y = _as_numeric_array(results_df[spec["y_col"]])

        if spec["moving"]:
            if framerate is None:
                warnings.append(
                    f"Skipping '{spec['title']}' because 'video_parameters.recorded_framerate' is missing."
                )
                continue
            if len(values_x) < 2 or len(values_y) < 2:
                warnings.append(
                    f"Skipping '{spec['title']}' because at least two frames are required."
                )
                continue
            values_x = np.diff(values_x) * framerate
            values_y = np.diff(values_y) * framerate

        try:
            result = render_dot_plot(
                values_x,
                values_y,
                name_x=spec["name_x"],
                name_y=spec["name_y"],
                units_x=spec["units_x"],
                units_y=spec["units_y"],
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            warnings.append(f"Failed to render '{spec['title']}': {exc}")
            continue
            
        graphs[spec["title"]] = result.figure

    return graphs, warnings

def build_fin_tail_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    """
    Build the fin/tail timeline plot requested by the config flag.
    Uses the modular render_fin_tail plotter with an in-memory bundle.
    """
    graphs: Dict[str, GraphSource] = {}
    warnings: List[str] = []

    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_angle_and_distance_plot"):
        return graphs, warnings

    required_cols = {
        "leftFinAngles": "LF_Angle",
        "rightFinAngles": "RF_Angle",
        "tailDistances": "Tail_Distance",
    }
    missing_cols = [col for col in required_cols.values() if col not in results_df.columns]
    if missing_cols:
        warnings.append(f"Fin/tail plot skipped; missing columns: {', '.join(missing_cols)}.")
        return graphs, warnings

    # Prevent external plot windows from opening in the GUI.
    settings = cfg.get("angle_and_distance_plot_settings") or {}
    settings = dict(settings)
    settings["open_plot"] = False
    cfg["angle_and_distance_plot_settings"] = settings
    cfg["open_plots"] = False

    # Build a minimal bundle for the plotter.
    time_ranges = cfg.get("time_ranges") or []
    if not time_ranges and len(results_df) > 0:
        time_ranges = [(0, len(results_df) - 1)]

    calculated_values: Dict[str, Any] = {
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
        return graphs, warnings

    warnings.extend(result.warnings)
    if result.figures:
        graphs["Fin Angles + Tail Distance"] = result.figures[0]
    else:
        warnings.append("Fin/tail plot produced no figures.")

    return graphs, warnings

def _extract_time_ranges(config: Dict[str, Any], results_df: pd.DataFrame) -> List[List[int]]:
    """Derive time ranges from config or DataFrame columns."""
    cfg_ranges = (config or {}).get("time_ranges") or []
    if cfg_ranges:
        return [list(map(int, tr)) for tr in cfg_ranges]

    start_cols = [c for c in results_df.columns if c.startswith("timeRangeStart_")]
    end_cols = [c for c in results_df.columns if c.startswith("timeRangeEnd_")]
    ranges: List[List[int]] = []
def build_spine_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any], parsed_points: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    """
    Build spine snapshot plots using the modular render_spines plotter.
    Requires parsed_points (spine coordinates) plus the calculation DataFrame for angles.
    """
    graphs: Dict[str, GraphSource] = {}
    warnings: List[str] = []

    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_spines"):
        return graphs, warnings

    if parsed_points is None or "spine" not in parsed_points:
        warnings.append("Spine plots skipped: parsed point coordinates are unavailable.")
        return graphs, warnings

    if "LF_Angle" not in results_df.columns or "RF_Angle" not in results_df.columns:
        warnings.append("Spine plots skipped: missing LF_Angle/RF_Angle columns.")
        return graphs, warnings

    # Prevent external plot windows from opening in the GUI.
    spine_settings = dict(cfg.get("spine_plot_settings") or {})
    spine_settings["open_plot"] = False
    cfg["spine_plot_settings"] = spine_settings
    cfg["open_plots"] = False

    time_ranges = _extract_time_ranges(cfg, results_df)

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
        return graphs, warnings

    warnings.extend(result.warnings)
    if not result.figures:
        warnings.append("Spine plot produced no figures.")
        return graphs, warnings

    if result.mode == "by_bout":
        for idx, fig in enumerate(result.figures):
            graphs[f"Spines Bout {idx}"] = fig
    else:
        graphs["Spines Combined"] = result.figures[0]

    return graphs, warnings


def build_head_plot_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    """
    Build the head orientation (head yaw) plot using the modular render_headplot plotter.
    """
    graphs: Dict[str, GraphSource] = {}
    warnings: List[str] = []

    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_head_plot"):
        return graphs, warnings

    if "HeadYaw" not in results_df.columns:
        warnings.append("Head plot skipped: missing HeadYaw column.")
        return graphs, warnings

    # Prevent external plot windows from opening in the GUI
    head_settings = dict(cfg.get("head_plot_settings") or {})
    head_settings["open_plot"] = False
    cfg["head_plot_settings"] = head_settings
    cfg["open_plots"] = False

    time_ranges = _extract_time_ranges(cfg, results_df)

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
        from src.core.graphs.plots import render_headplot
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


def save_to_html(fig: go.Figure, title: str, out_dir: Path, config: Dict[str, Any], session=None) -> None:
    """
    Save a Plotly figure as an interactive HTML file in the given directory (best-effort).
    Uses CDN for plotly JS to keep file size smaller and consistent.
    """
    try:
        fname = _safe_filename(title) or "graph"

        html_path = out_dir / f"{fname}.html"
                
        # Use CDN for plotly JS to keep file size smaller and consistent
        pio.write_html(fig, file=str(html_path), include_plotlyjs="cdn", auto_open=False)

        if session is not None:
            session.addGraphToConfig(config["config_path"], str(html_path))
            session.save()
    except Exception as e:
        print(f"Could not save '{title}' as HTML: {e}")
