from __future__ import annotations

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from app_platform.paths import app_stylesheet_path
from styles.themes import THEMES, apply_error_toast_theme
from ui.components.error_toast import ErrorToast


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def toast(qt_app):
    t = ErrorToast(None, on_console_clicked=lambda: None)
    apply_error_toast_theme(t, THEMES["dark"])
    yield t
    t.hide()
    t.deleteLater()


def test_buttons_lay_out_by_widget_rect(toast):
    # Without this, macOS style overlaps the two QSS-styled buttons (#128).
    assert toast._btn_console.testAttribute(Qt.WA_LayoutUsesWidgetRect)
    assert toast._btn_close.testAttribute(Qt.WA_LayoutUsesWidgetRect)


@pytest.fixture
def app_stylesheet(qt_app):
    # The overlap only shows up once the app stylesheet wraps the native macOS style.
    previous = qt_app.styleSheet()
    qt_app.setStyleSheet(app_stylesheet_path().read_text(encoding="utf-8"))
    yield
    qt_app.setStyleSheet(previous)


def test_buttons_do_not_overlap(app_stylesheet, toast, qt_app):
    toast.show_message("Session", "Sessions aren't available for Mouse yet.", timeout_ms=0)
    qt_app.processEvents()

    console = toast._btn_console.geometry()
    close = toast._btn_close.geometry()
    assert console.right() < close.left()
