from __future__ import annotations
from typing import Dict, Optional

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

from PyQt5.QtWebEngineWidgets import *
import numpy as np

GraphSource = go.Figure

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
        self._data = data

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
