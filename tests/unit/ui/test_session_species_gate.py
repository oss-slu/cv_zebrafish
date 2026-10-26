from __future__ import annotations

import pytest
from PyQt5.QtWidgets import QApplication

import ui.main_window_shell as shell_mod
from app_platform.ui_preferences import UiPreferences
from src.app_platform.species import Species
from ui.main_window_shell import MainShellWindow


@pytest.fixture(scope="session")
def qt_app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _DialogOpened(Exception):
    pass


class _FakeDialog:
    def __init__(self, *args, **kwargs):
        raise _DialogOpened


class _StopLoad(Exception):
    """Raised by the fake loader so an allowed load stops before touching real panels."""


@pytest.fixture
def shell(qt_app, monkeypatch):
    # Keep the test off the user's on-disk session registry and real dialogs.
    monkeypatch.setattr(shell_mod, "sync_registry_with_disk", lambda: None)
    monkeypatch.setattr(shell_mod, "SessionSelectDialog", _FakeDialog)
    loaded = []

    def fake_load(path):
        loaded.append(path)
        raise _StopLoad

    monkeypatch.setattr(shell_mod, "load_session_from_json", fake_load)
    w = MainShellWindow(ui_prefs=UiPreferences())
    toasts = []
    monkeypatch.setattr(w, "_show_error_toast", lambda title, msg: toasts.append((title, msg)))
    monkeypatch.setattr(w, "_warn_blocked", lambda: None)
    w.toasts = toasts
    w.loaded = loaded
    yield w
    w.close()


def _choose(w: MainShellWindow, species: Species) -> None:
    combo = w.workspace.species_panel.species_combo
    combo.setCurrentIndex(combo.findData(species))
    w.workspace.species_panel.continue_btn.click()


def test_species_is_none_until_chosen(shell):
    assert shell.species is None


@pytest.mark.parametrize("species", [Species.ZEBRAFISH, Species.MOUSE])
def test_species_is_readable_after_choice(shell, species):
    _choose(shell, species)
    assert shell.species is species


def test_back_from_mouse_clears_species(shell):
    _choose(shell, Species.MOUSE)
    shell.workspace.mouse_panel.load_panel.back_button.click()
    assert shell.species is None


def test_open_session_blocked_before_species_chosen(shell):
    shell._on_open_session()  # _FakeDialog would raise if the dialog opened
    assert shell.toasts == [("Session", "Choose a species first.")]
    assert shell.workspace.current_panel() is shell.workspace.species_panel


def test_open_session_blocked_on_mouse_path(shell):
    _choose(shell, Species.MOUSE)
    shell._on_open_session()
    assert shell.toasts == [("Session", "Sessions aren't available for Mouse yet.")]
    assert shell.workspace.current_panel() is shell.workspace.mouse_panel


def test_open_session_allowed_after_zebrafish(shell):
    _choose(shell, Species.ZEBRAFISH)
    with pytest.raises(_DialogOpened):
        shell._on_open_session()
    assert shell.toasts == []


@pytest.mark.parametrize("species", [None, Species.MOUSE])
def test_load_session_from_path_is_gated(shell, species):
    if species is not None:
        _choose(shell, species)
    shell._load_session_from_path("/tmp/some_session.json")
    assert shell.loaded == []
    assert shell.current_session is None
    assert len(shell.toasts) == 1


def test_load_session_from_path_allowed_after_zebrafish(shell):
    _choose(shell, Species.ZEBRAFISH)
    with pytest.raises(_StopLoad):
        shell._load_session_from_path("/tmp/some_session.json")
    assert shell.loaded == ["/tmp/some_session.json"]

class _FakeVerifySession:
    def __init__(self):
        self.csvs = {}

    def addCSVFolder(self, folder_path, files):
        self.csvs.setdefault(folder_path, {})

    def save(self):
        pass

    def checkExists(self, csv_path=None, config_path=None):
        return config_path in self.csvs.get(csv_path, {})

    def addConfigToCSV(self, csv_path, config_path):
        self.csvs[csv_path][config_path] = []


def test_json_config_after_folder_upload_attaches_to_folder(shell, monkeypatch):
    session = _FakeVerifySession()
    shell.current_session = session
    shell._verify_last_csv_path = "/tmp/previous.csv"
    monkeypatch.setattr(shell, "_refresh_sidebar_capabilities", lambda: None)

    folder_path = "/tmp/csv_folder"
    json_path = "/tmp/config.json"

    shell._on_verify_folder_selected(
        folder_path,
        ["/tmp/csv_folder/a.csv", "/tmp/csv_folder/b.csv"],
    )

    assert shell._verify_last_csv_path == folder_path

    shell._on_verify_json_selected(json_path)

    assert json_path in session.csvs[folder_path]
    assert "/tmp/previous.csv" not in session.csvs
