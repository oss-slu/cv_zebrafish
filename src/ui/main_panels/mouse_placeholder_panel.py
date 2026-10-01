"""Placeholder landing panel for the mouse workflow (issue #117).

Replace with the real mouse analysis entry point once that issue merges.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class MousePlaceholderPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 30, 40, 30)

        label = QLabel("Mouse workflow coming soon.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)