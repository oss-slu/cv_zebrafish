"""Short-lived busy popup for quick blocking operations (e.g. heatmap wipe)."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget


class BriefBusyDialog(QDialog):
    """Small frameless dialog with an indeterminate bar for brief synchronous work."""

    def __init__(self, parent: QWidget | None, message: str) -> None:
        super().__init__(parent)
        self.setObjectName("BriefBusyDialog")
        self.setWindowFlags(
            Qt.Dialog | Qt.FramelessWindowHint | Qt.CustomizeWindowHint
        )
        self.setModal(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._shown_at = 0.0
        self._minimum_ms = 350

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._label = QLabel(message)
        self._label.setObjectName("BriefBusyLabel")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self._bar = QProgressBar()
        self._bar.setObjectName("BriefBusyBar")
        self._bar.setRange(0, 0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        layout.addWidget(self._bar)
        self.adjustSize()

    def set_message(self, message: str) -> None:
        self._label.setText(message)

    def show_busy(self) -> None:
        self._shown_at = time.monotonic()
        self.show()
        QApplication.processEvents()

    def finish(self, *, minimum_ms: int | None = None) -> None:
        """Hide after optional minimum visible time so the popup is perceptible."""
        min_ms = self._minimum_ms if minimum_ms is None else minimum_ms
        elapsed_ms = int((time.monotonic() - self._shown_at) * 1000)
        remaining = max(0, min_ms - elapsed_ms)
        if remaining > 0:
            QTimer.singleShot(remaining, self.accept)
        else:
            self.accept()


def show_brief_busy_dialog(
    parent: QWidget | None,
    message: str,
    *,
    minimum_ms: int = 350,
) -> BriefBusyDialog:
    """Create, show, and return a brief busy dialog; call ``finish()`` when work completes."""
    dlg = BriefBusyDialog(parent, message)
    dlg._minimum_ms = minimum_ms
    dlg.show_busy()
    return dlg


@contextmanager
def brief_busy_scope(
    parent: QWidget | None,
    message: str,
    *,
    minimum_ms: int = 350,
) -> Iterator[BriefBusyDialog]:
    """Context manager wrapper around :func:`show_brief_busy_dialog`."""
    dlg = show_brief_busy_dialog(parent, message, minimum_ms=minimum_ms)
    try:
        yield dlg
    finally:
        dlg.finish(minimum_ms=minimum_ms)
