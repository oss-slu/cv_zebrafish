"""View Output main panel: embeds legacy GraphViewerScene until a full restyle."""

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from src.ui.scenes.GraphViewerScene import GraphViewerScene


class ViewOutputPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.viewer = GraphViewerScene()
        layout.addWidget(self.viewer)
