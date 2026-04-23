"""Frameless-dialog title row: title + close only (matches main shell chrome; no logo)."""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QToolButton, QWidget

from ui.components.scene_help import create_scene_help_button


class DialogTitleBar(QWidget):
    def __init__(
        self,
        dialog: QDialog,
        title: str,
        parent: QWidget | None = None,
        *,
        help_title: Optional[str] = None,
        help_paragraph: Optional[str] = None,
        help_tips: Optional[Sequence[str]] = None,
    ):
        # help_title is the window name for the help dialog only; the modal title is f"Help - {help_title}".
        super().__init__(parent)
        self.setObjectName("AppTitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._dlg = dialog
        self._drag_anchor: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)

        self._title = QLabel(title)
        self._title.setObjectName("DialogTitleLabel")
        layout.addWidget(self._title, 0, Qt.AlignVCenter)

        layout.addStretch(1)

        if help_title and help_paragraph:
            hb = create_scene_help_button(
                self,
                title=help_title,
                paragraph=help_paragraph,
                tips=tuple(help_tips) if help_tips is not None else None,
            )
            layout.addWidget(hb, 0, Qt.AlignVCenter)

        self._btn_close = QToolButton()
        self._btn_close.setObjectName("TitleChromeClose")
        self._btn_close.setText("\u00d7")
        self._btn_close.setAutoRaise(True)
        self._btn_close.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._btn_close.setFixedSize(52, 40)
        self._btn_close.setCursor(Qt.PointingHandCursor)
        self._btn_close.clicked.connect(self._dlg.reject)
        layout.addWidget(self._btn_close, 0, Qt.AlignVCenter)

        self.setFixedHeight(52)

    def _allow_window_drag(self, pos) -> bool:
        w = self.childAt(pos)
        cur = w
        while cur is not None and cur != self:
            if isinstance(cur, QToolButton):
                return False
            cur = cur.parentWidget()
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._allow_window_drag(event.pos()):
            self._drag_anchor = event.globalPos() - self._dlg.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_anchor is not None:
            self._dlg.move(event.globalPos() - self._drag_anchor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_anchor = None
        super().mouseReleaseEvent(event)
