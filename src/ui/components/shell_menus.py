"""File / Help menus for the frameless main shell (title bar tool buttons)."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction, QMainWindow, QMenu


def build_file_help_menus(
    shell: QMainWindow,
    *,
    on_session_select: Callable[[], None],
    on_view_console: Callable[[], None],
) -> tuple[QMenu, QMenu]:
    """Return (File, Help) menus wired to the given shell callbacks."""
    file_menu = QMenu(shell)
    exit_act = QAction("Save && Exit", shell)
    exit_act.setShortcut(QKeySequence.Quit)
    exit_act.triggered.connect(shell.close)
    file_menu.addAction(exit_act)
    shell.addAction(exit_act)

    sess_act = QAction("Session Select…", shell)
    sess_act.triggered.connect(on_session_select)
    file_menu.addAction(sess_act)

    help_menu = QMenu(shell)
    console_act = QAction("View Console", shell)
    console_act.triggered.connect(lambda _checked=False: on_view_console())
    help_menu.addAction(console_act)

    return file_menu, help_menu
