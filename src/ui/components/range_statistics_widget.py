"""
range_statistics_widget.py
--------------------------
A PyQt5 widget for specifying/selecting a data range and displaying
calculated basic statistics (min, max, frame/x positions, mean)
for interactive graph data.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import plotly.graph_objs as go
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.core.analysis.range_statistics import (
    RangeStatisticsResult,
    clean_numeric_pairs,
    compute_range_statistics,
    extract_traces_from_figure,
)
try:
    from src.ui.components.wide_popup_combo import WidePopupComboBox
except ImportError:
    try:
        from ui.components.wide_popup_combo import WidePopupComboBox
    except ImportError:
        from PyQt5.QtWidgets import QComboBox as WidePopupComboBox


def _format_pos(pos: Optional[float]) -> str:
    """Format an X/frame coordinate cleanly (as integer if applicable)."""
    if pos is None:
        return "—"
    if abs(pos - round(pos)) < 1e-5:
        return str(int(round(pos)))
    return f"{pos:.3f}".rstrip("0").rstrip(".")


def _format_val(val: Optional[float]) -> str:
    """Format a metric value with appropriate precision."""
    if val is None:
        return "—"
    if abs(val) >= 1e5 or (0 < abs(val) < 1e-4):
        return f"{val:.4e}"
    formatted = f"{val:.4f}".rstrip("0").rstrip(".")
    return formatted if formatted != "-0" else "0"


class RangeStatisticsWidget(QWidget):
    """
    UI panel allowing users to specify a frame/x-axis range and view
    basic statistics (min, max, positions, mean) for graph data.

    Signals:
    --------
    rangeChanged(float, float):
        Emitted when a new range is calculated.
    zoomRequested(float, float):
        Emitted when the user requests zooming the graph view to the specified range.
    resetRequested():
        Emitted when the user requests resetting the range to the full dataset.
    """

    rangeChanged = pyqtSignal(float, float)
    zoomRequested = pyqtSignal(float, float)
    resetRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("RangeStatisticsWidget")

        self._traces: Dict[str, Tuple[List[float], List[float]]] = {}
        self._current_stats: Optional[RangeStatisticsResult] = None
        self._updating_inputs: bool = False

        self._build_ui()
        self.clear()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Container card frame
        card = QFrame()
        card.setObjectName("RangeStatisticsCard")
        card.setStyleSheet(
            "QFrame#RangeStatisticsCard {"
            "  background-color: rgba(255, 255, 255, 0.05);"
            "  border: 1px solid rgba(128, 128, 128, 0.25);"
            "  border-radius: 8px;"
            "}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        # ----------------- Controls Row -----------------
        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(10)

        header_label = QLabel("<b>Range Statistics</b>")
        header_label.setStyleSheet("font-size: 13px;")
        ctrl_layout.addWidget(header_label)

        # Signal / Trace selector
        self.trace_label = QLabel("Signal:")
        ctrl_layout.addWidget(self.trace_label)

        self.trace_combo = WidePopupComboBox()
        self.trace_combo.setMinimumWidth(160)
        self.trace_combo.currentIndexChanged.connect(self._on_trace_changed)
        ctrl_layout.addWidget(self.trace_combo)

        ctrl_layout.addSpacing(6)

        # Range Start spinbox
        lbl_start = QLabel("Start (X):")
        ctrl_layout.addWidget(lbl_start)

        self.start_spin = QDoubleSpinBox()
        self.start_spin.setRange(-1e9, 1e9)
        self.start_spin.setDecimals(2)
        self.start_spin.setSingleStep(1.0)
        self.start_spin.setKeyboardTracking(False)
        self.start_spin.setToolTip("Start frame or x-axis value")
        self.start_spin.valueChanged.connect(self._on_input_changed)
        ctrl_layout.addWidget(self.start_spin)

        # Range End spinbox
        lbl_end = QLabel("End (X):")
        ctrl_layout.addWidget(lbl_end)

        self.end_spin = QDoubleSpinBox()
        self.end_spin.setRange(-1e9, 1e9)
        self.end_spin.setDecimals(2)
        self.end_spin.setSingleStep(1.0)
        self.end_spin.setKeyboardTracking(False)
        self.end_spin.setToolTip("End frame or x-axis value")
        self.end_spin.valueChanged.connect(self._on_input_changed)
        ctrl_layout.addWidget(self.end_spin)

        # Action Buttons
        self.calc_btn = QPushButton("Calculate")
        self.calc_btn.setToolTip("Calculate statistics for the entered range")
        self.calc_btn.clicked.connect(self.calculate_statistics)
        ctrl_layout.addWidget(self.calc_btn)

        self.full_range_btn = QPushButton("Full Range")
        self.full_range_btn.setToolTip("Reset range to encompass the entire dataset")
        self.full_range_btn.clicked.connect(self.reset_to_full_range)
        ctrl_layout.addWidget(self.full_range_btn)

        self.zoom_btn = QPushButton("Zoom to Range")
        self.zoom_btn.setToolTip("Zoom graph to match the selected range")
        self.zoom_btn.clicked.connect(self._on_zoom_clicked)
        ctrl_layout.addWidget(self.zoom_btn)

        ctrl_layout.addStretch(1)
        card_layout.addLayout(ctrl_layout)

        # ----------------- Statistics Display Grid -----------------
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(16)
        stats_grid.setVerticalSpacing(4)

        # Minimum Value & Position
        lbl_min_title = QLabel("Minimum:")
        lbl_min_title.setStyleSheet("font-weight: bold; color: #4a90e2;")
        self.lbl_min_val = QLabel("—")
        self.lbl_min_val.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.lbl_min_pos = QLabel("(at frame: —)")
        self.lbl_min_pos.setStyleSheet("color: gray;")

        min_box = QHBoxLayout()
        min_box.setSpacing(6)
        min_box.addWidget(lbl_min_title)
        min_box.addWidget(self.lbl_min_val)
        min_box.addWidget(self.lbl_min_pos)
        stats_grid.addLayout(min_box, 0, 0)

        # Maximum Value & Position
        lbl_max_title = QLabel("Maximum:")
        lbl_max_title.setStyleSheet("font-weight: bold; color: #e25c4a;")
        self.lbl_max_val = QLabel("—")
        self.lbl_max_val.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.lbl_max_pos = QLabel("(at frame: —)")
        self.lbl_max_pos.setStyleSheet("color: gray;")

        max_box = QHBoxLayout()
        max_box.setSpacing(6)
        max_box.addWidget(lbl_max_title)
        max_box.addWidget(self.lbl_max_val)
        max_box.addWidget(self.lbl_max_pos)
        stats_grid.addLayout(max_box, 0, 1)

        # Mean Value
        lbl_mean_title = QLabel("Mean:")
        lbl_mean_title.setStyleSheet("font-weight: bold; color: #2ecc71;")
        self.lbl_mean_val = QLabel("—")
        self.lbl_mean_val.setStyleSheet("font-size: 13px; font-weight: bold;")

        mean_box = QHBoxLayout()
        mean_box.setSpacing(6)
        mean_box.addWidget(lbl_mean_title)
        mean_box.addWidget(self.lbl_mean_val)
        stats_grid.addLayout(mean_box, 0, 2)

        # Points Count
        lbl_count_title = QLabel("Points:")
        lbl_count_title.setStyleSheet("font-weight: bold; color: #9b59b6;")
        self.lbl_count_val = QLabel("—")
        self.lbl_count_val.setStyleSheet("font-size: 13px;")

        count_box = QHBoxLayout()
        count_box.setSpacing(6)
        count_box.addWidget(lbl_count_title)
        count_box.addWidget(self.lbl_count_val)
        stats_grid.addLayout(count_box, 0, 3)

        stats_grid.setColumnStretch(4, 1)
        card_layout.addLayout(stats_grid)

        # Status / Feedback label (e.g. invalid range message)
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #d9534f; font-size: 11px;")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        card_layout.addWidget(self.status_label)

        layout.addWidget(card)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_figure(self, fig: Optional[go.Figure]) -> None:
        """Load data traces from a Plotly figure and calculate full range statistics."""
        self._traces = extract_traces_from_figure(fig)
        self._populate_traces()

    def set_series(
        self,
        x_values: Sequence[float],
        y_values: Sequence[float],
        name: str = "Series",
    ) -> None:
        """Set a single dataset directly (useful for programmatic or non-figure usage)."""
        clean_x, clean_y = clean_numeric_pairs(x_values, y_values)
        self._traces = {name: (clean_x, clean_y)}
        self._populate_traces()

    def set_range(self, start_x: float, end_x: float) -> None:
        """
        Update the range spinboxes and calculate statistics for [start_x, end_x].
        Ensures start_x <= end_x.
        """
        s = min(float(start_x), float(end_x))
        e = max(float(start_x), float(end_x))

        self._updating_inputs = True
        try:
            self.start_spin.setValue(s)
            self.end_spin.setValue(e)
        finally:
            self._updating_inputs = False

        self.calculate_statistics()

    def _apply_full_range(self) -> bool:
        """Set start and end spinboxes to the full range of the active trace. Returns True if successful."""
        trace_data = self._get_active_trace_data()
        if not trace_data:
            self.clear_stats()
            return False

        x_vals, _ = trace_data
        min_x = min(x_vals)
        max_x = max(x_vals)

        self._updating_inputs = True
        try:
            self.start_spin.setValue(min_x)
            self.end_spin.setValue(max_x)
        finally:
            self._updating_inputs = False

        self.calculate_statistics()
        return True

    def reset_to_full_range(self) -> None:
        """Reset the range inputs to the full dataset and emit resetRequested to reset graph zoom."""
        if self._apply_full_range():
            self.resetRequested.emit()

    def sync_to_full_range(self) -> None:
        """
        Update range inputs and stats to full range without emitting resetRequested.

        Used when the graph itself resets zoom (e.g. autorange or double click)
        to prevent a recursive feedback loop back to the graph.
        """
        self._apply_full_range()

    def calculate_statistics(self) -> None:
        """Calculate statistics for the currently specified range and update UI."""
        trace_data = self._get_active_trace_data()
        if not trace_data:
            self.clear_stats("No data available to calculate statistics.")
            return

        x_vals, y_vals = trace_data
        start_x = self.start_spin.value()
        end_x = self.end_spin.value()

        result = compute_range_statistics(x_vals, y_vals, start_x, end_x)
        self._current_stats = result
        self._display_statistics(result)

        if result.is_valid:
            self.rangeChanged.emit(start_x, end_x)

    def get_current_statistics(self) -> Optional[RangeStatisticsResult]:
        """Return the most recently calculated RangeStatisticsResult."""
        return self._current_stats

    def clear(self) -> None:
        """Reset widget to empty placeholder state."""
        self._traces.clear()
        self._current_stats = None
        self.trace_combo.blockSignals(True)
        self.trace_combo.clear()
        self.trace_combo.blockSignals(False)

        self._updating_inputs = True
        try:
            self.start_spin.setValue(0.0)
            self.end_spin.setValue(0.0)
        finally:
            self._updating_inputs = False

        self.clear_stats()
        self.setEnabled(False)

    def clear_stats(self, message: Optional[str] = None) -> None:
        """Reset display values to placeholders."""
        self.lbl_min_val.setText("—")
        self.lbl_min_pos.setText("(at frame: —)")
        self.lbl_max_val.setText("—")
        self.lbl_max_pos.setText("(at frame: —)")
        self.lbl_mean_val.setText("—")
        self.lbl_count_val.setText("—")

        if message:
            self.status_label.setText(message)
            self.status_label.setVisible(True)
        else:
            self.status_label.setText("")
            self.status_label.setVisible(False)

    # ------------------------------------------------------------------
    # Internal Handlers
    # ------------------------------------------------------------------

    def _populate_traces(self) -> None:
        self.trace_combo.blockSignals(True)
        self.trace_combo.clear()

        if not self._traces:
            self.clear()
            return

        self.setEnabled(True)
        for name in self._traces.keys():
            self.trace_combo.addItem(name)

        # Show trace combo if there are multiple traces; hide label/combo if only 1
        has_multiple = len(self._traces) > 1
        self.trace_label.setVisible(has_multiple)
        self.trace_combo.setVisible(has_multiple)

        self.trace_combo.setCurrentIndex(0)
        self.trace_combo.blockSignals(False)

        # Determine precision based on X values (integer frames vs floats)
        self._adjust_spinbox_precision()
        self.reset_to_full_range()

    def _adjust_spinbox_precision(self) -> None:
        trace_data = self._get_active_trace_data()
        if not trace_data:
            return

        x_vals, _ = trace_data
        # If all x-values are integers (e.g. frame numbers), use step 1
        all_int = all(abs(x - round(x)) < 1e-5 for x in x_vals[:100])
        if all_int:
            self.start_spin.setDecimals(0)
            self.end_spin.setDecimals(0)
            self.start_spin.setSingleStep(1.0)
            self.end_spin.setSingleStep(1.0)
        else:
            self.start_spin.setDecimals(3)
            self.end_spin.setDecimals(3)
            self.start_spin.setSingleStep(0.1)
            self.end_spin.setSingleStep(0.1)

    def _get_active_trace_data(self) -> Optional[Tuple[List[float], List[float]]]:
        if not self._traces:
            return None
        name = self.trace_combo.currentText()
        if name and name in self._traces:
            return self._traces[name]
        return next(iter(self._traces.values()))

    def _on_trace_changed(self, _idx: int) -> None:
        self._adjust_spinbox_precision()
        self.reset_to_full_range()

    def _on_input_changed(self) -> None:
        if self._updating_inputs:
            return
        self.calculate_statistics()

    def _on_zoom_clicked(self) -> None:
        s = min(self.start_spin.value(), self.end_spin.value())
        e = max(self.start_spin.value(), self.end_spin.value())
        self.zoomRequested.emit(s, e)

    def _display_statistics(self, res: RangeStatisticsResult) -> None:
        if not res.is_valid:
            self.clear_stats(res.error_message or "Invalid range.")
            return

        self.status_label.setVisible(False)
        self.status_label.setText("")

        self.lbl_min_val.setText(_format_val(res.min_value))
        self.lbl_min_pos.setText(f"(at frame: {_format_pos(res.min_x)})")

        self.lbl_max_val.setText(_format_val(res.max_value))
        self.lbl_max_pos.setText(f"(at frame: {_format_pos(res.max_x)})")

        self.lbl_mean_val.setText(_format_val(res.mean_value))
        self.lbl_count_val.setText(f"{res.count} pts")
