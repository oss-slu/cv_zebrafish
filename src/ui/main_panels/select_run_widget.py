from __future__ import annotations

import json
import threading
from os import path
from pathlib import Path

from PyQt5.QtCore import QObject, QEvent, QThread, Qt, QSize, pyqtSignal, pyqtSlot
from typing import Any
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser

from ui.components.branding import view_output_tool_icon
from ui.components.scene_help import create_scene_help_button

from src.app_platform.paths import default_sample_config, default_sample_csv
from src.app_platform.paths import images_dir

FOLDER_ICON = images_dir() / "folder-black.svg"


class _SingleCalcWorker(QObject):
    """Background parse + `run_calculations` for single-CSV runs (stays off the UI thread)."""

    ok = pyqtSignal(object)  # payload dict
    err = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, csv_path: str, config: dict[str, Any], cancel_event: threading.Event):
        super().__init__()
        self._csv = csv_path
        self._config = config
        self._ce = cancel_event

    def _cancelled(self) -> bool:
        return self._ce.is_set()

    @pyqtSlot()
    def work(self) -> None:
        from src.core.calculations.cancelled import CalculationAborted

        th = self.thread()
        try:
            if self._cancelled():
                self.cancelled.emit()
                return
            try:
                parsed_points = parser.parse_dlc_csv(self._csv, self._config)
            except Exception as e:
                self.err.emit(str(e))
                return
            if self._cancelled():
                self.cancelled.emit()
                return
            try:
                results = calculations.run_calculations(
                    parsed_points, self._config, cancel_check=self._cancelled
                )
            except CalculationAborted:
                self.cancelled.emit()
                return
            except Exception as e:
                self.err.emit(str(e))
                return
            if results is None:
                self.err.emit("The calculation pipeline returned no results.")
                return
            if self._cancelled():
                self.cancelled.emit()
                return
            self.ok.emit(
                {
                    "results_df": results,
                    "config": self._config,
                    "csv_path": self._csv,
                    "parsed_points": parsed_points,
                }
            )
        finally:
            if th is not None:
                th.quit()


def _is_displayable_graph_png(p) -> bool:
    try:
        pp = Path(p)
        return pp.suffix.lower() == ".png" and pp.is_file()
    except Exception:
        return False


