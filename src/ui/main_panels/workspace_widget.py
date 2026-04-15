from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ui.main_panels.empty_session_panel import EmptySessionPanel
from ui.main_panels.select_run_panel import SelectRunPanel
from ui.main_panels.verify_panel import VerifyPanel
from ui.main_panels.view_output_panel import ViewOutputPanel


class WorkspaceWidget(QWidget):
    """
    Hosts main-panel views. Indices: 0 empty session, 1 verify, 2 select/run, 3 view output.
    """

    IDX_EMPTY = 0
    IDX_VERIFY = 1
    IDX_SELECT_RUN = 2
    IDX_VIEW_OUTPUT = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("WorkspaceMain")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._stack = QStackedWidget()
        self._stack.setObjectName("WorkspaceStack")
        self._stack.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._stack)

        self.empty_panel = EmptySessionPanel()
        self._stack.addWidget(self.empty_panel)

        self.verify_panel = VerifyPanel()
        self._stack.addWidget(self.verify_panel)
        self.select_run_panel = SelectRunPanel()
        self._stack.addWidget(self.select_run_panel)
        self.view_output_panel = ViewOutputPanel()
        self._stack.addWidget(self.view_output_panel)

    def show_empty(self) -> None:
        self._stack.setCurrentIndex(self.IDX_EMPTY)

    def show_verify(self) -> None:
        self._stack.setCurrentIndex(self.IDX_VERIFY)

    def show_select_run(self) -> None:
        self._stack.setCurrentIndex(self.IDX_SELECT_RUN)

    def show_view_output(self) -> None:
        self._stack.setCurrentIndex(self.IDX_VIEW_OUTPUT)
