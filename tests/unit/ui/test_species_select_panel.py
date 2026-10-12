from __future__ import annotations

import pytest
from PyQt5.QtWidgets import QApplication

from src.app_platform.species import Species
from ui.main_panels.species_select_panel import SpeciesSelectPanel
from ui.main_panels.workspace_widget import WorkspaceWidget
from ui.main_window_shell import MainShellWindow


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_defaults_to_zebrafish(qt_app):
    panel = SpeciesSelectPanel()
    assert panel.current_species() is Species.ZEBRAFISH
    assert panel.continue_btn.isEnabled()


def test_continue_emits_zebrafish_by_default(qt_app):
    panel = SpeciesSelectPanel()
    received = []
    panel.species_selected.connect(received.append)

    panel.continue_btn.click()

    assert received == [Species.ZEBRAFISH]


def test_selecting_mouse_emits_mouse_on_continue(qt_app):
    panel = SpeciesSelectPanel()
    received = []
    panel.species_selected.connect(received.append)

    mouse_index = panel.species_combo.findData(Species.MOUSE)
    panel.species_combo.setCurrentIndex(mouse_index)
    panel.continue_btn.click()

    assert received == [Species.MOUSE]


def test_workspace_starts_on_species_panel(qt_app):
    workspace = WorkspaceWidget()
    assert workspace._stack.currentIndex() == WorkspaceWidget.IDX_SPECIES


def test_shell_navigation_landing_to_zebrafish_workflow(qt_app):
    """Verify landing page -> select Zebrafish -> Continue -> empty session page is shown."""
    shell = MainShellWindow()
    try:
        assert shell.workspace._stack.currentIndex() == WorkspaceWidget.IDX_SPECIES
        assert shell._species is None
        assert shell._species_chosen is False

        # Click Continue with default (Zebrafish)
        shell.workspace.species_panel.continue_btn.click()

        assert shell._species_chosen is True
        assert shell._species is Species.ZEBRAFISH
        assert shell.workspace._stack.currentIndex() == WorkspaceWidget.IDX_EMPTY
    finally:
        shell.close()


def test_shell_navigation_landing_to_mouse_and_back(qt_app):
    """Verify landing page -> select Mouse -> Continue -> mouse page is shown, and Back returns to landing."""
    shell = MainShellWindow()
    try:
        assert shell.workspace._stack.currentIndex() == WorkspaceWidget.IDX_SPECIES

        # Select Mouse and Continue
        mouse_index = shell.workspace.species_panel.species_combo.findData(Species.MOUSE)
        shell.workspace.species_panel.species_combo.setCurrentIndex(mouse_index)
        shell.workspace.species_panel.continue_btn.click()

        assert shell._species_chosen is True
        assert shell._species is Species.MOUSE
        assert shell.workspace._stack.currentIndex() == WorkspaceWidget.IDX_MOUSE

        # Click Back on mouse placeholder
        shell.workspace.mouse_panel.back_button.click()

        assert shell._species_chosen is False
        assert shell._species is None
        assert shell.workspace._stack.currentIndex() == WorkspaceWidget.IDX_SPECIES
    finally:
        shell.close()
