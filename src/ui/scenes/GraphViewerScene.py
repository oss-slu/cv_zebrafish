from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
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

from src.core.graphs.plots import render_dot_plot
from src.core.graphs.plots.headplot import plot_head

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

HEAD_PLOT_SPEC: Dict[str, Any] = {
    "flag": "show_head_plot",
    "title_prefix": "Head Plot",
    "required_df_cols": ["HeadYaw", "LF_Angle", "RF_Angle"],
    "settings_key": "head_plot_settings",
    "default_settings": {
        "plot_draw_offset": 15,
        "ignore_synchronized_fin_peaks": True,
        "sync_fin_peaks_range": 3,
        "fin_peaks_for_right_fin": False,
        "split_plots_by_bout": True,
    },
}

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
        self._current_name: Optional[str] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._data = None

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
    def set_graphs(self, graphs: Dict[str, GraphSource]):
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
        """Consume calculation payload and build the requested dot plots and head plots."""
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
        csv_path = data.get("csv_path")

        if not isinstance(results_df, pd.DataFrame):
            self._show_empty_state("Graphs require a pandas DataFrame payload.")
            return
        if not isinstance(config, dict):
            self._show_empty_state("Missing config dictionary; cannot determine requested plots.")
            return

        all_graphs = {}
        all_warnings = []

        # Build dot plots
        dot_graphs, dot_warnings = build_dot_plot_graphs(results_df, config)
        all_graphs.update(dot_graphs)
        all_warnings.extend(dot_warnings)

        # Build head plots (extracts data directly from DataFrame)
        head_graphs, head_warnings = build_head_plot_graphs(results_df, config)
        all_graphs.update(head_graphs)
        all_warnings.extend(head_warnings)

        tooltip = "\n".join(all_warnings) if all_warnings else ""
        self.list.setToolTip(tooltip)
        self.image_label.setToolTip(tooltip)

        if not all_graphs:
            message = all_warnings[0] if all_warnings else "No plots were requested in the config."
            self._show_empty_state(message)
            return

        self.set_graphs(all_graphs)

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


def _as_numeric_array(series: pd.Series) -> np.ndarray:
    """Convert a pandas Series to a numeric numpy array, coercing failures to NaN."""
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.to_numpy()


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


def build_head_plot_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    """
    Build head plot figures if requested in config flags.
    Extracts data directly from the DataFrame.

    Returns the generated figures and any warnings explaining skipped plots.
    """
    graphs: Dict[str, GraphSource] = {}
    warnings: List[str] = []

    shown_outputs = (config or {}).get("shown_outputs") or {}
    
    # Check if head plot is requested
    if not shown_outputs.get(HEAD_PLOT_SPEC["flag"], False):
        return graphs, warnings

    # Validate DataFrame has required columns
    missing_cols = [col for col in HEAD_PLOT_SPEC["required_df_cols"] if col not in results_df.columns]
    if missing_cols:
        warnings.append(
            f"Head plot skipped: missing DataFrame columns {', '.join(missing_cols)}."
        )
        return graphs, warnings

    if results_df.shape[0] == 0:
        warnings.append("Head plot skipped: DataFrame is empty.")
        return graphs, warnings

    # Extract data directly from DataFrame (no loader needed!)
    head_yaw = _as_numeric_array(results_df["HeadYaw"])
    left_fin_angles = _as_numeric_array(results_df["LF_Angle"])
    right_fin_angles = _as_numeric_array(results_df["RF_Angle"])

    # Get time ranges from config or use full dataset
    time_ranges = config.get("time_ranges")
    if not time_ranges:
        # Default: treat entire dataset as one bout
        time_ranges = [(0, len(head_yaw) - 1)]

    # Get head plot settings from config
    head_settings = config.get(HEAD_PLOT_SPEC["settings_key"], {})
    head_settings = {**HEAD_PLOT_SPEC["default_settings"], **head_settings}

    # Get cutoffs
    cutoffs = config.get("graph_cutoffs", {})
    if "left_fin_angle" not in cutoffs:
        cutoffs["left_fin_angle"] = 10
    if "right_fin_angle" not in cutoffs:
        cutoffs["right_fin_angle"] = 10

    # Generate head plot (ctx=None means no file output, GUI-only)
    try:
        result = plot_head(
            head_yaw=head_yaw,
            left_fin_values=left_fin_angles,
            right_fin_values=right_fin_angles,
            time_ranges=time_ranges,
            head_settings=head_settings,
            cutoffs=cutoffs,
            ctx=None,  # No file output for GUI
            open_plot=False,
        )
    except Exception as exc:
        warnings.append(f"Failed to generate head plot: {exc}")
        return graphs, warnings

    # Add figures to graphs dict
    # If split by bout, we get multiple figures with labels
    # Otherwise, we get a single figure
    if result.labels:
        for fig, label in zip(result.figures, result.labels):
            graphs[f"{HEAD_PLOT_SPEC['title_prefix']}: {label}"] = fig
    elif result.figures:
        graphs[HEAD_PLOT_SPEC["title_prefix"]] = result.figures[0]

    return graphs, warnings
