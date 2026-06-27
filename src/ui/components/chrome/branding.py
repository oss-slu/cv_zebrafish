"""Shared app logo loading (assets/images/fish1.png)."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QLabel

from app_platform.paths import images_dir


def view_output_tool_icon(theme_name: str, *, active: bool = True) -> Optional[QIcon]:
    """Same SVG assets as the sidebar View Output tool (``sidebar_view_output_*``)."""
    theme = (theme_name or "dark").lower()
    if theme not in ("dark", "light"):
        theme = "dark"
    state = "active" if active else "inactive"
    p = images_dir() / f"sidebar_view_output_{theme}_{state}.svg"
    if p.is_file():
        ic = QIcon(str(p))
        if not ic.isNull():
            return ic
    legacy = images_dir() / f"sidebar_view_output_{theme}.svg"
    if legacy.is_file():
        ic = QIcon(str(legacy))
        if not ic.isNull():
            return ic
    return None


def fish_pixmap(square_size: int) -> QPixmap:
    """Scaled square pixmap of the zebrafish logo, or a gray fallback."""
    path = images_dir() / "fish1.png"
    pm = QPixmap(str(path))
    if pm.isNull():
        pm = QPixmap(square_size, square_size)
        pm.fill(Qt.gray)
        return pm
    return pm.scaled(square_size, square_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def title_bar_logo_label(size: int = 28) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(fish_pixmap(size))
    lbl.setFixedSize(size, size)
    lbl.setScaledContents(False)
    lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    return lbl
