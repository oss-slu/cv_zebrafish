"""Reusable scene help: small ⓘ control opens a short modal (spec #94)."""

from __future__ import annotations

from typing import Optional, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QToolButton, QWidget


def format_help_body(paragraph: str, tips: Optional[Sequence[str]] = None) -> str:
    t = (paragraph or "").strip()
    if tips:
        t += "\n\nTips:\n" + "\n".join(f"• {s}" for s in tips)
    return t


def show_scene_help(
    parent: QWidget,
    window_name: str,
    paragraph: str,
    tips: Optional[Sequence[str]] = None,
) -> None:
    """Frameless, themed window titled ``Help - {window_name}`` (no OS title bar, no system info icon)."""
    from ui.components.scene_help_dialog import SceneHelpDialog

    SceneHelpDialog(parent, window_name, paragraph, tips).exec_()


def create_scene_help_button(
    parent: QWidget,
    *,
    title: str,
    paragraph: str,
    tips: Optional[Sequence[str]] = None,
) -> QToolButton:
    """ⓘ in the title area; click opens a themed help dialog: title bar shows ``Help - {title}`` (``title`` = window name, e.g. ``No Session Window``)."""
    btn = QToolButton(parent)
    btn.setObjectName("SceneHelpButton")
    btn.setText("ⓘ")
    btn.setToolTip("Help for this screen")
    btn.setAutoRaise(True)
    btn.setCursor(Qt.PointingHandCursor)

    def _on() -> None:
        show_scene_help(parent, title, paragraph, tips)

    btn.clicked.connect(_on)
    return btn
