from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPanel(QWidget):
    """Temporary panel until the real scene is ported from `ui.scenes`."""

    def __init__(self, title: str, detail: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        title_lbl = QLabel(title)
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title_lbl)
        if detail:
            body = QLabel(detail)
            body.setAlignment(Qt.AlignCenter)
            body.setWordWrap(True)
            layout.addWidget(body)
        layout.addStretch(1)
