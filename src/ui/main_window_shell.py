"""
New application shell: single top bar (logo, inline File / Help, window controls), sidebar, workspace.

Uses Qt.FramelessWindowHint. On Windows, WM_NCHITTEST enables native edge resize for frameless windows.
"""

import ctypes
import sys
from collections import deque
from datetime import datetime

import pandas as pd

from src.core.calculations.cancelled import CalculationAborted
from PyQt5.QtCore import QEvent, QPoint, QTimer, QSize, Qt, QThread
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

from app_platform.paths import app_stylesheet_path, sessions_dir
from app_platform.session_registry import sync_registry_with_disk, touch_last_opened
from app_platform.ui_preferences import UiPreferences, load_ui_preferences
from styles.themes import THEMES, application_tooltip_stylesheet, apply_error_toast_theme, apply_theme
from styles.ui_scale import scale_stylesheet, set_ui_scale_factor
from session.session import load_session_from_json

from ui.components.chrome_separators import horizontal_separator
from ui.components.console_dialog import ConsoleViewerDialog
from ui.components.error_toast import ErrorToast
from ui.components.custom_title_bar import CustomTitleBar
from ui.components.shell_menus import build_file_help_menus
from ui.components.sidebar_tools import SidebarTools
from ui.main_panels.graph_viewer_widget import (
    count_figures_in_folder_runs,
    count_figures_in_graph_dict,
    get_graph_names_to_build,
)
from ui.main_panels.workspace_widget import WorkspaceWidget
from ui.popup_panels.generate_config_dialog import GenerateConfigDialog
from ui.popup_panels.session_select_dialog import SessionSelectDialog
from ui.workers.folder_graph_save_worker import FolderGraphSaveWorker
from ui.workers.folder_pipeline_worker import FolderPipelineWorker

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
    def __init__(self, ui_prefs: UiPreferences | None = None):
        super().__init__()
        self.setObjectName("MainShellWindow")
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("CV Zebrafish")
        self.setMinimumSize(QSize(900, 510))
        self.resize(QSize(1000, 700))

        self._ui_prefs = ui_prefs if ui_prefs is not None else load_ui_preferences()
        th = self._ui_prefs.theme
        self.current_theme = th if th in THEMES else "dark"
        apply_theme(self, THEMES[self.current_theme])

        self._has_session = False
        self.current_session = None
        self._verify_last_csv_path = None
        self._calculation_has_run = False
        self._view_output_sidebar_unlocked = False

        self._folder_thread: QThread | None = None
        self._folder_worker: FolderPipelineWorker | None = None
        self._folder_save_thread: QThread | None = None
        self._folder_save_worker: FolderGraphSaveWorker | None = None
        self._folder_save_ctx: dict | None = None

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
        self.sidebar.settings_requested.connect(self._open_settings)
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
        """
        Resume to the most advanced *available* workspace state:
          - no CSVs yet -> Verify
          - CSVs but no configs -> Verify + open Generate Config dialog
          - any config present (including prior graph runs) -> Select & Run
        """
        s = self.current_session
        if s is None:
            return

        if s.length() == 0:
            self._show_verify_panel(persist=False)
            return

        has_any_config = any(bool(configs) for configs in (s.csvs or {}).values())

        if not has_any_config:
            # User has uploaded CSVs but not attached/generated a config yet.
            self._show_verify_panel(persist=False)
            self._open_generate_config_dialog()
            return

        # Any existing config means Select & Run is available. This also covers
        # sessions that previously reached graph generation without auto-loading graphs.
        last_csv = getattr(s, "last_csv_path", None)
        last_cfg = getattr(s, "last_config_path", None)
        if last_csv and last_cfg:
            config_scene = self.workspace.select_run_panel.selection
            config_scene.set_selected_paths(last_csv, last_cfg)
        self._show_select_run_panel(persist=False)
        self._persist_last_scene("Select Configuration")

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

    def _calculation_cancelled(self) -> bool:
        return self.workspace.select_run_panel.selection.is_calculation_cancelled()

    def _deferred_view_output_after_ready(self, config_scene) -> None:
        """After 100% 'Ready', hold ~1s so the label is readable, then open Graphs and clear the bar."""
        def _go() -> None:
            self._persist_calculation_succeeded()
            self._show_view_output_panel()
            config_scene.set_progress(0, 0, "")

        QTimer.singleShot(1000, _go)

    def _handle_calculation_data(self, data) -> None:
        """Orchestrate graph build after Run Calculation. Progress is monotonic; 100% only when UI is ready (#91)."""
        config_scene = self.workspace.select_run_panel.selection
        if data is None:
            config_scene.finish_calculation_run()
            return
        graphs_scene = self.workspace.view_output_panel.viewer
        is_cancel = self._calculation_cancelled

        if data and isinstance(data, dict) and data.get("csv_files"):
            self._start_folder_pipeline_async(data)
            return

        try:
            self._run_single_csv_calculation(
                data, config_scene, graphs_scene, is_cancel
            )
        except CalculationAborted:
            config_scene.set_progress(0, 0, "")
        finally:
            config_scene.finish_calculation_run()

    def _start_folder_pipeline_async(self, data: dict) -> None:
        config_scene = self.workspace.select_run_panel.selection
        self._cleanup_folder_worker_handles()
        config_scene.set_progress(0, 0, "")
        config_scene.start_progress_run()

        ce = config_scene.calculation_cancel_event()
        th = QThread()
        worker = FolderPipelineWorker(dict(data), ce)
        worker.moveToThread(th)
        self._folder_thread = th
        self._folder_worker = worker

        th.started.connect(worker.run)
        worker.progress.connect(config_scene.set_progress, Qt.QueuedConnection)
        worker.finished.connect(self._on_folder_pipeline_finished, Qt.QueuedConnection)
        worker.failed.connect(self._on_folder_pipeline_failed, Qt.QueuedConnection)
        worker.cancelled.connect(self._on_folder_pipeline_cancelled, Qt.QueuedConnection)
        th.finished.connect(self._on_folder_thread_finished)
        th.start()

    def _on_folder_thread_finished(self) -> None:
        self._folder_thread = None
        if self._folder_worker is not None:
            self._folder_worker.deleteLater()
            self._folder_worker = None

    def _cleanup_folder_save_handles(self) -> None:
        self._folder_save_ctx = None
        if self._folder_save_thread is not None:
            try:
                self._folder_save_thread.quit()
                self._folder_save_thread.wait(3000)
            except Exception:
                pass
        self._folder_save_thread = None
        self._folder_save_worker = None

    def _cleanup_folder_worker_handles(self) -> None:
        if self._folder_thread is not None:
            try:
                self._folder_thread.quit()
                self._folder_thread.wait(3000)
            except Exception:
                pass
        self._folder_thread = None
        self._folder_worker = None
        self._cleanup_folder_save_handles()

    def _on_folder_save_thread_finished(self) -> None:
        self._folder_save_thread = None
        if self._folder_save_worker is not None:
            self._folder_save_worker.deleteLater()
            self._folder_save_worker = None

    def _on_folder_save_progress_tick(
        self, done: int, n: int, detail: str
    ) -> None:
        ctx = self._folder_save_ctx
        if ctx is None:
            return
        if self._calculation_cancelled():
            return
        config_scene = self.workspace.select_run_panel.selection
        step = int(ctx["phase_base"]) + int(done)
        config_scene.set_progress(
            step,
            int(ctx["total_steps"]),
            f"Saving {done}/{n}  —  {detail}",
        )

    def _on_folder_save_finished(self, result: dict, records: object) -> None:
        self._folder_save_ctx = None
        config_scene = self.workspace.select_run_panel.selection
        graphs_scene = self.workspace.view_output_panel.viewer
        if self._calculation_cancelled():
            config_scene.set_progress(0, 0, "")
            config_scene.finish_calculation_run()
            self._cleanup_folder_worker_handles()
            return
        rows = records if isinstance(records, list) else []
        sess = getattr(graphs_scene, "current_session", None)
        if sess is not None:
            for row in rows:
                if isinstance(row, tuple) and len(row) == 4:
                    sess.addFolderGraph(*row)
            try:
                sess.save()
            except Exception:
                pass
        try:
            self._apply_folder_run_after_save(result)
        except Exception:
            config_scene.set_progress(0, 0, "")
            config_scene.finish_calculation_run()
            self._cleanup_folder_worker_handles()

    def _on_folder_save_failed(self, message: str) -> None:
        self._folder_save_ctx = None
        config_scene = self.workspace.select_run_panel.selection
        config_scene.set_progress(0, 0, "")
        self._show_error_toast("Saving graphs failed", message)
        config_scene.finish_calculation_run()
        self._cleanup_folder_worker_handles()

    def _on_folder_save_cancelled(self) -> None:
        self._folder_save_ctx = None
        config_scene = self.workspace.select_run_panel.selection
        config_scene.set_progress(0, 0, "")
        config_scene.finish_calculation_run()
        self._cleanup_folder_worker_handles()

    def _apply_folder_run_after_save(self, result: dict) -> None:
        config_scene = self.workspace.select_run_panel.selection
        graphs_scene = self.workspace.view_output_panel.viewer
        graphs_by_csv = result["graphs_by_csv"]
        results_by_csv = result["results_by_csv"]
        csv_files = result["csv_files"]
        config = result["config"]
        config_path = result["config_path"]
        csv_folder_id = result["csv_folder_id"]
        total_files = result["total_files"]
        total_graphs = result["total_graphs"]
        n_save = count_figures_in_folder_runs(graphs_by_csv)
        total_steps = 2 * total_files + total_graphs + n_save + 2
        step = 2 * total_files + total_graphs + n_save
        step += 1
        config_scene.set_progress(step, total_steps, "Preparing graph viewer…")
        graphs_scene.set_context(
            csv_id=csv_folder_id, config_path=config_path, csv_files=csv_files
        )
        graphs_scene.set_graphs_by_csv(
            graphs_by_csv,
            config=config,
            results_by_csv=results_by_csv,
        )
        step += 1
        config_scene.set_progress(step, total_steps, "Ready")
        config_scene.finish_calculation_run()
        self._deferred_view_output_after_ready(config_scene)

    def _on_folder_pipeline_failed(self, message: str) -> None:
        config_scene = self.workspace.select_run_panel.selection
        config_scene.set_progress(0, 0, "")
        self._show_error_toast("Folder run failed", message)
        config_scene.finish_calculation_run()
        self._cleanup_folder_worker_handles()

    def _on_folder_pipeline_cancelled(self) -> None:
        config_scene = self.workspace.select_run_panel.selection
        config_scene.set_progress(0, 0, "")
        config_scene.finish_calculation_run()
        self._cleanup_folder_worker_handles()

    def _on_folder_pipeline_finished(self, result: dict) -> None:
        config_scene = self.workspace.select_run_panel.selection
        graphs_scene = self.workspace.view_output_panel.viewer
        is_cancel = self._calculation_cancelled

        graphs_by_csv = result["graphs_by_csv"]
        csv_files = result["csv_files"]
        config_path = result["config_path"]
        csv_folder_id = result["csv_folder_id"]
        total_files = result["total_files"]
        total_graphs = result["total_graphs"]

        if is_cancel():
            config_scene.set_progress(0, 0, "")
            config_scene.finish_calculation_run()
            self._cleanup_folder_worker_handles()
            return

        if getattr(graphs_scene, "current_session", None) is None:
            config_scene.set_progress(0, 0, "")
            config_scene.finish_calculation_run()
            self._cleanup_folder_worker_handles()
            return

        n_save = count_figures_in_folder_runs(graphs_by_csv)
        total_steps = 2 * total_files + total_graphs + n_save + 2
        phase_base = 2 * total_files + total_graphs

        self._cleanup_folder_save_handles()

        self._folder_save_ctx = {
            "total_steps": total_steps,
            "phase_base": phase_base,
        }

        session_root = sessions_dir() / graphs_scene.current_session.getName()
        ce = config_scene.calculation_cancel_event()

        th = QThread()
        worker = FolderGraphSaveWorker(
            session_root=session_root,
            csv_folder_id=csv_folder_id,
            csv_files=csv_files,
            config_path=config_path,
            graphs_by_csv=graphs_by_csv,
            cancel_event=ce,
        )
        worker.moveToThread(th)
        self._folder_save_thread = th
        self._folder_save_worker = worker

        th.started.connect(worker.run)
        worker.progress.connect(
            self._on_folder_save_progress_tick,
            Qt.QueuedConnection,
        )
        worker.finished.connect(
            lambda rec: self._on_folder_save_finished(result, rec),
            Qt.QueuedConnection,
        )
        worker.failed.connect(self._on_folder_save_failed, Qt.QueuedConnection)
        worker.cancelled.connect(self._on_folder_save_cancelled, Qt.QueuedConnection)
        th.finished.connect(self._on_folder_save_thread_finished)
        th.start()

    def _run_single_csv_calculation(
        self, data, config_scene, graphs_scene, is_cancel
    ) -> None:
        gcount: int = 0
        if is_cancel():
            raise CalculationAborted()

        if isinstance(data, dict) and data.get("_prebuilt_graphs") is not None:
            graphs = data["_prebuilt_graphs"]
            cfg = data.get("_prebuilt_config")
            if not isinstance(cfg, dict):
                cfg = data.get("config")
            gcount = len(get_graph_names_to_build(data))
        elif data and isinstance(data, dict) and data.get("results_df") is not None:
            names = get_graph_names_to_build(data)
            gcount = len(names)
            if gcount == 0:
                graphs, cfg = graphs_scene.build_graphs_with_progress(
                    data, lambda n, t, g: None, is_cancelled=is_cancel
                )
            else:
                _st = [2 + 2 * gcount + 2]
                config_scene.start_progress_run()
                config_scene.set_progress(2, _st[0], f"0/{gcount} — building graphs")
                def _single_progress(n, total, graph_name: str) -> None:
                    if is_cancel():
                        raise CalculationAborted()
                    config_scene.set_progress(2 + n, _st[0], f"{n}/{total} — {graph_name}")
                    QApplication.processEvents()

                graphs, cfg = graphs_scene.build_graphs_with_progress(
                    data, _single_progress, is_cancelled=is_cancel
                )
        else:
            graphs, cfg = graphs_scene.build_graphs_with_progress(
                data, lambda n, t, g: None, is_cancelled=is_cancel
            )

        if graphs is not None and cfg is not None:
            df = data.get("results_df")
            n_fig = count_figures_in_graph_dict(graphs) if isinstance(graphs, dict) else 0
            st_final = 2 + gcount + n_fig + 2

            def _save_p(i, nt, name):
                if is_cancel():
                    raise CalculationAborted()
                config_scene.set_progress(2 + gcount + i, st_final, f"Saving {i}/{nt}  —  {name}")
                QApplication.processEvents()

            def _prep():
                if is_cancel():
                    raise CalculationAborted()
                config_scene.set_progress(2 + gcount + n_fig + 1, st_final, "Preparing graph viewer…")
                QApplication.processEvents()

            set_graphs_kw: dict = {}
            if gcount > 0:
                set_graphs_kw = {
                    "save_progress": _save_p,
                    "on_preparing_viewer": _prep,
                    "is_cancelled": is_cancel,
                }
            try:
                graphs_scene.set_graphs(
                    graphs,
                    config=cfg,
                    results_df=df if isinstance(df, pd.DataFrame) else None,
                    **set_graphs_kw,
                )
            except CalculationAborted:
                raise
            try:
                graphs_scene.set_context(
                    csv_id=data.get("csv_path") if isinstance(data, dict) else None,
                    config_path=(cfg.get("config_path") if isinstance(cfg, dict) else None),
                    csv_files=None,
                )
            except Exception:
                pass
            QApplication.processEvents()
            if gcount > 0:
                config_scene.set_progress(st_final, st_final, "Ready")
                QApplication.processEvents()
                self._deferred_view_output_after_ready(config_scene)
            else:
                self._persist_calculation_succeeded()
                self._show_view_output_panel()
        else:
            graphs_scene.set_data(data)
            self._view_output_sidebar_unlocked = True
            self._show_view_output_panel()
            self._refresh_sidebar_capabilities()
        if not (graphs is not None and cfg is not None and gcount > 0):
            config_scene.set_progress(0, 0, "")

    def _open_settings(self) -> None:
        from ui.popup_panels.settings_dialog import SettingsDialog

        SettingsDialog(self, self._ui_prefs).exec_()

    def _primary_screen_metrics(self) -> tuple[float, int, int, float]:
        dpi = 96.0
        w, h = 1920, 1080
        dpr = 1.0
        app_inst = QApplication.instance()
        if app_inst is not None:
            scr = app_inst.primaryScreen()
            if scr is not None:
                dpi = float(scr.logicalDotsPerInchX())
                g = scr.availableGeometry()
                w, h = g.width(), g.height()
                dpr = float(scr.devicePixelRatio())
        return dpi, w, h, dpr

    def _apply_prefs_preview(self, prefs: UiPreferences) -> None:
        dpi, w, h, dpr = self._primary_screen_metrics()
        scale = prefs.effective_ui_scale(dpi, w, h, dpr)
        set_ui_scale_factor(scale)
        app_inst = QApplication.instance()
        path = app_stylesheet_path()
        if app_inst is not None and path.is_file():
            base = scale_stylesheet(path.read_text(encoding="utf-8"), scale)
            th_name = prefs.theme if prefs.theme in THEMES else "dark"
            app_inst.setStyleSheet(base + application_tooltip_stylesheet(THEMES[th_name]))
        self.current_theme = prefs.theme if prefs.theme in THEMES else "dark"
        apply_theme(self, THEMES[self.current_theme])
        apply_error_toast_theme(self._error_toast, THEMES[self.current_theme])
        self.sidebar.reflect_theme(self.current_theme)
        self.workspace.select_run_panel.selection.polish_tree_for_theme(self.current_theme)
        self._error_toast.reposition_if_visible()

    def _reapply_ui_preferences(self) -> None:
        self._apply_prefs_preview(self._ui_prefs)

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
