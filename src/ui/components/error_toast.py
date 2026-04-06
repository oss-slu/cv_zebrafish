"""Floating toast: bottom-right near the main window; not system-wide always-on-top."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)


class ErrorToast(QWidget):
    """Top-level tool window: clickable while window-modal dialogs are open; hides when the app loses focus."""

    def __init__(
        self,
        anchor_widget: QWidget | None,
        *,
        on_console_clicked,
        default_timeout_ms: int = 12000,
    ):
        super().__init__(None)
        self._anchor = anchor_widget
        self.setObjectName("ErrorToast")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, False)

        # No WindowStaysOnTopHint — other applications should cover this when you switch away.
        # No WindowDoesNotAcceptFocus — × / console must work while Generate Config (app-modal) is open.
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)

        self._on_console = on_console_clicked
        self._default_timeout_ms = default_timeout_ms

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)

        self._title = QLabel()
        self._title.setObjectName("ErrorToastTitle")
        self._title.setWordWrap(True)
        outer.addWidget(self._title)

        self._body = QLabel()
        self._body.setObjectName("ErrorToastBody")
        self._body.setWordWrap(True)
        self._body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._body.setMaximumWidth(400)
        outer.addWidget(self._body)

        row = QHBoxLayout()
        row.addStretch(1)
        self._btn_console = QPushButton()
        self._btn_console.setObjectName("ErrorToastConsoleBtn")
        self._btn_console.setCursor(Qt.PointingHandCursor)
        self._btn_console.setToolTip("Open console (Help → View Console)")
        if self.style():
            self._btn_console.setIcon(self.style().standardIcon(QStyle.SP_FileDialogDetailedView))
        self._btn_console.clicked.connect(self._on_console_clicked)
        row.addWidget(self._btn_console)

        self._btn_close = QPushButton("×")
        self._btn_close.setObjectName("ErrorToastCloseBtn")
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.setToolTip("Dismiss")
        self._btn_close.clicked.connect(self.hide)
        row.addWidget(self._btn_close)
        outer.addLayout(row)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def _on_console_clicked(self) -> None:
        try:
            self._on_console()
        except Exception:
            pass

    def show_message(self, title: str, body: str, *, timeout_ms: int | None = None) -> None:
        self._timer.stop()
        self._title.setText(title or "Notice")
        self._body.setText(body or "")
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        # Defer raise so z-order wins over an already-visible app-modal dialog (no global topmost).
        QTimer.singleShot(0, self.raise_)
        ms = self._default_timeout_ms if timeout_ms is None else timeout_ms
        if ms > 0:
            self._timer.start(ms)

    def _reposition(self) -> None:
        self.adjustSize()
        w, h = self.width(), self.height()
        m = 16
        screen = QApplication.primaryScreen()
        ag = screen.availableGeometry() if screen else None

        anchor = self._anchor
        if anchor is not None and anchor.isVisible():
            br = anchor.mapToGlobal(anchor.rect().bottomRight())
            x = br.x() - w - m
            y = br.y() - h - m
        elif ag is not None:
            x = ag.right() - w - m + 1
            y = ag.bottom() - h - m + 1
        else:
            x, y = m, m

        if ag is not None:
            x = min(max(ag.left() + m, x), ag.right() - w - m + 1)
            y = min(max(ag.top() + m, y), ag.bottom() - h - m + 1)
        self.move(x, y)

    def reposition_if_visible(self) -> None:
        if self.isVisible():
            self._reposition()
