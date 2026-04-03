"""
New application shell: single top bar (logo, inline File/Help, window controls), sidebar, workspace.

Uses Qt.FramelessWindowHint; legacy flow remains in ui.scenes.MainWindow.
On Windows, WM_NCHITTEST enables native edge resize for frameless windows.
"""

import ctypes
import sys

from PyQt5.QtCore import QEvent, QPoint, QSize, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from styles.themes import THEMES, apply_theme

from ui.components.chrome_separators import horizontal_separator
from ui.components.custom_title_bar import CustomTitleBar
from ui.components.sidebar_tools import SidebarTools
from ui.main_panels.workspace_widget import WorkspaceWidget

# winuser.h — frameless resize hit testing
_HTLEFT = 10
_HTRIGHT = 11
_HTTOP = 12
_HTTOPLEFT = 13
_HTTOPRIGHT = 14
_HTBOTTOM = 15
_HTBOTTOMLEFT = 16
_HTBOTTOMRIGHT = 17
_WM_NCHITTEST = 0x0084


def _read_wm_nchittest_lparam(msg_ptr: int) -> tuple[int, int] | None:
    """
    Read (message, lParam) from a native MSG* without ctypes.wintypes (some envs lack it).
    Layout matches MSVC MSG: x64 message@+8, lParam@+24; x86 message@+4, lParam@+12.
    """
    if not msg_ptr:
        return None
    ps = ctypes.sizeof(ctypes.c_void_p)
    if ps == 8:
        msg_off, lparam_off = 8, 24
    else:
        msg_off, lparam_off = 4, 12
    try:
        mid = ctypes.c_uint32.from_address(msg_ptr + msg_off).value
        lp = ctypes.c_ssize_t.from_address(msg_ptr + lparam_off).value
    except OSError:
        return None
    return mid, int(lp)


class MainShellWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setObjectName("MainShellWindow")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("CV Zebrafish")
        self.setMinimumSize(QSize(900, 510))
        self.resize(QSize(1000, 700))

        self.current_theme = "dark"
        apply_theme(self, THEMES[self.current_theme])

        self._has_session = False

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        file_menu, help_menu = self._build_top_menus()
        self._title_bar = CustomTitleBar(self, file_menu, help_menu, shell)
        shell_layout.addWidget(self._title_bar)

        shell_layout.addWidget(horizontal_separator())

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        sidebar_wrap = QWidget()
        sidebar_wrap.setObjectName("ShellSidebar")
        sidebar_wrap.setAttribute(Qt.WA_StyledBackground, True)
        sw = QHBoxLayout(sidebar_wrap)
        sw.setContentsMargins(0, 0, 0, 0)
        sw.setSpacing(0)
        self.sidebar = SidebarTools()
        sw.addWidget(self.sidebar)
        body_layout.addWidget(sidebar_wrap)

        self.workspace = WorkspaceWidget()
        body_layout.addWidget(self.workspace, stretch=1)

        shell_layout.addWidget(body, stretch=1)

        self.setCentralWidget(shell)

        self.sidebar.tool_triggered.connect(self._on_sidebar_tool)
        self.sidebar.theme_toggle_requested.connect(self._toggle_theme)
        self.workspace.empty_panel.open_session_requested.connect(self._on_open_session)

        self.sidebar.reflect_theme(self.current_theme)

        self._apply_session_state()

        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self._title_bar.update_max_button()
        super().changeEvent(event)

    def nativeEvent(self, eventType, message):
        """Windows: let the OS resize the frameless window from edges/corners (Aero)."""
        if sys.platform != "win32":
            return False, 0
        try:
            et = bytes(eventType)
        except (TypeError, AttributeError):
            return False, 0
        if et != b"windows_generic_MSG":
            return False, 0
        try:
            addr = int(message)
        except (TypeError, ValueError, OverflowError):
            return False, 0
        parsed = _read_wm_nchittest_lparam(addr)
        if parsed is None:
            return False, 0
        mid, lp = parsed
        if mid != _WM_NCHITTEST:
            return False, 0
        x = ctypes.c_int16(lp & 0xFFFF).value
        y = ctypes.c_int16((lp >> 16) & 0xFFFF).value
        local = self.mapFromGlobal(QPoint(x, y))
        m = 8
        w, h = self.width(), self.height()
        on_l = local.x() < m
        on_r = local.x() >= w - m
        on_t = local.y() < m
        on_b = local.y() >= h - m

        if on_t and on_l:
            return True, _HTTOPLEFT
        if on_t and on_r:
            return True, _HTTOPRIGHT
        if on_b and on_l:
            return True, _HTBOTTOMLEFT
        if on_b and on_r:
            return True, _HTBOTTOMRIGHT
        if on_l:
            return True, _HTLEFT
        if on_r:
            return True, _HTRIGHT
        if on_t:
            return True, _HTTOP
        if on_b:
            return True, _HTBOTTOM

        return False, 0

    def _build_top_menus(self) -> tuple[QMenu, QMenu]:
        """Inline top strip uses QMenu attached to QToolButton (avoids Windows QMenuBar >> overflow)."""
        file_menu = QMenu(self)
        exit_act = QAction("Save && Exit", self)
        exit_act.setShortcut(QKeySequence.Quit)
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)
        self.addAction(exit_act)

        sess_act = QAction("Session Select…", self)
        sess_act.triggered.connect(self._on_open_session)
        file_menu.addAction(sess_act)

        help_menu = QMenu(self)
        console_act = QAction("View Console", self)
        console_act.triggered.connect(self._show_console_placeholder)
        help_menu.addAction(console_act)

        return file_menu, help_menu

    def _apply_session_state(self) -> None:
        self.sidebar.set_session_active(self._has_session)
        if not self._has_session:
            self.workspace.show_empty()

    def _on_open_session(self) -> None:
        QMessageBox.information(
            self,
            "Session Select",
            "Session Select dialog is the next implementation step.\n\n"
            "Until then, no session is loaded; sidebar tools stay disabled.",
        )

    def _show_console_placeholder(self) -> None:
        QMessageBox.information(
            self,
            "View Console",
            "Console capture / log viewer is not wired yet.",
        )

    def _toggle_theme(self) -> None:
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        apply_theme(self, THEMES[self.current_theme])
        self.sidebar.reflect_theme(self.current_theme)

    def _on_sidebar_tool(self, key: str) -> None:
        if not self._has_session:
            return
        if key == "verify":
            self.workspace.show_verify()
        elif key == "select_run":
            self.workspace.show_select_run()
        elif key == "view_output":
            self.workspace.show_view_output()
        elif key == "generate":
            QMessageBox.information(
                self,
                "Generate Config",
                "Generate Config will open as a modal dialog (next steps).",
            )
