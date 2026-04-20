from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.components.branding import fish_pixmap


class EmptySessionPanel(QWidget):
    """No session: large fish logo + message; entire area opens Session Select when clicked."""

    open_session_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        layout.addStretch(2)

        self._logo = QLabel()
        self._logo.setPixmap(fish_pixmap(150))
        self._logo.setAlignment(Qt.AlignCenter)
        self._logo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._logo, 0, Qt.AlignHCenter)

        hint = QLabel("+ Load Session")
        hint.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(15)
        hint.setFont(f)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(hint)

        layout.addStretch(3)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_session_requested.emit()
        super().mousePressEvent(event)
