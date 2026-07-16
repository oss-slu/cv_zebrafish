"""Load a session JSON off the UI thread."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from session.session import load_session_from_json


class SessionLoadWorker(QThread):
    finished_ok = pyqtSignal(object, str)
    failed = pyqtSignal(str)

    def __init__(self, json_path: str, parent=None):
        super().__init__(parent)
        self._json_path = json_path

    def run(self) -> None:
        try:
            session = load_session_from_json(self._json_path)
            self.finished_ok.emit(session, self._json_path)
        except Exception as exc:
            self.failed.emit(str(exc))