class ConfigSelectionScene(QWidget):
    """
    Scene that allows users to run calculations on zebrafish data.
    Displays saved CSVs/configs from the current session and allows new ones to be added.
    """
    data_generated = pyqtSignal(object)  # emits calculation results
    view_output_requested = pyqtSignal(str, str)  # csv_path, config_path
    generate_config_copy_requested = pyqtSignal(str, str)  # csv_path, config_json_path
    toast_requested = pyqtSignal(str, str)  # title, message — errors and successes (no blocking dialogs)

    def __init__(self):
        super().__init__()

        self.current_session = None
        self.csv_path = None
        self.config_path = None
        self.previous_settings = {"csv_path": None, "config_path": None}
        self._tree_theme = "dark"
        # Monotonic run progress: never show a lower % than a prior step in the same run (#91).
        self._progress_run_floor: int = 0
        self._progress_run_busy: bool = False
        self._calculation_run_active: bool = False
        self._cancel_event = threading.Event()
        self._calc_thread: QThread | None = None
        self._calc_worker: _SingleCalcWorker | None = None

        # --- Layout setup ---
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.addStretch(1)
        header = QLabel("Select Configuration")
        header.setObjectName("ConfigSelectionHeader")
        head_row.addWidget(header, 0, Qt.AlignVCenter)
        head_row.addStretch(1)
        head_row.addWidget(
            create_scene_help_button(
                self,
                title="Select Configuration",
                paragraph=(
                    "In the session file tree, select a CSV and a configuration JSON under it, then click Run Calculation. "
                    "Click a CSV in the first column, or a .json in the second column, to make that selection. "
                    "Click the line-graph icon in the right column to open graph outputs. "
                    "(Or double click a .json in the name column to select and start a run from there.) "
                    "Right click a .json to delete it, use Generate copy…, or open View output when that row has saved graphs. "
                    "Right click a CSV row in the first column to delete the CSV. "
                    "The progress bar roughly shows the amount of analysis completed."
                ),
                tips=(
                    "While a run is in progress, the main button reads Stop — click it to cancel, then you can start a different run.",
                ),
            ),
            0,
            Qt.AlignRight | Qt.AlignTop,
        )
        layout.addLayout(head_row)

        self.status_label = QLabel("Select a CSV and Config to run calculations.")
        self.status_label.setObjectName("ConfigSelectionStatus")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # ===============================
        # Session File Tree
        # ===============================
        self.file_tree = QTreeWidget()
        self.file_tree.setObjectName("ConfigSelectionTree")
        self.file_tree.setAttribute(Qt.WA_StyledBackground, True)
        self.file_tree.setHeaderLabels(["CSV Files", "Configurations", ""])
        self.file_tree.setColumnCount(3)
        self.file_tree.setIconSize(QSize(16, 16))
        self.file_tree.setColumnWidth(0, 200)
        _th = self.file_tree.header()
        _th.setSectionResizeMode(0, QHeaderView.Interactive)
        _th.setSectionResizeMode(1, QHeaderView.Stretch)
        _th.setSectionResizeMode(2, QHeaderView.Fixed)
        self.file_tree.setColumnWidth(2, 34)
        self.file_tree.itemClicked.connect(self.handle_tree_click)
        self.file_tree.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        self.file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.file_tree.viewport().installEventFilter(self)
        layout.addWidget(self.file_tree)

        # ===============================
        # Calculation Button + Toggle (same row, centered)
        # ===============================
        self.calc_button = QPushButton("Run Calculation")
        self.calc_button.setObjectName("ConfigSelectionCalcButton")
        self.calc_button.setEnabled(False)
        self.calc_button.clicked.connect(self._on_calc_button_clicked)
        self.toggle_button = QPushButton()
        self.toggle_button.setObjectName("ConfigSelectionTestToggle")
        self.toggle_button.setCheckable(True)
        self.toggle_button.setIcon(QIcon())
        self.toggle_button.setFixedSize(40, 22)
        self.toggle_button.setToolTip("Use Default Config")
        self.toggle_button.clicked.connect(self.toggle_test)
        toggle_label = QLabel("Get Test Output")
        toggle_label.setObjectName("ConfigSelectionHint")
        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.calc_button)
        button_row.addWidget(self.toggle_button)
        button_row.addWidget(toggle_label)
        button_row.addStretch()
        layout.addLayout(button_row)

        # ===============================
        # Progress bar (under button row)
        # ===============================
        progress_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ConfigSelectionProgress")
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("ConfigSelectionStatus")
        progress_row.addWidget(self.progress_bar, stretch=1)
        progress_row.addWidget(self.progress_label)
        layout.addLayout(progress_row)
        self.progress_bar.hide()
        self.progress_label.hide()

        self.setLayout(layout)

    def eventFilter(self, obj, event):
        """Open View Output on release in the graph column. The cell is only ~34px; the icon is
        left-aligned, so a right-edge hit test could miss the icon entirely."""
        if (
            obj is self.file_tree.viewport()
            and event.type() == QEvent.MouseButtonRelease
            and event.button() == Qt.LeftButton
        ):
            pos = event.pos()
            idx = self.file_tree.indexAt(pos)
            if idx.isValid() and idx.column() == 2:
                item = self.file_tree.itemFromIndex(idx)
                if item is None:
                    return super().eventFilter(obj, event)
                cfg_data = item.data(1, Qt.UserRole)
                if not cfg_data:
                    return super().eventFilter(obj, event)
                r = self.file_tree.visualRect(self.file_tree.indexFromItem(item, 2))
                if not r.contains(pos):
                    return super().eventFilter(obj, event)
                parent = item.parent()
                csv_for = parent.data(0, Qt.UserRole) if parent else None
                if csv_for and self._config_row_has_graphs(csv_for, cfg_data):
                    self.view_output_requested.emit(csv_for, cfg_data)
                return True
        return super().eventFilter(obj, event)

    def _update_calc_button_state(self):
        if self._calculation_run_active:
            self.calc_button.setEnabled(True)
            return
        self.calc_button.setEnabled(bool(self.csv_path and self.config_path))

    def set_selected_paths(self, csv_path: str | None, config_path: str | None) -> None:
        """Set CSV + config selection (e.g. session resume) and refresh Run button / status."""
        self.csv_path = csv_path
        self.config_path = config_path
        if self.csv_path and self.config_path:
            self.status_label.setText(
                f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
            )
        self._update_calc_button_state()

    # ==============================================================
    # Session Integration
    # ==============================================================

    def reset_selection_ui(self) -> None:
        """Clear tree selection state when switching sessions."""
        if self._calculation_run_active:
            self.request_cancel_calculation()
        self.finish_calculation_run()
        self.csv_path = None
        self.config_path = None
        self.previous_settings = {"csv_path": None, "config_path": None}
        if self.toggle_button.isChecked():
            self.toggle_button.blockSignals(True)
            self.toggle_button.setChecked(False)
            self.toggle_button.blockSignals(False)
        self.toggle_button.setToolTip("Use Default Config")
        self.status_label.setText("Select a CSV and Config to run calculations.")
        self._update_calc_button_state()
        self.set_progress(0, 0, "")

    def _graph_output_column_icon(self) -> QIcon:
        ic = view_output_tool_icon(self._tree_theme, active=True)
        if ic is None or ic.isNull():
            return self.style().standardIcon(QStyle.SP_FileDialogInfoView)
        return ic

    def _refresh_view_output_icons_in_tree(self) -> None:
        """Re-apply View Output column icons when theme changes (SVG is theme-specific)."""
        if not self.current_session:
            return
        graph_icon = self._graph_output_column_icon()
        for i in range(self.file_tree.topLevelItemCount()):
            csv_item = self.file_tree.topLevelItem(i)
            if not csv_item:
                continue
            csv_path = csv_item.data(0, Qt.UserRole)
            if not csv_path or str(csv_path).startswith("("):
                continue
            for j in range(csv_item.childCount()):
                cfg_item = csv_item.child(j)
                cfg_path = cfg_item.data(1, Qt.UserRole) if cfg_item else None
                if cfg_item and cfg_path and self._config_row_has_graphs(csv_path, cfg_path):
                    cfg_item.setIcon(2, graph_icon)

    def polish_tree_for_theme(self, theme_name: str) -> None:
        """Brighter expand/collapse affordance in dark mode (palette mid tones)."""
        from PyQt5.QtGui import QColor, QPalette

        self._tree_theme = theme_name or "dark"
        self._refresh_view_output_icons_in_tree()

        if theme_name == "dark":
            pal = QPalette(self.file_tree.palette())
            pal.setColor(QPalette.Mid, QColor("#aeb0c8"))
            pal.setColor(QPalette.Light, QColor("#d4d5e5"))
            pal.setColor(QPalette.Dark, QColor("#c4c6d8"))
            self.file_tree.setPalette(pal)
        else:
            self.file_tree.setPalette(self.palette())

    def load_session(self, session):
        """Load a Session object and populate the tree view."""
        try:
            if self.current_session is not None:
                self.current_session.session_updated.disconnect(self.populate_tree)
        except (TypeError, RuntimeError):
            pass

        self.current_session = session
        self.reset_selection_ui()

        # refresh tree on session updates
        self.current_session.session_updated.connect(self.populate_tree)

        # initial population
        self.populate_tree()

    def populate_tree(self):
        """Populate the QTreeWidget with CSVs and Configs from the session."""
        self.file_tree.clear()

        if not self.current_session:
            self.set_progress(0, 0, "")
            return

        # Show progress while building the tree (large sessions/folders can take time).
        total_items = 0
        try:
            for _csv_path, configs in (self.current_session.csvs or {}).items():
                total_items += 1  # csv node
                total_items += len(list((configs or {}).keys()))  # config children
        except Exception:
            total_items = 0

        if total_items > 0:
            self.set_progress(0, total_items, "Loading session items...")
        if self.current_session.length() == 0:
            item = QTreeWidgetItem(["(No saved CSVs)", "", ""])
            item.setDisabled(True)
            self.file_tree.addTopLevelItem(item)
            self.set_progress(0, 0, "")
            return
    
        done = 0
        for csv_path, configs in self.current_session.csvs.items():
            is_folder = False
            n_files = 0
            try:
                is_folder = bool(getattr(self.current_session, "is_folder_csv", lambda _p: False)(csv_path))
                if is_folder:
                    files = self.current_session.get_folder_files(csv_path)
                    n_files = len(files)
            except Exception:
                is_folder = False

            if is_folder:
                folder_name = path.basename(csv_path) or csv_path
                csv_name = f"{folder_name} ({n_files} files)"
            else:
                csv_name = path.basename(csv_path) or csv_path
            csv_item = QTreeWidgetItem([csv_name, "", ""])
            csv_item.setData(0, Qt.UserRole, csv_path)
            if is_folder:
                csv_item.setIcon(0, QIcon(str(FOLDER_ICON)))

            if not configs:
                placeholder = QTreeWidgetItem(["", "(No configs)", ""])
                placeholder.setDisabled(True)
                csv_item.addChild(placeholder)
            else:
                graph_icon = self._graph_output_column_icon()
                for cfg in configs.keys():
                    cfg_name = path.basename(cfg) or cfg
                    cfg_item = QTreeWidgetItem(["", cfg_name, ""])
                    cfg_item.setData(1, Qt.UserRole, cfg)
                    if self._config_row_has_graphs(csv_path, cfg):
                        cfg_item.setIcon(2, graph_icon)
                        cfg_item.setToolTip(
                            2,
                            "Saved graph output — click the icon to open View Output",
                        )
                    csv_item.addChild(cfg_item)
                    done += 1
                    if total_items > 0:
                        self.set_progress(done, total_items, "Loading session items...")

            self.file_tree.addTopLevelItem(csv_item)
            csv_item.setExpanded(True)
            done += 1
            if total_items > 0:
                self.set_progress(done, total_items, "Loading session items...")

        self.set_progress(0, 0, "")
        self.file_tree.setColumnWidth(2, 34)

    def _config_row_has_graphs(self, csv_path: str, cfg_path: str) -> bool:
        """True only when at least one saved PNG exists on disk (View Output can show it)."""
        if not self.current_session or not csv_path or not cfg_path:
            return False
        try:
            if self.current_session.is_folder_csv(csv_path):
                per = self.current_session.getFolderGraphs(csv_path, cfg_path)
                for _cf, assets in (per or {}).items():
                    for a in assets or []:
                        if _is_displayable_graph_png(a):
                            return True
                return False
            for p in self.current_session.csvs.get(csv_path, {}).get(cfg_path, []) or []:
                if _is_displayable_graph_png(p):
                    return True
            return False
        except Exception:
            return False

    def _on_tree_context_menu(self, pos):
        item = self.file_tree.itemAt(pos)
        if not item or not self.current_session:
            return
        cfg_path = item.data(1, Qt.UserRole)
        menu = QMenu(self)
        if cfg_path:
            parent = item.parent()
            csv_path = parent.data(0, Qt.UserRole) if parent else None
            if not csv_path or str(csv_path).startswith("("):
                return
            if self._config_row_has_graphs(csv_path, cfg_path):
                act = menu.addAction("View output")
                act.triggered.connect(
                    lambda _checked=False, c=csv_path, j=cfg_path: self.view_output_requested.emit(
                        c, j
                    )
                )
            act_copy = menu.addAction("Generate copy…")
            act_copy.triggered.connect(
                lambda _checked=False, c=csv_path, j=cfg_path: self.generate_config_copy_requested.emit(
                    c, j
                )
            )
            act_del = menu.addAction("Delete JSON…")
            act_del.triggered.connect(
                lambda _checked=False, c=csv_path, j=cfg_path: self._delete_json_row(c, j)
            )
        else:
            csv_top = item.data(0, Qt.UserRole)
            if csv_top and not str(csv_top).startswith("("):
                act_csv = menu.addAction("Delete CSV…")
                act_csv.triggered.connect(lambda _checked=False, c=csv_top: self._delete_csv_row(c))
        if menu.actions():
            menu.exec_(self.file_tree.viewport().mapToGlobal(pos))

    def _delete_csv_msg_parent(self) -> QWidget:
        """Use top-level window so the box isn’t lost behind frameless chrome / stacks."""
        w = self.window()
        return w if isinstance(w, QWidget) else self

    def _confirm_delete_csv_dialog(self, has_attached_json: bool, csv_label: str) -> bool:
        """Single modal: full warning; Delete / Back (Back default). Parent = main window."""
        msg = QMessageBox(self._delete_csv_msg_parent())
        msg.setWindowModality(Qt.ApplicationModal)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Delete CSV")
        if has_attached_json:
            msg.setText(
                f"Remove “{csv_label}” from this session?\n\n"
                "Deleting this CSV will delete all attached JSON files on disk and remove "
                "their entries from the session.\n\nThis cannot be undone.\n\n"
                "Press Delete to proceed, or Back to cancel."
            )
        else:
            msg.setText(
                f"Remove “{csv_label}” from this session?\n\n"
                "No JSON configs are attached to this CSV.\n\n"
                "Press Delete to proceed, or Back to cancel."
            )
        back_btn = msg.addButton("Back", QMessageBox.RejectRole)
        delete_btn = msg.addButton("Delete", QMessageBox.DestructiveRole)
        msg.setDefaultButton(back_btn)
        msg.exec_()
        return msg.clickedButton() is delete_btn

    def _delete_csv_row(self, csv_path: str) -> None:
        if not self.current_session:
            return
        configs = self.current_session.csvs.get(csv_path, {}) or {}
        config_paths = [c for c in configs.keys() if c]
        label = path.basename(csv_path) or csv_path
        if not self._confirm_delete_csv_dialog(bool(config_paths), label):
            return
        for jp in config_paths:
            try:
                Path(jp).unlink(missing_ok=True)
            except Exception:
                pass
        self.current_session.removeCSV(csv_path)
        self.current_session.save()
        if self.csv_path == csv_path:
            self.reset_selection_ui()
        self.populate_tree()
        self.status_label.setText(f"Removed “{label}” from the session.")

    def _delete_json_row(self, csv_path: str, config_path: str) -> None:
        if (
            QMessageBox.question(
                self,
                "Delete JSON",
                "Remove this configuration from the session and delete the JSON file?\n\n"
                + path.basename(config_path),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            p = Path(config_path)
            if p.is_file():
                p.unlink()
        except Exception as exc:
            self.toast_requested.emit("Delete file", str(exc))
        self.current_session.removeConfigFromCSV(csv_path, config_path)
        self.current_session.save()
        self.populate_tree()
        self.toast_requested.emit("Removed", f"Removed {path.basename(config_path)} from the session.")

    def _on_tree_item_double_clicked(self, item, column):
        """Double-click a config JSON row to select it and start calculation (if not already running)."""
        cfg_data = item.data(1, Qt.UserRole)
        if not cfg_data:
            return
        if column != 1:
            return
        p = str(cfg_data)
        if not p.lower().endswith(".json"):
            return
        self.handle_tree_click(item, 1)
        if self._calculation_run_active:
            return
        if self.csv_path and self.config_path:
            self.calculate()

    def handle_tree_click(self, item, column):
        """Handle user clicking a CSV or config in the tree."""
        csv_data = item.data(0, Qt.UserRole)
        cfg_data = item.data(1, Qt.UserRole)

        if cfg_data:
            if column == 2:
                return
            if column != 1:
                return
            parent = item.parent()
            csv_for = parent.data(0, Qt.UserRole) if parent else None
            if not csv_for:
                return
            self.config_path = cfg_data
            self.csv_path = csv_for
            self.status_label.setText(
                f"Selected: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
            )
            try:
                if self.current_session is not None and self.csv_path and self.config_path:
                    self.current_session.last_csv_path = self.csv_path
                    self.current_session.last_config_path = self.config_path
                    self.current_session.save()
            except Exception:
                pass
            if self.csv_path and self.config_path:
                self.status_label.setText(
                    f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
                )
            self._update_calc_button_state()
            return

        if csv_data and not cfg_data:
            if column != 0:
                return
            self.csv_path = csv_data
            self.config_path = None
            self.status_label.setText(f"Selected CSV: {path.basename(csv_data)}")
            self._update_calc_button_state()

    def toggle_test(self):
        """Switch between test config (default sample files) and tree selection."""
        if self.toggle_button.isChecked():
            self.toggle_button.setToolTip("Using Test Config")
            self.previous_settings["csv_path"] = self.csv_path
            self.previous_settings["config_path"] = self.config_path
            self.csv_path = str(default_sample_csv())
            cfg = default_sample_config()
            self.config_path = str(cfg)
            self.status_label.setText(
                f"Using test config: {Path(self.csv_path).name} + {cfg.name}"
            )
            self._update_calc_button_state()
        else:
            self.toggle_button.setToolTip("Use Default Config")
            self.csv_path = self.previous_settings["csv_path"]
            self.config_path = self.previous_settings["config_path"]
            if self.csv_path and self.config_path:
                self.status_label.setText(
                    f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
                )
                self._update_calc_button_state()
            else:
                self.status_label.setText("Select a CSV and Config to run calculations.")
                self._update_calc_button_state()

    def start_progress_run(self) -> None:
        """Start a new determinate run (e.g. graph build in shell) after parse/calc; resets monotonic floor."""
        self._progress_run_floor = 0
        if self._progress_run_busy:
            self.set_progress_busy(False)
        if self.progress_bar.isHidden():
            self.progress_bar.setRange(0, 100)

    def set_progress_busy(self, active: bool, message: str = "") -> None:
        """
        Indeterminate bar while the pipeline has no sub-milestones to report
        (e.g. long run_calculations on the UI thread). Does not set a percentage.
        """
        self._progress_run_busy = bool(active)
        if not active:
            self.progress_bar.setRange(0, 100)
            return
        self._progress_run_floor = 0
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.show()
        if message:
            self.progress_label.setText(message)
        else:
            self.progress_label.setText("Working…")
        QApplication.processEvents()

    def set_progress(self, n, total, graph_name):
        """
        Update progress. [n]/[total] is the current step; graph_name is status text.
        total<=0: hide the bar. Percent never goes down within a run unless reset (hide) or
        start_progress_run() / set_progress(0,0,).
        """
        if total <= 0:
            self.progress_bar.hide()
            self.progress_label.hide()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_label.setText("")
            self._progress_run_busy = False
            self._progress_run_floor = 0
            return
        if self._progress_run_busy:
            self._progress_run_busy = False
            self.progress_bar.setRange(0, 100)
        self.progress_bar.show()
        self.progress_label.show()
        self.progress_bar.setMaximum(100)
        raw = (100 * int(n)) // int(total) if total else 0
        if raw < self._progress_run_floor:
            raw = self._progress_run_floor
        else:
            self._progress_run_floor = raw
        self.progress_bar.setValue(min(100, raw))
        if graph_name == "Loading graphs...":
            self.progress_label.setText("Loading Graphs…")
        else:
            self.progress_label.setText(f"{n}/{total} — {graph_name}")
        QApplication.processEvents()

    # ==============================================================
    # Calculation run control (Run / Stop)
    # ==============================================================

    def begin_calculation_run(self) -> None:
        self._cancel_event.clear()
        self._calculation_run_active = True
        self.calc_button.setText("Stop Calculation")
        self.calc_button.setEnabled(True)

    def finish_calculation_run(self) -> None:
        self._cancel_event.clear()
        self._calculation_run_active = False
        self.calc_button.setText("Run Calculation")
        self._update_calc_button_state()

    def request_cancel_calculation(self) -> None:
        self._cancel_event.set()

    def is_calculation_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def _on_calc_button_clicked(self) -> None:
        if self._calculation_run_active:
            self.request_cancel_calculation()
        else:
            self.calculate()

    def _on_single_worker_ok(self, payload: object) -> None:
        if not self._calculation_run_active:
            return
        self.set_progress_busy(False)
        self.set_progress(0, 0, "")
        self.status_label.setText("Calculation successful.")
        self.data_generated.emit(payload)

    def _on_single_worker_err(self, message: str) -> None:
        self.set_progress_busy(False)
        self.set_progress(0, 0, "")
        self.status_label.setText("Error.")
        self.toast_requested.emit("Calculation failed", message)
        self.finish_calculation_run()

    def _on_single_worker_cancelled(self) -> None:
        self.set_progress_busy(False)
        self.set_progress(0, 0, "")
        if self.csv_path and self.config_path:
            self.status_label.setText(
                f"Ready: {path.basename(self.csv_path)} + {path.basename(self.config_path)}"
            )
        else:
            self.status_label.setText("Select a CSV and Config to run calculations.")
        self.finish_calculation_run()

    def _setup_single_worker_thread(
        self, config: dict[str, Any]
    ) -> None:
        if self._calc_thread is not None:
            return
        self._calc_thread = QThread()
        self._calc_worker = _SingleCalcWorker(
            str(self.csv_path), dict(config), self._cancel_event
        )
        self._calc_worker.moveToThread(self._calc_thread)
        self._calc_thread.started.connect(self._calc_worker.work)
        self._calc_worker.ok.connect(self._on_single_worker_ok, Qt.QueuedConnection)
        self._calc_worker.err.connect(self._on_single_worker_err, Qt.QueuedConnection)
        self._calc_worker.cancelled.connect(self._on_single_worker_cancelled, Qt.QueuedConnection)
        self._calc_thread.finished.connect(self._on_single_thread_finished)
        self._calc_thread.start()

    def _on_single_thread_finished(self) -> None:
        if self._calc_worker is not None:
            self._calc_worker.deleteLater()
            self._calc_worker = None
        self._calc_thread = None

    # ==============================================================
    # Calculation Logic
    # ==============================================================

    def calculate(self):
        """Run the calculation pipeline and emit data_generated with the payload."""
        if self._calculation_run_active:
            return
        if not self.csv_path or not self.config_path:
            self.toast_requested.emit(
                "Missing files", "Select both a CSV and a config JSON before running."
            )
            return

        if self.current_session:
            # Persist last-used pair for session resume.
            try:
                self.current_session.last_csv_path = self.csv_path
                self.current_session.last_config_path = self.config_path
            except Exception:
                pass
            if not self.current_session.checkExists(
                csv_path=self.csv_path, config_path=self.config_path
            ):
                if not self.current_session.checkExists(self.csv_path):
                    self.current_session.addCSV(self.csv_path)
                self.current_session.addConfigToCSV(self.csv_path, self.config_path)
            self.current_session.save()

        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                config = json.load(handle)
        except (OSError, json.JSONDecodeError) as e:
            self.toast_requested.emit("Config error", str(e))
            self.status_label.setText("Could not read config.")
            return
        config["config_path"] = self.config_path

        # If this CSV is a folder, emit a folder payload for the shell to orchestrate
        # running calculations across all files with aggregated progress.
        try:
            if self.current_session is not None and self.current_session.is_folder_csv(self.csv_path):
                files = self.current_session.get_folder_files(self.csv_path)
                if not files:
                    self.toast_requested.emit(
                        "Empty folder",
                        "This folder has no CSV files recorded in the session.",
                    )
                    return
                self.begin_calculation_run()
                payload = {
                    "csv_folder": self.csv_path,
                    "csv_files": files,
                    "config": config,
                    "config_path": self.config_path,
                }
                # No toast: progress bar in the shell shows bulk status; avoids covering status text.
                self.data_generated.emit(payload)
                return
        except Exception:
            pass

        self.set_progress(0, 0, "")
        self.set_progress_busy(True, "Reading CSV and computing metrics (this can take a while)…")
        self.status_label.setText("Working…")
        QApplication.processEvents()
        self.begin_calculation_run()
        self._setup_single_worker_thread(config)