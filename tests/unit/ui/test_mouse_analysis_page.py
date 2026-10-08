from __future__ import annotations

import ast
from pathlib import Path

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QFileDialog, QGroupBox

from mouse import DLC_FILE_FILTER, MouseAnalysisPage
from ui.main_panels.workspace_widget import WorkspaceWidget

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
MOUSE_ROOT = SRC_ROOT / "mouse"

# Zebrafish-specific packages the mouse package must not depend on.
ZEBRAFISH_MODULES = ("core", "ui.main_panels", "ui.popup_panels", "ui.workers", "session")


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    # Treat ``src.core.x`` the same as ``core.x``.
    return {n[len("src."):] if n.startswith("src.") else n for n in names}


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(prefix + ".")


def _fake_dialog(monkeypatch, path, seen=None):
    def fake(parent, caption, directory, filter_):
        if seen is not None:
            seen["filter"] = filter_
        return str(path), filter_

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake)


def _left_click(widget):
    QTest.mouseClick(widget, Qt.LeftButton, pos=widget.rect().center())


def test_page_starts_on_load_step_with_mouse_logo(qt_app):
    page = MouseAnalysisPage()
    assert page.current_step() == MouseAnalysisPage.IDX_LOAD
    assert page.dlc_path is None
    logo = page.load_panel.logo.pixmap()
    assert logo is not None and not logo.isNull()
    # A loaded logo keeps its transparent background; the missing-file fallback is solid gray.
    assert logo.hasAlphaChannel()


def test_analysis_step_has_placeholder_sections(qt_app):
    page = MouseAnalysisPage()
    titles = {g.title() for g in page.findChildren(QGroupBox)}
    assert "Parameters (coming soon)" in titles
    assert page.results_placeholder.text() == "Results will appear here"


def test_clicking_load_panel_picks_file_and_shows_analysis(qt_app, monkeypatch, tmp_path):
    seen = {}
    picked = tmp_path / "mouse1DLC_resnet50.h5"
    _fake_dialog(monkeypatch, picked, seen)
    page = MouseAnalysisPage()
    emitted = []
    page.dlc_file_selected.connect(emitted.append)

    _left_click(page.load_panel)

    assert seen["filter"] == DLC_FILE_FILTER
    assert "*.h5" in DLC_FILE_FILTER and "*.csv" in DLC_FILE_FILTER
    assert page.current_step() == MouseAnalysisPage.IDX_ANALYSIS
    assert page.dlc_path_field.text() == "mouse1DLC_resnet50.h5"
    assert page.dlc_path_field.toolTip() == str(picked)
    assert page.dlc_path == picked
    assert emitted == [str(picked)]


def test_cancelled_picker_on_load_step_stays_on_load_step(qt_app, monkeypatch):
    page = MouseAnalysisPage()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))

    _left_click(page.load_panel)

    assert page.current_step() == MouseAnalysisPage.IDX_LOAD
    assert page.dlc_path is None


def test_upload_button_replaces_file_and_cancel_keeps_it(qt_app, monkeypatch):
    page = MouseAnalysisPage()
    page.set_dlc_file("/data/first.csv")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *a, **k: ("", ""))
    page.dlc_button.click()
    assert page.dlc_path_field.text() == "first.csv"

    _fake_dialog(monkeypatch, Path("/data/second.h5"))
    page.dlc_button.click()
    assert page.dlc_path_field.text() == "second.h5"
    assert page.current_step() == MouseAnalysisPage.IDX_ANALYSIS


@pytest.mark.parametrize("step", ["load", "analysis"])
def test_back_emits_back_requested_and_resets(qt_app, monkeypatch, step):
    # Back must not also open the file picker on the clickable load panel.
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: pytest.fail("picker opened")
    )
    page = MouseAnalysisPage()
    if step == "analysis":
        page.set_dlc_file("/data/first.csv")
    calls = []
    page.back_requested.connect(lambda: calls.append(True))

    button = page.load_panel.back_button if step == "load" else page.back_button
    _left_click(button)

    assert calls == [True]
    assert page.current_step() == MouseAnalysisPage.IDX_LOAD
    assert page.dlc_path is None
    assert page.dlc_path_field.text() == ""


def test_workspace_routes_mouse_and_back_to_species(qt_app):
    ws = WorkspaceWidget()
    assert isinstance(ws.mouse_panel, MouseAnalysisPage)

    ws.show_mouse()
    assert ws._stack.currentIndex() == WorkspaceWidget.IDX_MOUSE
    assert ws._stack.currentWidget() is ws.mouse_panel

    ws.show_species()
    assert ws._stack.currentIndex() == WorkspaceWidget.IDX_SPECIES


def test_mouse_package_does_not_import_zebrafish_modules():
    for path in MOUSE_ROOT.rglob("*.py"):
        for module in _imported_modules(path):
            for banned in ZEBRAFISH_MODULES:
                assert not _matches(module, banned), f"{path.name} imports {module}"


def test_zebrafish_modules_do_not_import_mouse_package():
    # The workspace host and shell are the only places allowed to wire the page in.
    allowed = {
        SRC_ROOT / "ui" / "main_panels" / "workspace_widget.py",
        SRC_ROOT / "ui" / "main_window_shell.py",
    }
    for path in SRC_ROOT.rglob("*.py"):
        if MOUSE_ROOT in path.parents or path in allowed:
            continue
        for module in _imported_modules(path):
            assert not _matches(module, "mouse"), f"{path} imports {module}"
