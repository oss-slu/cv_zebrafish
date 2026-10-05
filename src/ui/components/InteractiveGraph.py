"""
InteractiveGraph.py
-------------------
A PyQt5 widget that renders a Plotly figure as an interactive HTML page
using QWebEngineView (zoom, pan, hover tooltips built-in via Plotly.js),
paired with an integrated RangeStatisticsWidget to compute and display
basic statistics (min, max, positions, mean) for user-selected ranges.

Falls back gracefully to a plain QLabel with an error message if
QtWebEngineWidgets is unavailable, while keeping range statistics fully functional.

Usage
-----
    from src.ui.components.InteractiveGraph import InteractiveGraph

    widget = InteractiveGraph(parent)
    widget.set_figure(fig)          # fig is a plotly go.Figure
    widget.clear()                  # reset to blank state
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import plotly
import plotly.graph_objs as go
import plotly.io as pio

from PyQt5.QtCore import QTimer, Qt, QUrl, pyqtSignal
from PyQt5.QtWidgets import QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from src.ui.components.range_statistics_widget import RangeStatisticsWidget

# ---------------------------------------------------------------------------
# Optional QtWebEngine import
# ---------------------------------------------------------------------------
try:
    from PyQt5.QtWebEngineWidgets import QWebEngineSettings, QWebEngineView

    _WEBENGINE_AVAILABLE = True
except ImportError:
    _WEBENGINE_AVAILABLE = False


# Plotly ≥2.3 uses :focus-visible in modebar CSS injected via insertRule(). Older
# Chromium (Qt 5 WebEngine) rejects that selector and aborts Plotly startup, so
# we ship a byte-patched copy of plotly.min.js (cached under %TEMP%) for previews.
_PLOTLY_QWEBENGINE_PATCHES: tuple[tuple[bytes, bytes], ...] = (
    (b'"X .modebar-btn:focus-visible"', b'"X .modebar-btn:focus"'),
    (b"button:focus:focus-visible", b"button:focus"),
    (b"button:focus:not(:focus-visible)", b"button:focus:not(:focus)"),
)


# ---------------------------------------------------------------------------
# Public widget
# ---------------------------------------------------------------------------


class InteractiveGraph(QWidget):
    """
    Displays a Plotly figure interactively (zoom / pan / hover) when
    PyQtWebEngine is available, and provides interactive range statistics
    calculation (min, max, frame positions, mean) for the current graph.

    Signals:
    --------
    rangeSelected(float, float):
        Emitted when a range is selected or zoomed in the interactive Plotly view.
    rangeReset():
        Emitted when the interactive view's zoom is reset to default autorange.
    """

    rangeSelected = pyqtSignal(float, float)
    rangeReset = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._figure: Optional[go.Figure] = None
        self._html_cache: Optional[str] = None
        self._preview_html_path: Optional[Path] = None

        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_figure(self, fig: go.Figure) -> None:
        """Render *fig* as an interactive Plotly chart and load range statistics."""
        if not isinstance(fig, go.Figure):
            self.clear()
            return

        self._figure = fig
        self._range_stats_widget.set_figure(fig)
        self._range_stats_widget.setVisible(True)

        html = self._figure_to_html(fig)
        self._html_cache = html

        if _WEBENGINE_AVAILABLE:
            # setHtml() uses a data:-like origin; Plotly's large inline bundle often
            # fails to run there, leaving a blank white view. file:// + load() is reliable.
            path = self._write_preview_html(html)
            self._web_view.load(QUrl.fromLocalFile(str(path.resolve())))
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
        self._range_stats_widget.clear()

        if _WEBENGINE_AVAILABLE:
            self._web_view.setUrl(QUrl("about:blank"))
            self._stack.setCurrentWidget(self._web_view)
        else:
            self._fallback_label.setText("Select a graph on the left.")
            self._stack.setCurrentWidget(self._fallback_label)

    @property
    def figure(self) -> Optional[go.Figure]:
        """Return the currently displayed Plotly figure (or None)."""
        return self._figure

    @property
    def range_stats_widget(self) -> RangeStatisticsWidget:
        """Return the embedded range statistics widget."""
        return self._range_stats_widget

    def set_x_range(self, x0: float, x1: float) -> None:
        """Update the x-axis range in the interactive Plotly view."""
        self._run_plotly_js(
            f"if (window.Plotly) {{ Plotly.relayout(gd, {{ 'xaxis.range': [{x0}, {x1}] }}); }}"
        )

    def reset_zoom(self) -> None:
        """Reset the zoom/range in the interactive Plotly view to default autorange."""
        self._run_plotly_js(
            "if (window.Plotly) { Plotly.relayout(gd, { 'xaxis.autorange': true }); }"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, stretch=1)

        if _WEBENGINE_AVAILABLE:
            self._web_view = QWebEngineView()
            self._web_view.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            ws = self._web_view.settings()
            ws.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            ws.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            ws.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)
            self._web_view.loadFinished.connect(self._on_preview_load_finished)
            self._web_view.titleChanged.connect(self._on_title_changed)
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

        # Integrated Range Statistics panel
        self._range_stats_widget = RangeStatisticsWidget(self)
        layout.addWidget(self._range_stats_widget)

        # Connect range events between graph and statistics widget
        self.rangeSelected.connect(self._range_stats_widget.set_range)
        self.rangeReset.connect(self._range_stats_widget.reset_to_full_range)
        self._range_stats_widget.zoomRequested.connect(self.set_x_range)
        self._range_stats_widget.resetRequested.connect(self.reset_zoom)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if _WEBENGINE_AVAILABLE:
            # Plotly sometimes measures a 0×0 container on first paint; refresh after resize.
            QTimer.singleShot(0, self._resize_plotly_in_view)

    def _write_preview_html(self, html: str) -> Path:
        if self._preview_html_path is None:
            self._preview_html_path = Path(tempfile.gettempdir()) / (
                f"cv_zebrafish_plotly_{os.getpid()}_{id(self)}.html"
            )
        self._preview_html_path.write_text(html, encoding="utf-8")
        return self._preview_html_path

    def _on_preview_load_finished(self, ok: bool) -> None:
        if ok:
            self._resize_plotly_in_view()
            self._attach_plotly_listeners()

    def _run_plotly_js(self, body: str) -> None:
        """
        Execute JavaScript within the WebEngine view where `gd` is the Plotly graph element.

        Wraps the given script body inside a safe IIFE that resolves the Plotly container
        element (`gd`), guarding against missing elements or runtime exceptions.
        """
        if not _WEBENGINE_AVAILABLE or self._web_view is None:
            return
        js = (
            "(() => { try { "
            "var gd = document.querySelector('.plotly-graph-div') "
            "|| document.querySelector('.js-plotly-plot'); "
            f"if (gd) {{ {body} }} "
            "} catch (e) {} })();"
        )
        self._web_view.page().runJavaScript(js)

    def _on_title_changed(self, title: str) -> None:
        """
        Handle title change notifications emitted by the embedded WebEngine view.

        Note:
        `document.title` mutations + `QWebEngineView.titleChanged` serve as a lightweight,
        zero-dependency IPC channel between Plotly.js in the web view and Python.
        Unlike QWebChannel, this does not require injecting external scripts or registering
        extra QObjects, and works reliably with local HTML previews. A timestamp suffix
        (`:Date.now()`) ensures subsequent selections with identical bounds still trigger
        the signal.
        """
        if not title:
            return
        if title.startswith("RANGE:"):
            parts = title.split(":")
            if len(parts) >= 3:
                try:
                    x0 = float(parts[1])
                    x1 = float(parts[2])
                    self.rangeSelected.emit(min(x0, x1), max(x0, x1))
                except ValueError:
                    pass
        elif title.startswith("AUTORANGE:"):
            self.rangeReset.emit()

    def _attach_plotly_listeners(self) -> None:
        self._run_plotly_js(
            "if (!gd._cv_listeners_attached) { "
            "  gd._cv_listeners_attached = true; "
            "  gd.on('plotly_selected', function(eventData) { "
            "    if (eventData && eventData.range && eventData.range.x) { "
            "      document.title = 'RANGE:' + eventData.range.x[0] + ':' + eventData.range.x[1] + ':' + Date.now(); "
            "    } "
            "  }); "
            "  gd.on('plotly_relayout', function(eventData) { "
            "    if (!eventData) return; "
            "    if (eventData['xaxis.range[0]'] !== undefined && eventData['xaxis.range[1]'] !== undefined) { "
            "      document.title = 'RANGE:' + eventData['xaxis.range[0]'] + ':' + eventData['xaxis.range[1]'] + ':' + Date.now(); "
            "    } else if (eventData['xaxis.range'] && Array.isArray(eventData['xaxis.range'])) { "
            "      document.title = 'RANGE:' + eventData['xaxis.range'][0] + ':' + eventData['xaxis.range'][1] + ':' + Date.now(); "
            "    } else if (eventData['xaxis.autorange']) { "
            "      document.title = 'AUTORANGE:' + Date.now(); "
            "    } "
            "  }); "
            "}"
        )

    def _resize_plotly_in_view(self) -> None:
        self._run_plotly_js(
            "if (window.Plotly && Plotly.Plots) { Plotly.Plots.resize(gd); }"
        )

    @staticmethod
    def _patched_plotly_js_uri() -> str:
        """plotly.min.js with :focus-visible removed for Qt WebEngine compatibility."""
        pkg = Path(plotly.__file__).resolve().parent
        src = pkg / "package_data" / "plotly.min.js"
        dest = Path(tempfile.gettempdir()) / "cv_zebrafish_plotly_qwebengine.min.js"
        need_write = True
        if dest.is_file():
            try:
                need_write = (
                    dest.stat().st_mtime < src.stat().st_mtime
                    or dest.stat().st_size == 0
                )
            except OSError:
                need_write = True
        if need_write:
            data = src.read_bytes()
            for old, new in _PLOTLY_QWEBENGINE_PATCHES:
                data = data.replace(old, new)
            dest.write_bytes(data)
        return dest.resolve().as_uri()

    @staticmethod
    def _figure_to_html(fig: go.Figure) -> str:
        """Convert a Plotly figure to a self-contained HTML string."""
        view = go.Figure(fig)
        if view.layout.height is None:
            view.update_layout(height=560, autosize=True)
        return pio.to_html(
            view,
            include_plotlyjs=InteractiveGraph._patched_plotly_js_uri(),
            full_html=True,
            config={
                "scrollZoom": True,       # mouse-wheel zoom
                "displayModeBar": True,   # show the toolbar (zoom/pan/reset/save)
                "modeBarButtonsToAdd": [
                    "select2d",           # box select tool for range selection
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