"""
summary_statistics_widget.py
----------------------------
A PyQt5 widget for displaying summary statistics (mean, median, and units)
for kinematic analysis outputs in a structured, sortable table with export capabilities.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Optional, Sequence, Union

import pandas as pd
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.core.analysis.summary_statistics import (
    compute_summary_statistics_df,
    export_summary_statistics_to_csv,
    export_summary_statistics_to_excel,
)
try:
    from styles.ui_scale import scaled_px
except ImportError:
    try:
        from src.styles.ui_scale import scaled_px
    except ImportError:
        def scaled_px(val: int) -> int:
            return val

try:
    from src.ui.components.wide_popup_combo import WidePopupComboBox
except ImportError:
    try:
        from ui.components.wide_popup_combo import WidePopupComboBox
    except ImportError:
        from PyQt5.QtWidgets import QComboBox as WidePopupComboBox


def _format_stat(val: Optional[float]) -> str:
    """Format numeric statistics cleanly for UI display."""
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "—"
    if abs(val) >= 1e5 or (0 < abs(val) < 1e-4):
        return f"{val:.4e}"
    formatted = f"{val:.4f}".rstrip("0").rstrip(".")
    return formatted if formatted != "-0" else "0"


class SummaryStatisticsWidget(QWidget):
    """
    Displays analysis output summary statistics (parameter, mean, median, units)
    in a table with export options.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SummaryStatisticsWidget")

        self._current_summary_df: Optional[pd.DataFrame] = None
        self._results_by_csv: Optional[Dict[str, pd.DataFrame]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top control bar: CSV selector (for multi-CSV runs), count label, and export buttons
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(8)

        self.csv_label = QLabel("CSV file:")
        self.csv_label.setObjectName("SummaryStatsCsvLabel")
        self.csv_combo = WidePopupComboBox()
        self.csv_combo.setObjectName("SummaryStatsCsvCombo")
        self.csv_combo.currentIndexChanged.connect(self._on_csv_combo_changed)
        self.csv_label.setVisible(False)
        self.csv_combo.setVisible(False)

        top_bar.addWidget(self.csv_label)
        top_bar.addWidget(self.csv_combo, stretch=1)

        self.status_label = QLabel("No summary statistics calculated.")
        self.status_label.setObjectName("SummaryStatsStatusLabel")
        self.status_label.setStyleSheet("color: gray;")
        top_bar.addWidget(self.status_label)

        top_bar.addStretch()

        self.export_csv_btn = QPushButton("Export Summary CSV…")
        self.export_csv_btn.setObjectName("SummaryStatsExportCsvButton")
        self.export_csv_btn.setMinimumHeight(scaled_px(32))
        self.export_csv_btn.setToolTip("Export summary statistics table to CSV.")
        self.export_csv_btn.clicked.connect(self._on_export_csv_clicked)
        self.export_csv_btn.setEnabled(False)
        top_bar.addWidget(self.export_csv_btn)

        self.export_excel_btn = QPushButton("Export Summary Excel…")
        self.export_excel_btn.setObjectName("SummaryStatsExportExcelButton")
        self.export_excel_btn.setMinimumHeight(scaled_px(32))
        self.export_excel_btn.setToolTip("Export summary statistics table to Excel (.xlsx).")
        self.export_excel_btn.clicked.connect(self._on_export_excel_clicked)
        self.export_excel_btn.setEnabled(False)
        top_bar.addWidget(self.export_excel_btn)

        layout.addLayout(top_bar)

        # Table widget
        self.table = QTableWidget()
        self.table.setObjectName("SummaryStatsTable")
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Parameter", "Mean", "Median", "Units"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)

        layout.addWidget(self.table, stretch=1)

    def set_results_by_csv(self, results_by_csv: Optional[Dict[str, pd.DataFrame]]) -> None:
        """Update multi-CSV dataset mapping for folder runs."""
        self._results_by_csv = (
            {str(k): v for k, v in results_by_csv.items() if isinstance(v, pd.DataFrame)}
            if results_by_csv
            else None
        )
        has_multi = bool(self._results_by_csv and len(self._results_by_csv) > 1)
        self.csv_label.setVisible(has_multi)
        self.csv_combo.setVisible(has_multi)

        self.csv_combo.blockSignals(True)
        self.csv_combo.clear()
        if self._results_by_csv:
            for path_str in self._results_by_csv.keys():
                name = Path(path_str).name
                self.csv_combo.addItem(name, userData=path_str)
        self.csv_combo.blockSignals(False)

    def _on_csv_combo_changed(self, index: int) -> None:
        """Handle selection change in the multi-CSV dropdown."""
        if not self._results_by_csv or index < 0:
            return
        path_str = self.csv_combo.itemData(index)
        df = self._results_by_csv.get(str(path_str))
        self.set_dataframe(df)

    def set_dataframe(
        self,
        results_df: Optional[pd.DataFrame],
        parameters: Optional[Sequence[str]] = None,
        custom_units: Optional[Dict[str, str]] = None,
    ) -> None:
        """Compute and display summary statistics for the provided DataFrame."""
        if results_df is None or results_df.empty:
            self.clear()
            return

        summary_df = compute_summary_statistics_df(
            results_df, parameters=parameters, custom_units=custom_units
        )
        self._current_summary_df = summary_df

        self.table.setRowCount(len(summary_df))
        for row_idx, (_, row) in enumerate(summary_df.iterrows()):
            param_item = QTableWidgetItem(str(row["parameter"]))
            mean_item = QTableWidgetItem(_format_stat(row["mean"]))
            median_item = QTableWidgetItem(_format_stat(row["median"]))
            units_item = QTableWidgetItem(str(row["units"]) if row["units"] else "—")

            mean_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            median_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            units_item.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(row_idx, 0, param_item)
            self.table.setItem(row_idx, 1, mean_item)
            self.table.setItem(row_idx, 2, median_item)
            self.table.setItem(row_idx, 3, units_item)

        self.status_label.setText(f"{len(summary_df)} parameters calculated")
        self.status_label.setStyleSheet("")
        self.export_csv_btn.setEnabled(True)
        self.export_excel_btn.setEnabled(True)

    def clear(self) -> None:
        """Clear all table items and reset status."""
        self._current_summary_df = None
        self.table.setRowCount(0)
        self.status_label.setText("No summary statistics calculated.")
        self.status_label.setStyleSheet("color: gray;")
        self.export_csv_btn.setEnabled(False)
        self.export_excel_btn.setEnabled(False)

    def get_summary_dataframe(self) -> Optional[pd.DataFrame]:
        """Return the current summary statistics DataFrame."""
        return self._current_summary_df

    def _on_export_csv_clicked(self) -> None:
        if self._current_summary_df is None or self._current_summary_df.empty:
            QMessageBox.warning(self, "No data", "No summary statistics available to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Export Summary Statistics to CSV", "summary_statistics.csv", "CSV files (*.csv)"
        )
        if not path:
            return

        try:
            written = export_summary_statistics_to_csv(self._current_summary_df, path)
            QMessageBox.information(
                self, "Export complete", f"Saved summary statistics to:\n{written}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"Could not export summary stats:\n{exc}")

    def _on_export_excel_clicked(self) -> None:
        if self._current_summary_df is None or self._current_summary_df.empty:
            QMessageBox.warning(self, "No data", "No summary statistics available to export.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Summary Statistics to Excel",
            "summary_statistics.xlsx",
            "Excel files (*.xlsx)",
        )
        if not path:
            return

        try:
            written = export_summary_statistics_to_excel(self._current_summary_df, path)
            QMessageBox.information(
                self, "Export complete", f"Saved summary statistics to:\n{written}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"Could not export summary stats:\n{exc}")
