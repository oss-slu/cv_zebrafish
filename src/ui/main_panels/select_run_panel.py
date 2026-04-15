"""Select & Run main panel."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from .select_run_widget import ConfigSelectionScene


class SelectRunPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.selection = ConfigSelectionScene()
        layout.addWidget(self.selection)
