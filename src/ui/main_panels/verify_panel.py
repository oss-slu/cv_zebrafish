"""Verify Upload main panel: embeds legacy VerifyScene until a full restyle."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from ui.scenes.VerifyScene import VerifyScene


class VerifyPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.verify = VerifyScene()
        layout.addWidget(self.verify)
