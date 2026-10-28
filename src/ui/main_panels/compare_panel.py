"""Compare Fish panel: load several DeepLabCut files and compare them side by side."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd
from PyQt5.QtCore import Qt, QThread
from PyQt5.QtGui import QColor, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.core.comparison.fish_comparison_table import (
    FIXED_COLUMNS,
    build_comparison_table,
    export_comparison_table,
    get_parameter_names,
)
from src.core.comparison.fish_data import LoadedFish
from src.core.validation import json_verifier
from src.core.comparison.fish_plot_data import FishColorMap
from ui.components.fish_overlay_widget import FishOverlayWidget
from styles.ui_scale import scaled_px
from ui.workers.fish_load_worker import FishLoadWorker

_COL_INCLUDE, _COL_LABEL, _COL_ID, _COL_SOURCE, _COL_REMOVE = range(5)


def _format_value(value: float) -> str:
    """Format a statistic for display; NaN and infinity show as an em dash."""
    if value is None or math.isnan(value) or math.isinf(value):
        return "—"
    if abs(value) >= 1e5 or (0 < abs(value) < 1e-4):
        return f"{value:.4e}"
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class ComparePanel(QWidget):
    """Load several fish with one config, then compare their mean and median values."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ComparePanel")

        self._config: Optional[Dict[str, Any]] = None
        self._fish: List[LoadedFish] = []
        self._next_fish_number = 1
        self._excluded_fish_ids: Set[str] = set()
        self._excluded_parameters: Set[str] = set()
        self._comparison: Optional[pd.DataFrame] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[FishLoadWorker] = None
        self._pending_file_count = 0

        self._colors = FishColorMap()
        self._build_ui()
        self._refresh_all()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        margin = scaled_px(30)
        layout.setContentsMargins(margin, scaled_px(20), margin, scaled_px(20))
        layout.setSpacing(scaled_px(12))

        header = QLabel("Compare Fish")
        header.setStyleSheet("font-size: 17px; font-weight: bold;")
        layout.addWidget(header, 0, Qt.AlignHCenter)

        layout.addLayout(self._build_setup_row())

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_selection_area())
        splitter.addWidget(self._build_comparison_area())
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self.messages = QTextEdit()
        self.messages.setObjectName("CompareMessages")
        self.messages.setReadOnly(True)
        self.messages.setMaximumHeight(scaled_px(110))
        self.messages.setPlaceholderText("Load messages and errors appear here.")
        layout.addWidget(self.messages)

    def _build_setup_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(QLabel("Config:"))

        self.config_path_field = QLineEdit()
        self.config_path_field.setReadOnly(True)
        self.config_path_field.setPlaceholderText("No JSON config selected")
        row.addWidget(self.config_path_field, 1)

        self.config_button = QPushButton("Select Config…")
        self.config_button.setCursor(Qt.PointingHandCursor)
        self.config_button.clicked.connect(self._select_config)
        row.addWidget(self.config_button)

        self.add_files_button = QPushButton("Add Fish Files…")
        self.add_files_button.setCursor(Qt.PointingHandCursor)
        self.add_files_button.clicked.connect(self._add_files)
        row.addWidget(self.add_files_button)
        return row

    def _build_selection_area(self) -> QWidget:
        area = QWidget()
        layout = QHBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)

        fish_column = QVBoxLayout()
        fish_column.addWidget(QLabel("Loaded fish (double-click a label to rename):"))
        self.fish_table = QTableWidget(0, 5)
        self.fish_table.setObjectName("CompareFishTable")
        self.fish_table.setHorizontalHeaderLabels(["Include", "Label", "Fish ID", "Source file", ""])
        self.fish_table.verticalHeader().setVisible(False)
        self.fish_table.setSelectionBehavior(QTableWidget.SelectRows)
        header = self.fish_table.horizontalHeader()
        header.setSectionResizeMode(_COL_INCLUDE, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_LABEL, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_ID, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(_COL_SOURCE, QHeaderView.Stretch)
        header.setSectionResizeMode(_COL_REMOVE, QHeaderView.ResizeToContents)
        self.fish_table.itemChanged.connect(self._on_fish_item_changed)
        fish_column.addWidget(self.fish_table)
        layout.addLayout(fish_column, 3)

        parameter_column = QVBoxLayout()
        parameter_column.addWidget(QLabel("Parameters to compare:"))
        self.parameter_list = QListWidget()
        self.parameter_list.setObjectName("CompareParameterList")
        self.parameter_list.itemChanged.connect(self._on_parameter_item_changed)
        parameter_column.addWidget(self.parameter_list)

        buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(lambda: self._set_all_parameters(True))
        self.clear_all_button = QPushButton("Clear")
        self.clear_all_button.clicked.connect(lambda: self._set_all_parameters(False))
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.clear_all_button)
        parameter_column.addLayout(buttons)
        layout.addLayout(parameter_column, 2)
        return area

    def _build_comparison_area(self) -> QWidget:
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(0, 0, 0, 0)

        top = QHBoxLayout()
        self.status_label = QLabel("")
        top.addWidget(self.status_label, 1)
        self.export_button = QPushButton("Export Comparison…")
        self.export_button.setCursor(Qt.PointingHandCursor)
        self.export_button.setToolTip("Export the comparison table to CSV or Excel (.xlsx).")
        self.export_button.clicked.connect(self._export_comparison)
        top.addWidget(self.export_button)
        layout.addLayout(top)

        self.comparison_view = QTableWidget()
        self.comparison_view.setObjectName("CompareTable")
        self.comparison_view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.comparison_view.setAlternatingRowColors(True)
        self.comparison_view.setHorizontalScrollMode(QTableWidget.ScrollPerPixel)
        self.overlay_widget = FishOverlayWidget()
        self.view_tabs = QTabWidget()
        self.view_tabs.setObjectName("CompareViewTabs")
        self.view_tabs.addTab(self.comparison_view, "Table")
        self.view_tabs.addTab(self.overlay_widget, "Plots")
        layout.addWidget(self.view_tabs, 1)
        return area

    # ------------------------------------------------------- public helpers

    def add_fish(self, fish_list: Sequence[LoadedFish]) -> None:
        """Add already-loaded fish to the panel and refresh every view."""
        self._fish.extend(fish_list)
        self._refresh_all()

    def loaded_fish(self) -> List[LoadedFish]:
        """Return a copy of the fish currently held by the panel."""
        return list(self._fish)

    def comparison_table(self) -> Optional[pd.DataFrame]:
        """Return the table currently shown, or None if nothing is selected."""
        return None if self._comparison is None else self._comparison.copy()

    # ------------------------------------------------------- config + files

    def _select_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON Config", "", "JSON Files (*.json)"
        )
        if not path:
            return
        config, errors = self._read_config(Path(path))
        if errors:
            self._append_message(f"Config rejected ({Path(path).name}):")
            for error in errors:
                self._append_message(f"  - {error}")
            return
        self._config = config
        self.config_path_field.setText(path)
        self._append_message(f"Config loaded: {Path(path).name}")
        if self._fish:
            self._append_message("The new config applies only to files added from now on.")
        self._update_controls()

    @staticmethod
    def _read_config(path: Path) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        """Read and validate a JSON config; returns (config, error messages)."""
        try:
            with path.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
        except Exception as exc:
            return None, [f"Could not read the file: {exc}"]
        errors = list(json_verifier.validate_config(config, json_verifier.SCHEMA))
        if hasattr(json_verifier, "extra_checks"):
            errors.extend(json_verifier.extra_checks(config))
        return (None, errors) if errors else (config, [])

    def _add_files(self) -> None:
        if self._thread is not None or self._config is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select DeepLabCut CSV Files", "", "CSV Files (*.csv)"
        )
        if not paths:
            return

        already_loaded = {fish.source_file for fish in self._fish}
        new_paths = []
        for path in paths:
            if path in already_loaded:
                self._append_message(f"Skipped {Path(path).name}: already loaded.")
            else:
                new_paths.append(path)
        if new_paths:
            self._start_loading(new_paths)

    def _start_loading(self, paths: List[str]) -> None:
        self._pending_file_count = len(paths)
        self._worker = FishLoadWorker(
            paths,
            self._config,
            [fish.label for fish in self._fish],
            self._next_fish_number,
        )
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_load_progress)
        self._worker.finished.connect(self._on_load_finished)
        self._worker.failed.connect(self._on_load_failed)
        self._thread.finished.connect(self._on_thread_finished)
        self._update_controls()
        self._thread.start()

    def _on_load_progress(self, index: int, total: int, file_name: str) -> None:
        self.status_label.setText(f"Loading {index}/{total}: {file_name}…")

    def _on_load_finished(self, loaded: List[LoadedFish], failures: List[Tuple[str, str]]) -> None:
        self._next_fish_number += len(loaded)
        for path, reason in failures:
            self._append_message(f"Skipped {Path(path).name}:\n{reason}")
        for fish in loaded:
            if fish.warnings:
                self._append_message(f"{fish.label}: loaded with {len(fish.warnings)} warning(s).")
        self._append_message(f"Loaded {len(loaded)} of {self._pending_file_count} file(s).")
        if loaded:
            self.add_fish(loaded)

    def _on_load_failed(self, message: str) -> None:
        self._append_message(f"Loading failed: {message}")

    def _on_thread_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._refresh_all()

    # --------------------------------------------------------- fish table

    def _rebuild_fish_table(self) -> None:
        table = self.fish_table
        table.blockSignals(True)
        table.setRowCount(len(self._fish))
        for row, fish in enumerate(self._fish):
            include_item = QTableWidgetItem()
            include_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            include_item.setCheckState(
                Qt.Unchecked if fish.fish_id in self._excluded_fish_ids else Qt.Checked
            )
            table.setItem(row, _COL_INCLUDE, include_item)

            label_item = QTableWidgetItem(fish.label)
            label_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsEditable)
            swatch = QPixmap(14, 14)
            swatch.fill(QColor(self._colors.color_for(fish.fish_id)))
            label_item.setIcon(QIcon(swatch))
            table.setItem(row, _COL_LABEL, label_item)

            id_item = QTableWidgetItem(fish.fish_id)
            id_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            table.setItem(row, _COL_ID, id_item)

            source_item = QTableWidgetItem(Path(fish.source_file).name)
            source_item.setToolTip(fish.source_file)
            source_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            table.setItem(row, _COL_SOURCE, source_item)

            remove_button = QPushButton("Remove")
            remove_button.setCursor(Qt.PointingHandCursor)
            remove_button.clicked.connect(
                lambda _checked=False, fish_id=fish.fish_id: self._remove_fish(fish_id)
            )
            table.setCellWidget(row, _COL_REMOVE, remove_button)
        table.blockSignals(False)

    def _on_fish_item_changed(self, item: QTableWidgetItem) -> None:
        if item.row() >= len(self._fish):
            return
        fish = self._fish[item.row()]
        if item.column() == _COL_INCLUDE:
            if item.checkState() == Qt.Checked:
                self._excluded_fish_ids.discard(fish.fish_id)
            else:
                self._excluded_fish_ids.add(fish.fish_id)
            self._refresh_comparison()
        elif item.column() == _COL_LABEL:
            new_label = item.text().strip()
            error = self._label_error(fish, new_label)
            if error:
                self._append_message(error)
                self.fish_table.blockSignals(True)
                item.setText(fish.label)
                self.fish_table.blockSignals(False)
                return
            fish.label = new_label
            self._refresh_comparison()

    def _label_error(self, fish: LoadedFish, new_label: str) -> Optional[str]:
        if not new_label:
            return "Labels cannot be empty."
        if new_label in FIXED_COLUMNS:
            return f"'{new_label}' is reserved; choose another label."
        if any(other.label == new_label for other in self._fish if other is not fish):
            return f"The label '{new_label}' is already used by another fish."
        return None

    def _remove_fish(self, fish_id: str) -> None:
        self._fish = [fish for fish in self._fish if fish.fish_id != fish_id]
        self._excluded_fish_ids.discard(fish_id)
        self._colors.release(fish_id)
        self._refresh_all()

    # ----------------------------------------------------- parameter list

    def _rebuild_parameter_list(self) -> None:
        self.parameter_list.blockSignals(True)
        self.parameter_list.clear()
        for name in get_parameter_names(self._fish):
            item = QListWidgetItem(name)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(
                Qt.Unchecked if name in self._excluded_parameters else Qt.Checked
            )
            self.parameter_list.addItem(item)
        self.parameter_list.blockSignals(False)

    def _on_parameter_item_changed(self, item: QListWidgetItem) -> None:
        if item.checkState() == Qt.Checked:
            self._excluded_parameters.discard(item.text())
        else:
            self._excluded_parameters.add(item.text())
        self._refresh_comparison()

    def _set_all_parameters(self, checked: bool) -> None:
        state = Qt.Checked if checked else Qt.Unchecked
        self.parameter_list.blockSignals(True)
        for index in range(self.parameter_list.count()):
            item = self.parameter_list.item(index)
            item.setCheckState(state)
            if checked:
                self._excluded_parameters.discard(item.text())
            else:
                self._excluded_parameters.add(item.text())
        self.parameter_list.blockSignals(False)
        self._refresh_comparison()

    # ---------------------------------------------------- comparison table

    def _selected_fish(self) -> List[LoadedFish]:
        return [fish for fish in self._fish if fish.fish_id not in self._excluded_fish_ids]

    def _selected_parameters(self) -> List[str]:
        return [
            self.parameter_list.item(index).text()
            for index in range(self.parameter_list.count())
            if self.parameter_list.item(index).checkState() == Qt.Checked
        ]

    def _refresh_comparison(self) -> None:
        fish = self._selected_fish()
        parameters = self._selected_parameters()
        view = self.comparison_view
        if not fish or not parameters:
            self._comparison = None
            view.clear()
            self.overlay_widget.clear()
            view.setRowCount(0)
            view.setColumnCount(0)
            if not self._fish:
                self.status_label.setText("Select a config and add fish files to begin.")
            else:
                self.status_label.setText("Select at least one fish and one parameter.")
            self._update_controls()
            return

        comparison = build_comparison_table(fish, parameters)
        self._comparison = comparison
        view.clear()
        view.setColumnCount(len(comparison.columns))
        view.setRowCount(len(comparison))
        view.setHorizontalHeaderLabels([str(column) for column in comparison.columns])
        for row_index, row in enumerate(comparison.itertuples(index=False)):
            for column_index, value in enumerate(row):
                is_number = column_index >= len(FIXED_COLUMNS)
                item = QTableWidgetItem(_format_value(value) if is_number else str(value))
                item.setTextAlignment(
                    (Qt.AlignRight if is_number else Qt.AlignLeft) | Qt.AlignVCenter
                )
                view.setItem(row_index, column_index, item)
        view.resizeColumnsToContents()
        for column_index in range(len(FIXED_COLUMNS), len(comparison.columns)):
            view.setColumnWidth(column_index, max(view.columnWidth(column_index), scaled_px(110)))
        self.status_label.setText(f"{len(fish)} fish × {len(parameters)} parameters")
        self.overlay_widget.set_data(fish, parameters, self._colors)
        self._update_controls()

    def _export_comparison(self) -> None:
        if self._comparison is None:
            return
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Comparison Table",
            "fish_comparison.csv",
            "CSV files (*.csv);;Excel files (*.xlsx)",
        )
        if not path:
            return
        if Path(path).suffix.lower() not in (".csv", ".xlsx"):
            path += ".xlsx" if "xlsx" in selected_filter else ".csv"
        try:
            written = export_comparison_table(self._comparison, self._selected_fish(), path)
        except (OSError, ValueError, ImportError) as exc:
            self._append_message(f"Export failed: {exc}")
            QMessageBox.critical(self, "Export failed", f"Could not export the comparison:\n{exc}")
            return
        self._append_message(f"Exported comparison to {written}")

    # -------------------------------------------------------------- shared

    def _refresh_all(self) -> None:
        self._rebuild_fish_table()
        self._rebuild_parameter_list()
        self._refresh_comparison()

    def _update_controls(self) -> None:
        busy = self._thread is not None
        self.config_button.setEnabled(not busy)
        self.add_files_button.setEnabled(self._config is not None and not busy)
        self.add_files_button.setToolTip(
            "" if self._config is not None else "Select a JSON config first."
        )
        has_table = self._comparison is not None
        self.export_button.setEnabled(has_table and not busy)
        has_parameters = self.parameter_list.count() > 0
        self.select_all_button.setEnabled(has_parameters)
        self.clear_all_button.setEnabled(has_parameters)

    def _append_message(self, text: str) -> None:
        self.messages.append(text)