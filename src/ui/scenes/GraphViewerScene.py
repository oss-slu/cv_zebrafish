from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

import re
import numpy as np
import pandas as pd
from pathlib import Path
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import plotly.graph_objs as go
import plotly.io as pio

from src.core.graphs.loader_bundle import GraphDataBundle
from src.core.graphs.plots import render_dot_plot, render_fin_tail, render_headplot, render_spines

# Cross-correlation imports
from src.core.analysis.cross_correlation import (
    compute_cross_correlation_from_dataframe,
    get_available_signals,
)
from src.core.graphs.plots.crosscorr_plot import render_crosscorr_plot

from src.session import session
from src.app_platform.paths import images_dir, sessions_dir

FOLDER_ICON = images_dir() / "folder-black.svg"

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


class GraphViewerScene(QWidget):
    """
    Graph viewer with two tabs:
      1. Graphs - standard plots (dot, fin/tail, spine, head)
      2. Cross-Correlation - signal pair analysis
    """

    def __init__(self):
        super().__init__()

        self._graphs: Dict[str, GraphSource] = {}
        self._graphs_by_csv: Optional[Dict[str, Dict[str, GraphSource]]] = None
        self._csv_order: List[str] = []
        self._context_csv_id: Optional[str] = None
        self._context_config_path: Optional[str] = None
        self._context_csv_files: Optional[List[str]] = None
        self._context_selected_csv: Optional[str] = None
        self._out_dir: Optional[Path] = None
        self._current_name: Optional[str] = None
        self._original_pixmap: Optional[QPixmap] = None
        self._data = None
        self.current_session = None
        self._kaleido_available = _is_kaleido_available()

        # Cross-correlation state
        self._crosscorr_available = False
        self._crosscorr_signals = []
        self._current_crosscorr_fig = None
        self._current_df = None

        # Context banner
        self.context_icon = QLabel()
        self.context_icon.setFixedWidth(18)
        self.context_text = QLabel("")
        self.context_text.setWordWrap(True)
        self.context_text.setStyleSheet("color: #6c757d;")

        # CSV selector dropdown
        self.csv_combo = QComboBox()
        self.csv_combo.setVisible(False)
        self.csv_combo.currentIndexChanged.connect(self._on_csv_changed)

        # Graph list
        self.list = QListWidget()
        self.list.setMinimumWidth(240)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)

        # Image area for graphs
        self.image_label = QLabel("Select a graph on the left")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setWordWrap(True)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.image_label)

        # ---------------------------------------------------------------
        # Layout with tabs
        # ---------------------------------------------------------------
        context_row = QHBoxLayout()
        context_row.setContentsMargins(0, 0, 0, 0)
        context_row.setSpacing(8)
        context_row.addWidget(self.context_icon, 0, Qt.AlignLeft)
        context_row.addWidget(self.context_text, 1)

        context_widget = QWidget()
        context_widget.setLayout(context_row)

        # Tab widget
        self.tab_widget = QTabWidget()

        # Tab 1: Graphs
        graph_tab = QWidget()
        graph_layout = QHBoxLayout(graph_tab)
        graph_layout.setContentsMargins(0, 0, 0, 0)

        left_graph = QVBoxLayout()
        left_graph.addWidget(self.csv_combo)
        left_graph.addWidget(self.list, stretch=1)

        right_graph = QVBoxLayout()
        right_graph.addWidget(self.scroll, stretch=1)

        graph_layout.addLayout(left_graph)
        graph_layout.addLayout(right_graph, stretch=1)

        self.tab_widget.addTab(graph_tab, "Graphs")

        # Tab 2: Cross-Correlation
        crosscorr_tab = QWidget()
        crosscorr_layout = QVBoxLayout(crosscorr_tab)

        # Signal pair selection
        pair_row = QHBoxLayout()
        pair_row.addWidget(QLabel("Signal A:"))
        self.signal_a_combo = QComboBox()
        self.signal_a_combo.setMinimumWidth(150)
        pair_row.addWidget(self.signal_a_combo)

        pair_row.addWidget(QLabel("Signal B:"))
        self.signal_b_combo = QComboBox()
        self.signal_b_combo.setMinimumWidth(150)
        pair_row.addWidget(self.signal_b_combo)

        self.compute_crosscorr_btn = QPushButton("Compute Cross-Correlation")
        self.compute_crosscorr_btn.clicked.connect(self._compute_crosscorr)
        pair_row.addWidget(self.compute_crosscorr_btn)
        pair_row.addStretch()

        crosscorr_layout.addLayout(pair_row)

        # Cross-correlation display
        self.crosscorr_label = QLabel("Select two signals and click Compute.")
        self.crosscorr_label.setAlignment(Qt.AlignCenter)
        self.crosscorr_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.crosscorr_label.setWordWrap(True)

        self.crosscorr_scroll = QScrollArea()
        self.crosscorr_scroll.setWidgetResizable(True)
        self.crosscorr_scroll.setWidget(self.crosscorr_label)

        crosscorr_layout.addWidget(self.crosscorr_scroll, stretch=1)

        self.tab_widget.addTab(crosscorr_tab, "Cross-Correlation")
        self.tab_widget.setTabEnabled(1, False)  # disabled until data loads

        # Main layout
        right = QVBoxLayout()
        right.addWidget(context_widget)
        right.addWidget(self.tab_widget, stretch=1)

        outer = QVBoxLayout()
        outer.addLayout(right, stretch=1)
        self.setLayout(outer)

        self._show_empty_state("No graphs available.")
        self._refresh_context_banner()

    def set_context(self, csv_id: Optional[str], config_path: Optional[str], csv_files: Optional[List[str]] = None):
        self._context_csv_id = csv_id
        self._context_config_path = config_path
        self._context_csv_files = list(csv_files) if csv_files is not None else None
        self._context_selected_csv = csv_id
        self._refresh_context_banner()

    def _refresh_context_banner(self):
        csv_id = self._context_csv_id
        cfg = self._context_config_path
        config_name = Path(cfg).name if cfg else "(no config)"

        is_folder = False
        n_files = None
        if csv_id and self.current_session is not None:
            try:
                is_folder = bool(getattr(self.current_session, "is_folder_csv", lambda _p: False)(csv_id))
                if is_folder:
                    if self._context_csv_files is not None:
                        n_files = len(self._context_csv_files)
                    else:
                        n_files = len(self.current_session.get_folder_files(csv_id))
            except Exception:
                is_folder = False

        if is_folder:
            folder_name = Path(csv_id).name if csv_id else "(folder)"
            selected = self._context_selected_csv
            selected_name = Path(selected).name if selected else ""
            files_text = f"{n_files} files" if n_files is not None else ""
            if selected_name:
                text = f"{folder_name} ({files_text}) • {selected_name} • {config_name}" if files_text else f"{folder_name} • {selected_name} • {config_name}"
            else:
                text = f"{folder_name} ({files_text}) • {config_name}" if files_text else f"{folder_name} • {config_name}"
            self.context_icon.setPixmap(QIcon(str(FOLDER_ICON)).pixmap(16, 16))
            self.context_icon.setVisible(True)
            self.context_text.setText(text)
            return

        csv_name = Path(csv_id).name if csv_id else "(no csv)"
        self.context_icon.setVisible(False)
        self.context_text.setText(f"{csv_name} • {config_name}")

    def set_graphs(self, graphs: Dict[str, GraphSource], config: Dict[str, Any] = None):
        self._graphs_by_csv = None
        self._csv_order = []
        try:
            self.csv_combo.blockSignals(True)
            self.csv_combo.clear()
            self.csv_combo.setVisible(False)
            self.csv_combo.blockSignals(False)
        except Exception:
            pass
        self._graphs.clear()
        self._graphs.update(graphs)
        self.list.clear()
        self.list.addItems(list(self._graphs.keys()))
        self._context_selected_csv = self._context_csv_id
        self._refresh_context_banner()

        needs_kaleido = any(isinstance(src, go.Figure) for src in self._graphs.values())
        if needs_kaleido and not self._kaleido_available:
            self._show_empty_state(
                "Graphs are available, but cannot be displayed because Kaleido is not installed.\n"
                "Install it and restart the app:\n"
                "  pip install --upgrade kaleido\n"
                "or (conda):\n"
                "  conda install -c conda-forge python-kaleido"
            )
            return

        if self.list.count() > 0:
            self.list.setEnabled(True)
            self.list.setCurrentRow(0)
        else:
            self._show_empty_state("No graphs available.")

        if config and self.current_session is not None and self._out_dir is not None:
            for name, fig in self._graphs.items():
                save_to_html(fig, name, self._out_dir, config, self.current_session)

    def set_graphs_by_csv(self, graphs_by_csv: Dict[str, Dict[str, GraphSource]], config: Dict[str, Any] = None):
        self._graphs_by_csv = dict(graphs_by_csv or {})
        self._csv_order = list(self._graphs_by_csv.keys())

        if len(self._csv_order) <= 1:
            self.csv_combo.setVisible(False)
            only = self._csv_order[0] if self._csv_order else None
            self.set_graphs(self._graphs_by_csv.get(only, {}) if only else {}, config=config)
            return

        self.csv_combo.blockSignals(True)
        self.csv_combo.clear()
        for csv_path in self._csv_order:
            label = Path(csv_path).name if csv_path else "(unknown)"
            self.csv_combo.addItem(label, userData=csv_path)
        self.csv_combo.setVisible(True)
        self.csv_combo.setCurrentIndex(0)
        self.csv_combo.blockSignals(False)
        self._apply_selected_csv(config=config)

    def _on_csv_changed(self, _idx: int):
        self._apply_selected_csv(config=None)

    def _apply_selected_csv(self, config: Dict[str, Any] = None):
        if not self._graphs_by_csv:
            return
        csv_path = self.csv_combo.currentData()
        self._context_selected_csv = csv_path
        self._refresh_context_banner()
        graphs = self._graphs_by_csv.get(csv_path, {})
        self._graphs.clear()
        self._graphs.update(graphs)
        self.list.clear()
        self.list.addItems(list(self._graphs.keys()))
        if self.list.count() > 0:
            self.list.setEnabled(True)
            self.list.setCurrentRow(0)
        else:
            self._show_empty_state("No graphs available.")

    def save_folder_graphs(
        self,
        csv_folder_id: str,
        csv_files: List[str],
        config_path: str,
        graphs_by_csv: Dict[str, Dict[str, GraphSource]],
        config: Dict[str, Any],
    ) -> None:
        if self.current_session is None:
            return
        if not csv_folder_id or not config_path:
            return

        session_root = sessions_dir() / self.current_session.getName()
        base = session_root / "folders" / _safe_dirname(Path(csv_folder_id).name)
        base.mkdir(parents=True, exist_ok=True)

        used_csv_dirnames = set()
        csv_dir_for_path: Dict[str, Path] = {}
        for csv_path in (csv_files or []):
            stem = Path(csv_path).stem
            dname = _safe_dirname(stem)
            if dname in used_csv_dirnames:
                i = 2
                while f"{dname}_{i}" in used_csv_dirnames:
                    i += 1
                dname = f"{dname}_{i}"
            used_csv_dirnames.add(dname)
            out_dir = base / dname
            out_dir.mkdir(parents=True, exist_ok=True)
            csv_dir_for_path[csv_path] = out_dir

        for csv_path, graphs in (graphs_by_csv or {}).items():
            out_dir = csv_dir_for_path.get(csv_path)
            if out_dir is None:
                continue
            for title, src in (graphs or {}).items():
                if not isinstance(src, go.Figure):
                    continue
                try:
                    fname = _safe_filename(title) or "graph"
                    html_path = out_dir / f"{fname}.html"
                    png_path = out_dir / f"{fname}.png"

                    pio.write_html(src, file=str(html_path), include_plotlyjs="cdn", auto_open=False)
                    wrote_png = False
                    if _is_kaleido_available():
                        try:
                            png_bytes = pio.to_image(src, format="png", scale=2)
                            png_path.write_bytes(png_bytes)
                            wrote_png = True
                        except Exception:
                            wrote_png = False

                    if wrote_png and png_path.exists():
                        self.current_session.addFolderGraph(csv_folder_id, config_path, csv_path, str(png_path))
                    if html_path.exists():
                        self.current_session.addFolderGraph(csv_folder_id, config_path, csv_path, str(html_path))
                except Exception:
                    continue

        try:
            self.current_session.save()
        except Exception:
            pass

    def add_graph(self, name: str, graph: GraphSource):
        new_item = name not in self._graphs
        self._graphs[name] = graph
        if new_item:
            self.list.addItem(name)
            if self.list.count() == 1:
                self.list.setEnabled(True)
                self.list.setCurrentRow(0)

    def set_data(self, data):
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

        # Enable cross-correlation
        if isinstance(results_df, pd.DataFrame):
            self._enable_crosscorr(results_df)

    def build_graphs_with_progress(self, data, progress_callback):
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
            index += 1
            progress_callback(index, total, name)
            graphs[name] = fig
        for name, fig in _iter_fin_tail_graphs(results_df, config, warnings):
            index += 1
            progress_callback(index, total, name)
            graphs[name] = fig
        for name, fig in _iter_spine_graphs(results_df, config, parsed_points, warnings):
            index += 1
            progress_callback(index, total, name)
            graphs[name] = fig
        head_graphs, head_warnings = build_head_plot_graphs(results_df, config)
        warnings.extend(head_warnings)
        for name, fig in head_graphs.items():
            index += 1
            progress_callback(index, total, name)
            graphs[name] = fig
        return graphs, config

    # ------------------------------------------------------------------
    # Cross-correlation support
    # ------------------------------------------------------------------

    def _enable_crosscorr(self, df: pd.DataFrame):
        try:
            signals = get_available_signals(df)
            if len(signals) < 2:
                self._crosscorr_available = False
                self.tab_widget.setTabEnabled(1, False)
                return

            self._crosscorr_available = True
            self._crosscorr_signals = signals
            self._current_df = df

            self.signal_a_combo.blockSignals(True)
            self.signal_b_combo.blockSignals(True)

            self.signal_a_combo.clear()
            self.signal_b_combo.clear()

            self.signal_a_combo.addItems(signals)
            self.signal_b_combo.addItems(signals)

            if len(signals) >= 2:
                self.signal_a_combo.setCurrentIndex(0)
                self.signal_b_combo.setCurrentIndex(1)

            self.signal_a_combo.blockSignals(False)
            self.signal_b_combo.blockSignals(False)

            self.tab_widget.setTabEnabled(1, True)

        except Exception as e:
            print(f"[GraphViewerScene] Could not enable cross-correlation: {e}")
            self._crosscorr_available = False
            self.tab_widget.setTabEnabled(1, False)

    def _compute_crosscorr(self):
        if not self._crosscorr_available:
            self.crosscorr_label.setText("Cross-correlation not available for this dataset.")
            return

        signal_a = self.signal_a_combo.currentText()
        signal_b = self.signal_b_combo.currentText()

        if not signal_a or not signal_b:
            self.crosscorr_label.setText("Please select both signals.")
            return

        if signal_a == signal_b:
            self.crosscorr_label.setText("Please select two different signals.")
            return

        try:
            df = self._current_df
            if df is None:
                self.crosscorr_label.setText("No data available.")
                return

            result = compute_cross_correlation_from_dataframe(df, signal_a, signal_b)

            fig = render_crosscorr_plot(
                lags=result.lags.tolist(),
                correlations=result.correlations.tolist(),
                signal_a_name=signal_a,
                signal_b_name=signal_b,
                peak_lag=result.peak_lag,
                peak_correlation=result.peak_correlation,
            )

            pix = self._figure_to_pixmap(fig)
            if pix and not pix.isNull():
                self._current_crosscorr_pixmap = pix
                self._update_crosscorr_pixmap()
                self.crosscorr_label.setText("")
            else:
                self.crosscorr_label.setText("Could not render cross-correlation plot.")

        except Exception as e:
            self.crosscorr_label.setText(f"Error computing cross-correlation:\n{str(e)}")
            print(f"[GraphViewerScene] Cross-correlation error: {e}")

    def _update_crosscorr_pixmap(self):
        if not hasattr(self, "_current_crosscorr_pixmap") or self._current_crosscorr_pixmap is None:
            return

        viewport_size = self.crosscorr_scroll.viewport().size()
        target_w = max(50, viewport_size.width() - 16)
        scaled = self._current_crosscorr_pixmap.scaledToWidth(target_w, Qt.SmoothTransformation)
        self.crosscorr_label.setPixmap(scaled)
        self.crosscorr_label.setText("")

    # ------------------------------------------------------------------
    # Internal functions
    # ------------------------------------------------------------------

    def _on_selection_changed(self):
        items = self.list.selectedItems()
        if not items:
            if self.list.count() > 0:
                self.list.setCurrentRow(0)
            else:
                self._show_empty_state("No graphs available.")
            return
        self._current_name = items[0].text()
        self._show_graph(self._current_name)

    def _show_graph(self, name: str):
        source = self._graphs.get(name)
        if source is None:
            self._show_empty_state(f"Missing graph: {name}")
            return

        pix: Optional[QPixmap] = None
        if isinstance(source, go.Figure):
            pix = self._figure_to_pixmap(source)
        else:
            try:
                pix = QPixmap(str(source))
            except Exception:
                pix = None

        if pix is None or pix.isNull():
            self._show_empty_state("Unable to render this graph as a static image.")
            return

        self._original_pixmap = pix
        self._update_scaled_pixmap()
        self.image_label.setText("")
        self.list.setEnabled(True)

    def _set_message(self, text: str):
        self._original_pixmap = None
        self.image_label.setText(text)
        self.image_label.setPixmap(QPixmap())

    def _show_empty_state(self, text: str = "No graphs available."):
        self._set_message(text)
        self.list.setEnabled(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._original_pixmap:
            self._update_scaled_pixmap()

    def load_session(self, session):
        self.current_session = session
        try:
            csv_id = getattr(self.current_session, "last_csv_path", None)
            cfg = getattr(self.current_session, "last_config_path", None)
            csv_files = None
            if csv_id and getattr(self.current_session, "is_folder_csv", lambda _p: False)(csv_id):
                csv_files = self.current_session.get_folder_files(csv_id)
            self.set_context(csv_id=csv_id, config_path=cfg, csv_files=csv_files)
        except Exception:
            self._refresh_context_banner()

        self._out_dir = sessions_dir() / (self.current_session.getName())
        self._out_dir.mkdir(parents=True, exist_ok=True)

        try:
            last_csv_id = getattr(self.current_session, "last_csv_path", None)
            last_cfg = getattr(self.current_session, "last_config_path", None)
            if last_csv_id and last_cfg and getattr(self.current_session, "is_folder_csv", lambda _p: False)(last_csv_id):
                per_csv_assets = getattr(self.current_session, "getFolderGraphs", lambda *_a, **_k: {})(last_csv_id, last_cfg)
                if per_csv_assets:
                    graphs_by_csv: Dict[str, Dict[str, GraphSource]] = {}
                    for csv_file, assets in per_csv_assets.items():
                        g: Dict[str, GraphSource] = {}
                        for a in assets or []:
                            try:
                                p = Path(a)
                            except Exception:
                                continue
                            if p.suffix.lower() != ".png" or not p.exists():
                                continue
                            title = p.stem.replace("_", " ").strip() or p.name
                            if title not in g:
                                g[title] = p
                        if g:
                            graphs_by_csv[csv_file] = g

                    if graphs_by_csv:
                        self.set_graphs_by_csv(graphs_by_csv, config=None)
                        return
        except Exception:
            pass

        restored_graphs = self._load_saved_graphs_from_session()
        if restored_graphs:
            self.set_graphs(restored_graphs)
        else:
            self._show_empty_state("No saved graphs yet for this session.")

    def has_graphs(self) -> bool:
        return bool(self._graphs)

    def _update_scaled_pixmap(self):
        if not self._original_pixmap:
            return
        viewport_size: QSize = self.scroll.viewport().size()
        target_w = max(50, viewport_size.width() - 16)
        scaled = self._original_pixmap.scaledToWidth(target_w, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")

    def _figure_to_pixmap(self, fig: go.Figure) -> Optional[QPixmap]:
        if not self._kaleido_available:
            self._show_empty_state(
                "Cannot render graphs because Kaleido is not installed.\n"
                "Install it and restart the app:\n"
                "  pip install --upgrade kaleido\n"
                "or (conda):\n"
                "  conda install -c conda-forge python-kaleido"
            )
            return None
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

    def _load_saved_graphs_from_session(self) -> Dict[str, GraphSource]:
        if not self.current_session:
            return {}

        graphs: Dict[str, GraphSource] = {}
        seen_paths = set()
        session_dir = sessions_dir() / self.current_session.getName()

        try:
            saved = self.current_session.getAllGraphs()
        except Exception:
            saved = []

        def _unique_name(base: str) -> str:
            if base not in graphs:
                return base
            i = 2
            while f"{base} ({i})" in graphs:
                i += 1
            return f"{base} ({i})"

        for p in saved:
            try:
                pp = Path(p)
            except Exception:
                continue
            try:
                key = str(pp.resolve())
            except Exception:
                key = str(pp)
            if key in seen_paths:
                continue
            if pp.suffix.lower() != ".png" or not pp.exists():
                continue
            title = pp.stem.replace("_", " ").strip() or pp.name
            graphs[_unique_name(title)] = pp
            seen_paths.add(key)

        if graphs:
            return graphs

        if not session_dir.exists():
            return graphs
        for png_file in session_dir.rglob("*.png"):
            try:
                key = str(png_file.resolve())
            except Exception:
                key = str(png_file)
            if key in seen_paths:
                continue
            title = png_file.stem.replace("_", " ").strip() or png_file.name
            graphs[_unique_name(title)] = png_file
            seen_paths.add(key)

        return graphs


# ---------------------------------------------------------------------------
# Helpers (unchanged)
# ---------------------------------------------------------------------------

def _as_numeric_array(series: pd.Series) -> np.ndarray:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.to_numpy()


def _safe_filename(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", title).strip("_")


def _safe_dirname(name: str) -> str:
    return _safe_filename(name) or "item"


def _is_kaleido_available() -> bool:
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
            missing_cols = [c for c in (spec["x_col"], spec["y_col"]) if c not in results_df.columns]
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
            time_ranges = _extract_time_ranges(config, results_df)
            spine_settings = (config or {}).get("spine_plot_settings") or {}
            split_by_bout = bool(spine_settings.get("split_plots_by_bout", True))
            if split_by_bout and time_ranges:
                names.extend(f"Spines Bout {i}" for i in range(len(time_ranges)))
            elif not split_by_bout or not time_ranges:
                names.append("Spines Combined")

    if shown_outputs.get("show_head_plot") and "HeadYaw" in results_df.columns:
        names.append("Head Orientation")

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

    any_flag_enabled = any(shown_outputs.get(spec["flag"], False) for spec in DOT_PLOT_SPECS)
    if not any_flag_enabled:
        warnings.append("No dot plot flags are enabled in the config.")
        return

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
                values_x, values_y,
                name_x=spec["name_x"], name_y=spec["name_y"],
                units_x=spec["units_x"], units_y=spec["units_y"],
            )
        except Exception as exc:
            warnings.append(f"Failed to render '{spec['title']}': {exc}")
            continue
        yield (spec["title"], result.figure)


def _iter_fin_tail_graphs(
    results_df: pd.DataFrame, config: Dict[str, Any], warnings: List[str]
):
    cfg = dict(config or {})
    shown_outputs = cfg.get("shown_outputs") or {}
    if not shown_outputs.get("show_angle_and_distance_plot"):
        return
    required_cols = {"leftFinAngles": "LF_Angle", "rightFinAngles": "RF_Angle", "tailDistances": "Tail_Distance"}
    missing_cols = [col for col in required_cols.values() if col not in results_df.columns]
    if missing_cols:
        warnings.append(f"Fin/tail plot skipped; missing columns: {', '.join(missing_cols)}.")
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
        warnings.append("Spine plots skipped: parsed point coordinates are unavailable.")
        return
    if "LF_Angle" not in results_df.columns or "RF_Angle" not in results_df.columns:
        warnings.append("Spine plots skipped: missing LF_Angle/RF_Angle columns.")
        return
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


def _extract_time_ranges(config: Dict[str, Any], results_df: pd.DataFrame) -> List[List[int]]:
    cfg_ranges = (config or {}).get("time_ranges") or []
    if cfg_ranges:
        return [list(map(int, tr)) for tr in cfg_ranges]

    start_cols = [c for c in results_df.columns if c.startswith("timeRangeStart_")]
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
    results_df: pd.DataFrame, config: Dict[str, Any], parsed_points: Optional[Dict[str, Any]]
) -> Tuple[Dict[str, GraphSource], List[str]]:
    warnings: List[str] = []
    graphs: Dict[str, GraphSource] = {}
    for name, fig in _iter_spine_graphs(results_df, config, parsed_points, warnings):
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
    try:
        fname = _safe_filename(title) or "graph"
        html_path = out_dir / f"{fname}.html"
        png_path = out_dir / f"{fname}.png"

        pio.write_html(fig, file=str(html_path), include_plotlyjs="cdn", auto_open=False)

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



def _safe_dirname(name: str) -> str:
    """Filesystem-safe directory name (no extension)."""
    return _safe_filename(name) or "item"


def _is_kaleido_available() -> bool:
    """
    Best-effort check for Kaleido availability.
    Plotly's PNG export requires Kaleido; if it's missing, to_image() raises.
    """
    try:
        import kaleido  # noqa: F401
    except Exception:
        return False
    return True
