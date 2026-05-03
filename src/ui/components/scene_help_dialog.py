"""Themed, frameless help window for scene ⓘ (replaces native QMessageBox so title bar matches dark mode)."""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QDialog, QFrame, QPlainTextEdit, QVBoxLayout, QWidget

from styles.themes import THEMES, apply_theme

from ui.components.chrome_separators import horizontal_separator
from ui.components.dialog_title_bar import DialogTitleBar
from ui.components.scene_help import format_help_body
from ui.platform.frameless_resize import FramelessResizeMixin


def _transient_for_help(start: Optional[QWidget]) -> Optional[QWidget]:
    """Use the nearest parent QDialog (or the shell) so the help window centers and stacks well."""
    w = start
    while w is not None:
        if isinstance(w, QDialog):
            return w
        w = w.parentWidget()
    return start


def _theme_name_from_context(start: Optional[QWidget]) -> str:
    w = start
    while w is not None:
        if hasattr(w, "current_theme"):
            return getattr(w, "current_theme", "dark") or "dark"
        w = w.parentWidget()
    return "dark"


def _frame_title(window_name: str) -> str:
    wn = (window_name or "").strip()
    if wn.lower().startswith("help - "):
        return wn
    return f"Help - {wn}"


class SceneHelpDialog(FramelessResizeMixin, QDialog):
    """
    No OS chrome, no information pixmap — title uses DialogTitleBar (same as other app dialogs).
    Title: ``Help - {window_name}`` (e.g. ``Help - No Session Window``).
    """

    def __init__(
        self,
        requester: Optional[QWidget],
        window_name: str,
        paragraph: str,
        tips: Optional[Sequence[str]] = None,
    ):
        tr = _transient_for_help(requester) or requester
        super().__init__(tr)
        self.setObjectName("SceneHelpDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)

        theme_name = _theme_name_from_context(requester)
        apply_theme(self, THEMES[theme_name])
        title_text = _frame_title(window_name)
        self.setWindowTitle(title_text)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, title_text, self))
        outer.addWidget(horizontal_separator())

        body_wrap = QWidget()
        body_wrap.setObjectName("SceneHelpDialogBody")
        body_wrap.setAttribute(Qt.WA_StyledBackground, True)
        bl = QVBoxLayout(body_wrap)
        bl.setContentsMargins(16, 12, 16, 16)
        bl.setSpacing(0)

        text = QPlainTextEdit()
        text.setObjectName("SceneHelpDialogText")
        text.setReadOnly(True)
        text.setFrameShape(QFrame.NoFrame)
        text.setPlainText(format_help_body(paragraph, tips))
        text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        f = QFont()
        f.setPointSize(10)
        text.setFont(f)
        bl.addWidget(text, 1)
        outer.addWidget(body_wrap, stretch=1)

        self.setMinimumSize(400, 220)
        self.resize(500, 320)
