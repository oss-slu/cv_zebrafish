"""Placeholder landing panel for the mouse workflow (issue #117).

Replace with the real mouse analysis entry point once that issue merges.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class MousePlaceholderPanel(QWidget):
    back_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        label = QLabel("Mouse workflow coming soon.")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("MousePlaceholderBackButton")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.back_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
