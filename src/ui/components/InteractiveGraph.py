"""
InteractiveGraph.py
-------------------
A PyQt5 widget that renders a Plotly figure as an interactive HTML page
using QWebEngineView (zoom, pan, hover tooltips built-in via Plotly.js).

Falls back gracefully to a plain QLabel with an error message if
QtWebEngineWidgets is unavailable.

Usage
-----
    from src.ui.components.InteractiveGraph import InteractiveGraph

    widget = InteractiveGraph(parent)
    widget.set_figure(fig)          # fig is a plotly go.Figure
    widget.clear()                  # reset to blank state
"""

from __future__ import annotations

from typing import Optional

import plotly.graph_objs as go
import plotly.io as pio

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

# ---------------------------------------------------------------------------
# Optional QtWebEngine import
# ---------------------------------------------------------------------------
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView

    _WEBENGINE_AVAILABLE = True
except ImportError:
    _WEBENGINE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public widget
# ---------------------------------------------------------------------------


class InteractiveGraph(QWidget):
    """
    Displays a Plotly figure interactively (zoom / pan / hover) when
    PyQtWebEngine is available, or falls back to a static error label.

    Parameters
    ----------
    parent : QWidget, optional
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._figure: Optional[go.Figure] = None
        self._html_cache: Optional[str] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_figure(self, fig: go.Figure) -> None:
        """Render *fig* as an interactive Plotly chart inside the widget."""
        if not isinstance(fig, go.Figure):
            self.clear()
            return

        self._figure = fig
        html = self._figure_to_html(fig)
        self._html_cache = html

        if _WEBENGINE_AVAILABLE:
            # Load the HTML string directly into the web view.
            self._web_view.setHtml(html, QUrl("about:blank"))
            self._stack.setCurrentWidget(self._web_view)
        else:
            self._fallback_label.setText(
                "Interactive graphs require PyQtWebEngine.\n"
                "Install it with:\n"
                "  pip install PyQtWebEngine\n"
                "or:\n"
                "  conda install -c conda-forge pyqtwebengine\n\n"
                "Restart the app after installing."
            )
            self._stack.setCurrentWidget(self._fallback_label)

    def clear(self) -> None:
        """Reset the widget to its empty / placeholder state."""
        self._figure = None
        self._html_cache = None
        if _WEBENGINE_AVAILABLE:
            self._web_view.setHtml("", QUrl("about:blank"))
            self._stack.setCurrentWidget(self._web_view)
        else:
            self._fallback_label.setText("Select a graph on the left.")
            self._stack.setCurrentWidget(self._fallback_label)

    @property
    def figure(self) -> Optional[go.Figure]:
        """Return the currently displayed Plotly figure (or None)."""
        return self._figure

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        if _WEBENGINE_AVAILABLE:
            self._web_view = QWebEngineView()
            self._web_view.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            self._stack.addWidget(self._web_view)
        else:
            # Placeholder so the stack always has at least one widget
            self._web_view = None  # type: ignore[assignment]

        self._fallback_label = QLabel("Select a graph on the left.")
        self._fallback_label.setAlignment(Qt.AlignCenter)
        self._fallback_label.setWordWrap(True)
        self._fallback_label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self._stack.addWidget(self._fallback_label)

        # Start on the web view if available, otherwise the label
        if _WEBENGINE_AVAILABLE:
            self._stack.setCurrentWidget(self._web_view)
        else:
            self._stack.setCurrentWidget(self._fallback_label)

    @staticmethod
    def _figure_to_html(fig: go.Figure) -> str:
        """Convert a Plotly figure to a self-contained HTML string."""
        return pio.to_html(
            fig,
            include_plotlyjs="cdn",   # loads Plotly.js from CDN (~3 MB, cached)
            full_html=True,
            config={
                "scrollZoom": True,       # mouse-wheel zoom
                "displayModeBar": True,   # show the toolbar (zoom/pan/reset/save)
                "modeBarButtonsToAdd": [
                    "drawline",
                    "drawopenpath",
                    "eraseshape",
                ],
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": "zebrafish_graph",
                    "scale": 2,
                },
            },
        )