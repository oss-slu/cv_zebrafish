"""Shared app logo loading (assets/images/fish1.png)."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QLabel

from app_platform.paths import images_dir


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
