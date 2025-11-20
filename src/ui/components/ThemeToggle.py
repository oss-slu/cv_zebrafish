from PyQt5.QtWidgets import QWidget, QPushButton
from PyQt5.QtCore import Qt

class ThemeToggle(QWidget):
    def __init__(self, parent=None, on_toggle=None):
        super().__init__(parent)
        self.on_toggle = on_toggle

        # Make widget transparent container
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(60, 60)

        # Create the round button
        self.button = QPushButton("☾", self)
        self.button.setFixedSize(50, 50)
        self.button.move(5, 5)
        self.button.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border-radius: 25px;
                font-size: 22px;
            }
            QPushButton:hover {
                background-color: #666;
            }
        """)

        self.button.clicked.connect(self._clicked)

        # Float above all widgets
        self.raise_()

    def _clicked(self):
        if self.on_toggle:
            self.on_toggle()

    def reposition(self):
        """Position at bottom-right of parent window"""
        if not self.parent():
            return
        pw = self.parent().width()
        ph = self.parent().height()
        self.move(pw - self.width() - 15, ph - self.height() - 15)


    def resizeEvent(self, event):
        # Reposition automatically when the window resizes
        self.reposition()
        return super().resizeEvent(event)
