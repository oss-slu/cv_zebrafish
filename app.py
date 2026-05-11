from __future__ import annotations

import datetime as _dt
import sys
import threading
import traceback
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Capture real stderr before MainShellWindow replaces sys.stderr with a tee.
_REAL_STDERR = getattr(sys, "__stderr__", None) or sys.stderr


def _append_crash_log(text: str) -> None:
    try:
        from app_platform.paths import local_data_dir

        log_path = local_data_dir() / "crash.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def _format_crash_banner() -> str:
    return f"\n{'=' * 60}\n{_dt.datetime.now().isoformat()}\n"


def _log_exception(exc_type, exc, tb, *, prefix: str = "") -> None:
    try:
        body = "".join(traceback.format_exception(exc_type, exc, tb))
    except Exception:
        body = f"{exc_type!r}: {exc!r}\n"
    msg = prefix + body
    try:
        _REAL_STDERR.write(msg)
        _REAL_STDERR.flush()
    except Exception:
        pass
    _append_crash_log(_format_crash_banner() + msg)


def _install_crash_hooks() -> None:
    """Full tracebacks for uncaught errors (PyQt often only prints 'Unhandled Python exception')."""

    def _sys_excepthook(exc_type, exc, tb) -> None:
        _log_exception(exc_type, exc, tb)

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):

        def _thread_excepthook(args: threading.ExceptHookArgs) -> None:
            prefix = f"Exception in thread {args.thread.name!r}:\n"
            _log_exception(args.exc_type, args.exc_value, args.exc_traceback, prefix=prefix)

        threading.excepthook = _thread_excepthook


_install_crash_hooks()

from PyQt5.QtWidgets import QApplication

from app_platform.paths import app_stylesheet_path
from app_platform.ui_preferences import load_ui_preferences, sync_prefs_after_launch
from styles.themes import THEMES, application_tooltip_stylesheet
from styles.ui_scale import scale_stylesheet, set_ui_scale_factor

from ui.main_window_shell import MainShellWindow

app = QApplication(sys.argv)

prefs = load_ui_preferences()
_scr = app.primaryScreen()
dpi = float(_scr.logicalDotsPerInchX()) if _scr else 96.0
_geo = _scr.availableGeometry() if _scr else None
_sw, _sh = (_geo.width(), _geo.height()) if _geo is not None else (1920, 1080)
_dpr = float(_scr.devicePixelRatio()) if _scr else 1.0
sync_prefs_after_launch(prefs, dpi, _sw, _sh, _dpr)
scale = prefs.effective_ui_scale(dpi, _sw, _sh, _dpr)
set_ui_scale_factor(scale)

_qss_path = app_stylesheet_path()
if _qss_path.exists():
    _base_qss = scale_stylesheet(_qss_path.read_text(encoding="utf-8"), scale)
    _th = THEMES.get(prefs.theme, THEMES["dark"])
    app.setStyleSheet(_base_qss + application_tooltip_stylesheet(_th))

window = MainShellWindow(ui_prefs=prefs)
window.show()
app.exec()
