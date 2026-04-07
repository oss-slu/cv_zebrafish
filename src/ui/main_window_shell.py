"""
New application shell: single top bar (logo, inline File / Help, window controls), sidebar, workspace.

Uses Qt.FramelessWindowHint. On Windows, WM_NCHITTEST enables native edge resize for frameless windows.
"""

import ctypes
import sys
from collections import deque
from datetime import datetime
from pathlib import Path

import src.core.calculations.Driver as calculations
import src.core.parsing.Parser as parser
from PyQt5.QtCore import QEvent, QPoint, QSize, Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QShortcut,
    QVBoxLayout,
    QWidget,
)

from styles.themes import THEMES, apply_error_toast_theme, apply_theme
from app_platform.session_registry import sync_registry_with_disk, touch_last_opened
from session.session import load_session_from_json

from ui.components.chrome_separators import horizontal_separator
from ui.components.console_dialog import ConsoleViewerDialog
from ui.components.error_toast import ErrorToast
from ui.components.custom_title_bar import CustomTitleBar
from ui.components.shell_menus import build_file_help_menus
from ui.components.sidebar_tools import SidebarTools
from ui.main_panels.graph_viewer_widget import get_graph_names_to_build
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


class _StderrTee:
    """Keep last stderr chunks for Help → View Console while still printing to the real stderr."""

    __slots__ = ("_real", "_chunks")

    def __init__(self, real, chunks: deque):
        self._real = real
        self._chunks = chunks

    def write(self, s: str) -> int:
        if s is None:
            return 0
        try:
            self._real.write(s)
        except Exception:
            pass
        if s:
            self._chunks.append(s)
        try:
            return len(s)
        except Exception:
            return 0

    def flush(self) -> None:
        try:
            self._real.flush()
        except Exception:
            pass


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
        self._view_output_sidebar_unlocked = False

        self._stderr_chunks: deque[str] = deque(maxlen=400)
        self._toast_messages: deque[str] = deque(maxlen=120)
        self._orig_stderr = sys.stderr
        sys.stderr = _StderrTee(self._orig_stderr, self._stderr_chunks)

        # Merge session JSONs on disk into the machine-local registry; Session Select re-syncs and greys missing paths.
        try:
            sync_registry_with_disk()
        except OSError:
            pass

        shell = QWidget()
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        file_menu, help_menu = build_file_help_menus(
            self,
            on_session_select=self._on_open_session,
            on_view_console=self._open_console_viewer,
        )
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

        self._error_toast = ErrorToast(
            anchor_widget=self,
            on_console_clicked=self._open_console_viewer,
        )
        apply_error_toast_theme(self._error_toast, THEMES[self.current_theme])
        self._error_toast.hide()

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
        self.workspace.select_run_panel.selection.view_output_requested.connect(
            self._on_select_run_view_output
        )
        self.workspace.select_run_panel.selection.generate_config_copy_requested.connect(
            self._on_select_run_generate_copy
        )
        self.workspace.select_run_panel.selection.toast_requested.connect(self._show_error_toast)

        self.sidebar.reflect_theme(self.current_theme)
        self.sidebar.set_active_tool(None)

        self._apply_session_state()
        self.workspace.select_run_panel.selection.polish_tree_for_theme(self.current_theme)

        QShortcut(QKeySequence("Ctrl+W"), self, activated=self.close)

        app_inst = QApplication.instance()
        if app_inst is not None:
            app_inst.applicationStateChanged.connect(self._on_application_state_changed)

    def _on_application_state_changed(self, state: Qt.ApplicationState) -> None:
        """Hide toast when switching to another app so it does not float above the rest of the desktop."""
        if state != Qt.ApplicationActive and self._error_toast.isVisible():
            self._error_toast.hide()

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self._title_bar.update_max_button()
        super().changeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_error_toast", None) is not None:
            self._error_toast.reposition_if_visible()

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

    def _open_console_viewer(self) -> None:
        dlg = ConsoleViewerDialog(
            self,
            self._stderr_chunks,
            self.current_theme,
            toast_messages=self._toast_messages,
        )
        dlg.exec_()

    def _show_error_toast(self, title: str, message: str) -> None:
        self._toast_messages.append(f"{datetime.now():%H:%M:%S} [{title}] {message}\n")
        self._error_toast.show_message(title, message)

    def closeEvent(self, event):
        if getattr(self, "_orig_stderr", None) is not None and sys.stderr is not self._orig_stderr:
            try:
                sys.stderr.flush()
            except Exception:
                pass
            sys.stderr = self._orig_stderr
        super().closeEvent(event)

    def _apply_session_state(self) -> None:
        if not self._has_session:
            self.workspace.show_empty()
            self.sidebar.apply_session_capabilities(False, False, view_output_enabled=False)
            self.sidebar.set_active_tool(None)
        else:
            self._refresh_sidebar_capabilities()

    def _refresh_sidebar_capabilities(self) -> None:
        if not self._has_session or self.current_session is None:
            self.sidebar.apply_session_capabilities(False, False, view_output_enabled=False)
            return
        has_csv = self.current_session.length() > 0
        view_out = (
            self._view_output_sidebar_unlocked
            and has_csv
            and self._calculation_has_run
        )
        self.sidebar.apply_session_capabilities(
            True,
            has_csv,
            view_output_enabled=view_out,
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
            self._show_error_toast("Session error", str(e))
            return
        touch_last_opened(json_path, self.current_session.getName())
        self._view_output_sidebar_unlocked = False
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
        """Push ``current_session`` into workspace panels (Verify / Select & Run / View Output)."""
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

        # Last scene was Graphs: reopen Select & Run only (do not rebuild graphs on startup).
        if target == "Graphs":
            last_csv = getattr(s, "last_csv_path", None)
            last_cfg = getattr(s, "last_config_path", None)
            if last_csv and last_cfg:
                config_scene = self.workspace.select_run_panel.selection
                config_scene.set_selected_paths(last_csv, last_cfg)
                self._show_select_run_panel(persist=False)
                self._persist_last_scene("Select Configuration")
                return
            self._show_verify_panel(persist=False)
            return

        if target in ("Verify", "Generate Config"):
            self._show_verify_panel(persist=False)
        elif target == "Select Configuration":
            self._show_select_run_panel(persist=False)

    def _persist_calculation_succeeded(self) -> None:
        """Set flags, persist session, and refresh sidebar after a successful graph run."""
        self._calculation_has_run = True
        self._view_output_sidebar_unlocked = True
        try:
            if self.current_session is not None:
                self.current_session.calculation_has_run = True
                self.current_session.save()
        except Exception:
            pass
        self._refresh_sidebar_capabilities()

    def _handle_calculation_data(self, data) -> None:
        """Orchestrate graph build after Run Calculation."""
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
                self._show_error_toast("Bad Input", "Folder payload is missing CSV files or config.")
                return
            if not csv_folder_id or not config_path:
                self._show_error_toast("Bad Input", "Folder payload is missing folder id or config path.")
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
                    self._show_error_toast("Calculation Failed", f"Failed on {csv_path}:\n{exc}")
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
                self._show_error_toast("No Graphs", "No graphs were requested or available for this config.")
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
                self._show_error_toast("No Graphs", "Graphs could not be generated for this folder.")
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
            self._persist_calculation_succeeded()
            self._show_view_output_panel()
            config_scene.set_progress(0, 0, "")
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
            self._persist_calculation_succeeded()
            self._show_view_output_panel()
        else:
            graphs_scene.set_data(data)
            self._view_output_sidebar_unlocked = True
            self._show_view_output_panel()
            self._refresh_sidebar_capabilities()
        config_scene.set_progress(0, 0, "")

    def _toggle_theme(self) -> None:
        self.current_theme = "dark" if self.current_theme == "light" else "light"
        apply_theme(self, THEMES[self.current_theme])
        apply_error_toast_theme(self._error_toast, THEMES[self.current_theme])
        self.sidebar.reflect_theme(self.current_theme)
        self.workspace.select_run_panel.selection.polish_tree_for_theme(self.current_theme)
        self._error_toast.reposition_if_visible()

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
        self.sidebar.set_active_tool("verify")

    def _show_select_run_panel(self, persist: bool = True) -> None:
        if persist:
            self._persist_last_scene("Select Configuration")
        self.workspace.show_select_run()
        self.sidebar.set_active_tool("select_run")

    def _show_view_output_panel(self, persist: bool = True) -> None:
        if persist:
            self._persist_last_scene("Graphs")
        self.workspace.show_view_output()
        self.sidebar.set_active_tool("view_output")

    def _on_verify_csv_selected(self, csv_path: str) -> None:
        if not self.current_session:
            self._show_error_toast("No Session", "Create or load a session first.")
            return
        self._verify_last_csv_path = csv_path
        if not self.current_session.checkExists(csv_path=csv_path):
            self.current_session.addCSV(csv_path)
            self.current_session.save()
        self._refresh_sidebar_capabilities()

    def _on_verify_folder_selected(self, folder_path: str, csv_files) -> None:
        if not self.current_session:
            self._show_error_toast("No Session", "Create or load a session first.")
            return
        try:
            files = list(csv_files or [])
        except Exception:
            files = []
        if not folder_path or not files:
            self._show_error_toast("Invalid Folder", "No CSV files were provided for this folder.")
            return
        try:
            self.current_session.addCSVFolder(folder_path, files)
            self.current_session.save()
        except Exception as exc:
            self._show_error_toast("Folder Error", f"Failed to add folder to session:\n{exc}")
            return
        self._refresh_sidebar_capabilities()

    def _on_verify_json_selected(self, json_path: str) -> None:
        if not self.current_session:
            self._show_error_toast("No Session", "Create or load a session first.")
            return
        if not self._verify_last_csv_path:
            self._show_error_toast("Upload CSV First", "Upload a CSV before adding a JSON config.")
            return
        csv_path = self._verify_last_csv_path
        if not self.current_session.checkExists(csv_path=csv_path, config_path=json_path):
            self.current_session.addConfigToCSV(csv_path, json_path)
            self.current_session.save()
        self._refresh_sidebar_capabilities()

    def _open_generate_config_dialog(
        self,
        *,
        prefill_csv_path: str | None = None,
        prefill_json_path: str | None = None,
    ) -> None:
        if not self.current_session:
            self._show_error_toast("No Session", "Create or load a session first.")
            return
        dlg = GenerateConfigDialog(
            self,
            self.current_session,
            prefill_csv_path=prefill_csv_path,
            prefill_json_path=prefill_json_path,
        )
        if dlg.exec_() == QDialog.Accepted:
            self._broadcast_session_to_panels()
            self._show_select_run_panel()
            self._refresh_sidebar_capabilities()

    def _on_select_run_view_output(self, csv_path: str, config_path: str) -> None:
        self._view_output_sidebar_unlocked = True
        self._show_view_output_panel()
        self.workspace.view_output_panel.viewer.show_graphs_for_csv_config(csv_path, config_path)
        self._refresh_sidebar_capabilities()

    def _on_select_run_generate_copy(self, csv_path: str, config_path: str) -> None:
        self._open_generate_config_dialog(
            prefill_csv_path=csv_path,
            prefill_json_path=config_path,
        )

    def _on_verify_generate_json_requested(self) -> None:
        self._open_generate_config_dialog()

    def _warn_sidebar_blocked(self) -> None:
        """System attention sound when a sidebar tool is not available yet."""
        try:
            if sys.platform == "win32":
                ctypes.windll.user32.MessageBeep(0x00000030)  # MB_ICONWARNING
            else:
                QApplication.beep()
        except Exception:
            QApplication.beep()

    def _sidebar_blocked_message(self, tool_key: str) -> str | None:
        """
        First missing prerequisite wins (same order for every tool): session → CSV → graphs.
        Verify only requires a loaded session (where you add CSVs).
        """
        if not self._has_session:
            return "Tool can't be selected. Open Session."
        if tool_key == "verify":
            return None
        sess = self.current_session
        has_csv = sess is not None and sess.length() > 0
        if not has_csv:
            return "CSV hasn't been uploaded."
        if tool_key == "view_output":
            view_ok = self._view_output_sidebar_unlocked and self._calculation_has_run
            if not view_ok:
                return "Graph hasn't been generated."
        return None

    def _on_sidebar_tool(self, key: str) -> None:
        blocked = self._sidebar_blocked_message(key)
        if blocked is not None:
            self._warn_sidebar_blocked()
            self._show_error_toast("Sidebar", blocked)
            return
        if key == "verify":
            self._show_verify_panel()
        elif key == "select_run":
            self._show_select_run_panel()
        elif key == "view_output":
            self._show_view_output_panel()
        elif key == "generate":
            self._open_generate_config_dialog()
