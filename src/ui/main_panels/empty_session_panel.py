from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.components.branding import fish_pixmap
from ui.components.scene_help import create_scene_help_button


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

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addStretch(1)
        top.addWidget(
            create_scene_help_button(
                self,
                title="No Session Window",
                paragraph=(
                    "To create a session: click anywhere on this screen to open Session Select, or use the File menu and choose Session Select…. "
                    "There you can click + Create New or Upload New to add a new session file, or click a row in the list to open a session you already have. "
                    "After you have a session, add your data and work from the other screens."
                ),
                tips=(
                    "To repoint a missing file, open Session Select, right-click the row, and choose Find location…",
                ),
            ),
            0,
            Qt.AlignRight | Qt.AlignTop,
        )
        layout.addLayout(top)

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
