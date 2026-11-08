"""Overlaid time-series plot of one parameter across the selected fish."""

from __future__ import annotations

from typing import List, Optional, Sequence

import plotly.graph_objects as go
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.core.comparison.fish_data import LoadedFish
from src.core.comparison.fish_plot import build_overlay_figure
from src.core.comparison.fish_plot_data import FishColorMap
from src.ui.components.InteractiveGraph import InteractiveGraph

_EMPTY_MESSAGE = "Select at least one fish and one parameter to plot."


class FishOverlayWidget(QWidget):
    """
    Shows one parameter for several fish as overlaid lines, one color per fish.

    The figure is built whenever the data or parameter changes, but it is only
    loaded into the web view while the widget is visible, so a hidden tab costs
    nothing.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("FishOverlayWidget")
        self._fish: List[LoadedFish] = []
        self._color_map = FishColorMap()
        self._figure: Optional[go.Figure] = None
        self._needs_render = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Parameter:"))
        self.parameter_combo = QComboBox()
        self.parameter_combo.setObjectName("FishOverlayParameterCombo")
        self.parameter_combo.setMinimumContentsLength(18)
        self.parameter_combo.currentIndexChanged.connect(self._rebuild_figure)
        controls.addWidget(self.parameter_combo)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.message_label = QLabel(_EMPTY_MESSAGE)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label, 1)

        self._graph = InteractiveGraph()
        self._graph.setVisible(False)
        layout.addWidget(self._graph, 1)

    @property
    def figure(self) -> Optional[go.Figure]:
        """The overlay figure for the current data, or None when there is nothing to plot."""
        return self._figure

    def set_data(
        self,
        fish_list: Sequence[LoadedFish],
        parameters: Sequence[str],
        color_map: FishColorMap,
    ) -> None:
        """Plot ``fish_list``; ``parameters`` fills the dropdown (selection is kept if possible)."""
        self._fish = list(fish_list)
        self._color_map = color_map
        self._set_parameters(list(parameters))
        self._rebuild_figure()

    def clear(self) -> None:
        """Remove all data and show the empty message."""
        self._fish = []
        self._set_parameters([])
        self._rebuild_figure()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._render_if_visible()

    def _set_parameters(self, parameters: List[str]) -> None:
        previous = self.parameter_combo.currentText()
        self.parameter_combo.blockSignals(True)
        self.parameter_combo.clear()
        self.parameter_combo.addItems(parameters)
        if previous in parameters:
            self.parameter_combo.setCurrentText(previous)
        self.parameter_combo.blockSignals(False)

    def _rebuild_figure(self) -> None:
        parameter = self.parameter_combo.currentText()
        if self._fish and parameter:
            self._figure = build_overlay_figure(self._fish, parameter, self._color_map)
        else:
            self._figure = None
        self.message_label.setText(_EMPTY_MESSAGE)
        self.message_label.setVisible(self._figure is None)
        self._graph.setVisible(self._figure is not None)
        self._needs_render = True
        self._render_if_visible()

    def _render_if_visible(self) -> None:
        if not self._needs_render or not self.isVisible():
            return
        self._needs_render = False
        if self._figure is None:
            self._graph.clear()
            return
        try:
            self._graph.set_figure(self._figure)
        except Exception as exc:
            self._graph.setVisible(False)
            self.message_label.setText(f"Could not draw the plot:\n{exc}")
            self.message_label.setVisible(True)
            return
        # The range-statistics panel is built for single-line graphs.
        self._graph.range_stats_widget.setVisible(False)