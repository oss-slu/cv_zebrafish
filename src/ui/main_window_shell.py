"""
New application shell: single top bar (logo, inline File / Help, window controls), sidebar, workspace.

Uses Qt.FramelessWindowHint; legacy flow remains in ui.scenes.MainWindow.
On Windows, WM_NCHITTEST enables native edge resize for frameless windows.
"""

import ctypes
import sys
from pathlib import Path

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser
from PyQt5.QtCore import QEvent, QPoint, QSize, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QMessageBox,
    QShortcut,
    QVBoxLayout,
    QWidget,
)
from src.ui.scenes.GraphViewerScene import get_graph_names_to_build

from styles.themes import THEMES, apply_theme
from session.session import load_session_from_json

from ui.components.chrome_separators import horizontal_separator
from ui.components.custom_title_bar import CustomTitleBar
from ui.components.sidebar_tools import SidebarTools
from ui.main_panels.workspace_widget import WorkspaceWidget
from ui.popup_panels.generate_config_dialog import GenerateConfigDialog
from ui.popup_panels.session_select_dialog import SessionSelectDialog

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
        self.current_session = None
        self._verify_last_csv_path = None
        self._calculation_has_run = False

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

        v = self.workspace.verify_panel.verify
        v.csv_selected.connect(self._on_verify_csv_selected)
        v.csv_folder_selected.connect(self._on_verify_folder_selected)
        v.json_selected.connect(self._on_verify_json_selected)
        v.generate_json_requested.connect(self._on_verify_generate_json_requested)

        self.workspace.select_run_panel.selection.data_generated.connect(
            self._handle_calculation_data
        )

        self.sidebar.reflect_theme(self.current_theme)

        self._apply_session_state()
        self.workspace.select_run_panel.selection.polish_tree_for_theme(self.current_theme)

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
        console_act.triggered.connect(self._show_console_temp_placeholder)
        help_menu.addAction(console_act)

        return file_menu, help_menu

    def _show_console_temp_placeholder(self) -> None:
        """Temporary until stderr/log capture is wired (see UI rework spec)."""
        QMessageBox.information(
            self,
            "View Console",
            "Console capture / log viewer is not wired yet.",
        )

    def _apply_session_state(self) -> None:
        if not self._has_session:
            self.workspace.show_empty()
            self.sidebar.apply_session_capabilities(False, False, False)
        else:
            self._refresh_sidebar_capabilities()

    def _refresh_sidebar_capabilities(self) -> None:
        if not self._has_session or self.current_session is None:
            self.sidebar.apply_session_capabilities(False, False, False)
            return
        has_csv = self.current_session.length() > 0
        self.sidebar.apply_session_capabilities(
            True,
            has_csv,
            self._calculation_has_run,
        )

    def _on_open_session(self) -> None:
        dlg = SessionSelectDialog(self)
        if dlg.exec_() != QDialog.Accepted or not dlg.selected_path:
            return
        self._load_session_from_path(dlg.selected_path)

    def _load_session_from_path(self, json_path: str) -> None:
        try:
            self.current_session = load_session_from_json(json_path)
        except ValueError as e:
            QMessageBox.warning(self, "Session error", str(e))
            return
        self._has_session = True
        base = "CV Zebrafish"
        name = self.current_session.getName()
        self.setWindowTitle(f"{base} — {name}" if name else base)
        self._verify_last_csv_path = getattr(self.current_session, "last_csv_path", None)
        if self.current_session.length() == 0:
            self._calculation_has_run = False
        else:
            ran = bool(getattr(self.current_session, "calculation_has_run", False))
            self._calculation_has_run = ran or self.current_session.has_saved_graph_assets()
        self._apply_session_state()
        self._broadcast_session_to_panels()
        self._resume_workspace_from_session()

    def _broadcast_session_to_panels(self) -> None:
        """Push ``current_session`` into embedded legacy scenes (same as MainWindow.broadcastSession)."""
        if self.current_session is None:
            return
        self.workspace.select_run_panel.selection.load_session(self.current_session)
        self.workspace.select_run_panel.selection.polish_tree_for_theme(self.current_theme)
        self.workspace.view_output_panel.viewer.load_session(self.current_session)

    def _resume_workspace_from_session(self) -> None:
        """Open the panel matching persisted ``last_scene`` without rewriting it (see ``persist``)."""
        s = self.current_session
        if s is None:
            return

        if s.length() == 0:
            self._show_verify_panel(persist=False)
            return

        known = {"Verify", "Generate Config", "Select Configuration", "Graphs"}
        target = getattr(s, "last_scene", None) or "Verify"
        if target == "Landing" or target not in known:
            target = "Verify"

        # Graphs panel restores PNG/HTML paths from session only; no automatic recalculation.
        if target == "Graphs":
            self._show_view_output_panel(persist=False)
            return

        if target in ("Verify", "Generate Config"):
            self._show_verify_panel(persist=False)
        elif target == "Select Configuration":
            self._show_select_run_panel(persist=False)

    def _handle_calculation_data(self, data) -> None:
        """Orchestrate graph build after Run Calculation (mirrors MainWindow.handle_data)."""
        if data is None:
            return
        config_scene = self.workspace.select_run_panel.selection
        graphs_scene = self.workspace.view_output_panel.viewer

        def progress_callback(n, total, graph_name):
            config_scene.set_progress(n, total, graph_name)

        if data and isinstance(data, dict) and data.get("csv_files"):
            csv_files = list(data.get("csv_files") or [])
            config = data.get("config") or {}
            config_path = data.get("config_path") or (
                config.get("config_path") if isinstance(config, dict) else None
            )
            csv_folder_id = data.get("csv_folder")
            if not csv_files or not isinstance(config, dict):
                QMessageBox.warning(self, "Bad Input", "Folder payload is missing CSV files or config.")
                return
            if not csv_folder_id or not config_path:
                QMessageBox.warning(self, "Bad Input", "Folder payload is missing folder id or config path.")
                return

            results_by_csv = {}
            parsed_by_csv = {}
            total_files = len(csv_files)
            for idx, csv_path in enumerate(csv_files, start=1):
                config_scene.set_progress(idx, total_files, f"Calculating: {Path(csv_path).name}")
                try:
                    parsed_points = parser.parse_dlc_csv(csv_path, config)
                    results_df = calculations.run_calculations(parsed_points, config)
                except Exception as exc:
                    config_scene.set_progress(0, 0, "")
                    QMessageBox.warning(self, "Calculation Failed", f"Failed on {csv_path}:\n{exc}")
                    return
                results_by_csv[csv_path] = results_df
                parsed_by_csv[csv_path] = parsed_points

            total_graphs = 0
            file_payloads = []
            for csv_path in csv_files:
                payload = {
                    "results_df": results_by_csv[csv_path],
                    "config": config,
                    "csv_path": csv_path,
                    "parsed_points": parsed_by_csv[csv_path],
                }
                names = get_graph_names_to_build(payload)
                total_graphs += len(names)
                file_payloads.append((csv_path, payload))

            if total_graphs <= 0:
                config_scene.set_progress(0, 0, "")
                QMessageBox.warning(self, "No Graphs", "No graphs were requested or available for this config.")
                return

            graphs_by_csv = {}
            done = 0

            for csv_path, payload in file_payloads:
                def progress_callback2(_n, _total, graph_name, _csv=csv_path):
                    nonlocal done
                    done += 1
                    config_scene.set_progress(done, total_graphs, f"{Path(_csv).name} — {graph_name}")

                graphs, _cfg = graphs_scene.build_graphs_with_progress(payload, progress_callback2)
                if graphs is None:
                    continue
                graphs_by_csv[csv_path] = graphs

            if not graphs_by_csv:
                config_scene.set_progress(0, 0, "")
                QMessageBox.warning(self, "No Graphs", "Graphs could not be generated for this folder.")
                return

            try:
                graphs_scene.save_folder_graphs(
                    csv_folder_id=csv_folder_id,
                    csv_files=csv_files,
                    config_path=config_path,
                    graphs_by_csv=graphs_by_csv,
                    config=config,
                )
            except Exception:
                pass

            graphs_scene.set_context(csv_id=csv_folder_id, config_path=config_path, csv_files=csv_files)
            graphs_scene.set_graphs_by_csv(graphs_by_csv, config=config)
            self._calculation_has_run = True
            try:
                if self.current_session is not None:
                    self.current_session.calculation_has_run = True
                    self.current_session.save()
            except Exception:
                pass
            self._show_view_output_panel()
            config_scene.set_progress(0, 0, "")
            self._refresh_sidebar_capabilities()
            return

        if data and isinstance(data, dict) and data.get("results_df") is not None:
            names = get_graph_names_to_build(data)
            total = len(names)
            if total > 0:
                config_scene.set_progress(0, total, "Loading graphs...")
        graphs, cfg = graphs_scene.build_graphs_with_progress(data, progress_callback)

        if graphs is not None and cfg is not None:
            config_scene.set_progress(len(graphs), len(graphs), "Loading graphs...")
            QApplication.processEvents()
            graphs_scene.set_graphs(graphs, config=cfg)
            try:
                graphs_scene.set_context(
                    csv_id=data.get("csv_path") if isinstance(data, dict) else None,
                    config_path=(cfg.get("config_path") if isinstance(cfg, dict) else None),
                    csv_files=None,
                )
            except Exception:
                pass
            self._calculation_has_run = True
            try:
                if self.current_session is not None:
                    self.current_session.calculation_has_run = True
                    self.current_session.save()
            except Exception:
                pass
            self._show_view_output_panel()
        else:
            graphs_scene.set_data(data)
            self._show_view_output_panel()
        config_scene.set_progress(0, 0, "")
        self._refresh_sidebar_capabilities()

    def _toggle_theme(self) -> None:
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        apply_theme(self, THEMES[self.current_theme])
        self.sidebar.reflect_theme(self.current_theme)
        self.workspace.select_run_panel.selection.polish_tree_for_theme(self.current_theme)

    def _persist_last_scene(self, scene_name: str) -> None:
        if self.current_session is None:
            return
        self.current_session.last_scene = scene_name
        try:
            self.current_session.save()
        except Exception:
            pass

    def _show_verify_panel(self, persist: bool = True) -> None:
        if persist:
            self._persist_last_scene("Verify")
        self.workspace.show_verify()

    def _show_select_run_panel(self, persist: bool = True) -> None:
        if persist:
            self._persist_last_scene("Select Configuration")
        self.workspace.show_select_run()

    def _show_view_output_panel(self, persist: bool = True) -> None:
        if persist:
            self._persist_last_scene("Graphs")
        self.workspace.show_view_output()

    def _on_verify_csv_selected(self, csv_path: str) -> None:
        if not self.current_session:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return
        self._verify_last_csv_path = csv_path
        if not self.current_session.checkExists(csv_path=csv_path):
            self.current_session.addCSV(csv_path)
            self.current_session.save()
        self._refresh_sidebar_capabilities()

    def _on_verify_folder_selected(self, folder_path: str, csv_files) -> None:
        if not self.current_session:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return
        try:
            files = list(csv_files or [])
        except Exception:
            files = []
        if not folder_path or not files:
            QMessageBox.warning(
                self,
                "Invalid Folder",
                "No CSV files were provided for this folder.",
            )
            return
        try:
            self.current_session.addCSVFolder(folder_path, files)
            self.current_session.save()
        except Exception as exc:
            QMessageBox.warning(self, "Folder Error", f"Failed to add folder to session:\n{exc}")
            return
        self._refresh_sidebar_capabilities()

    def _on_verify_json_selected(self, json_path: str) -> None:
        if not self.current_session:
            QMessageBox.warning(self, "No Session", "Create or load a session first.")
            return
        if not self._verify_last_csv_path:
            QMessageBox.warning(
                self,
                "Upload CSV First",
                "Upload a CSV before adding a JSON config.",
            )
            return
        csv_path = self._verify_last_csv_path
        if not self.current_session.checkExists(csv_path=csv_path, config_path=json_path):
            self.current_session.addConfigToCSV(csv_path, json_path)
            self.current_session.save()
        self._refresh_sidebar_capabilities()

    def _open_generate_config_dialog(self) -> None:
        if not self.current_session:
            QMessageBox.warning(
                self,
                "No Session",
                "Create or load a session first.",
            )
            return
        dlg = GenerateConfigDialog(self, self.current_session)
        if dlg.exec_() == QDialog.Accepted:
            self._broadcast_session_to_panels()
            self._show_select_run_panel()
            self._refresh_sidebar_capabilities()

    def _on_verify_generate_json_requested(self) -> None:
        self._open_generate_config_dialog()

    def _on_sidebar_tool(self, key: str) -> None:
        if not self._has_session:
            return
        if key == "verify":
            self._show_verify_panel()
        elif key == "select_run":
            self._show_select_run_panel()
        elif key == "view_output":
            self._show_view_output_panel()
        elif key == "generate":
            self._open_generate_config_dialog()
