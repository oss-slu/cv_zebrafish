"""Tab icons for Pose Studio scenes."""

from __future__ import annotations

from PyQt5.QtGui import QIcon

from app_platform.paths import images_dir


def auto_label_tab_icon() -> QIcon:
    """Label-tag + cycle glyph for the Auto Label tab."""
    path = images_dir() / "auto_label_tab.svg"
    if path.is_file():
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return QIcon()
