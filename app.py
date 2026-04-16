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

from ui.main_window_shell import MainShellWindow

app = QApplication(sys.argv)
window = MainShellWindow()
window.show()
app.exec()
