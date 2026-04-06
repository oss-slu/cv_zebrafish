"""Window-modal console: shows buffered stderr text (see MainShellWindow tee)."""

from __future__ import annotations

from collections import deque

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from styles.themes import THEMES, apply_theme

from ui.components.chrome_separators import horizontal_separator
from ui.components.dialog_title_bar import DialogTitleBar


class ConsoleViewerDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        chunks: deque[str],
        theme_name: str,
        *,
        toast_messages: deque[str] | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("ConsoleViewerDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(520, 360)
        self.resize(640, 420)
        self._chunks = chunks
        self._toast_messages = toast_messages

        apply_theme(self, THEMES[theme_name])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, "Console", self))
        outer.addWidget(horizontal_separator())

        body = QWidget()
        body.setObjectName("ConsoleViewerBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        bl = QVBoxLayout(body)
        bl.setContentsMargins(10, 10, 10, 10)
        self._plain = QPlainTextEdit()
        self._plain.setObjectName("ConsoleViewerPlain")
        self._plain.setReadOnly(True)
        bl.addWidget(self._plain)
        outer.addWidget(body, stretch=1)

        row = QHBoxLayout()
        row.addStretch(1)
        ref = QPushButton("Refresh")
        ref.setCursor(Qt.PointingHandCursor)
        ref.clicked.connect(self._reload)
        row.addWidget(ref)
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        outer.addLayout(row)

        self._reload()

    def _reload(self) -> None:
        parts: list[str] = []
        if self._toast_messages and len(self._toast_messages) > 0:
            parts.append("— Toast / in-app messages —\n")
            parts.append("".join(self._toast_messages))
            parts.append("\n\n— stderr —\n")
        parts.append("".join(self._chunks))
        self._plain.setPlainText("".join(parts))
        cur = self._plain.textCursor()
        cur.movePosition(QTextCursor.End)
        self._plain.setTextCursor(cur)
