from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from ui.main_panels.empty_session_panel import EmptySessionPanel
from ui.main_panels.pose_studio_panel import PoseStudioPanel
from ui.main_panels.select_run_panel import SelectRunPanel
from ui.main_panels.verify_panel import VerifyPanel
from ui.main_panels.view_output_panel import ViewOutputPanel
from ui.components.widgets.loading_overlay import LoadingOverlay


class WorkspaceWidget(QWidget):
    """
    Hosts main-panel views.
    Indices: 0 empty, 1 verify, 2 select/run, 3 view output, 4 pose studio.
    """

    IDX_EMPTY = 0
    IDX_VERIFY = 1
    IDX_SELECT_RUN = 2
    IDX_VIEW_OUTPUT = 3
    IDX_POSE_STUDIO = 4

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

        self.pose_studio_panel = PoseStudioPanel()
        self._stack.addWidget(self.pose_studio_panel)

        self._loading_overlay = LoadingOverlay(self, title="Loading session")
        self._loading_overlay.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._loading_overlay.resize_to_parent()

    def show_empty(self) -> None:
        self._stack.setCurrentIndex(self.IDX_EMPTY)

    def show_verify(self) -> None:
        self._stack.setCurrentIndex(self.IDX_VERIFY)

    def show_select_run(self) -> None:
        self._stack.setCurrentIndex(self.IDX_SELECT_RUN)

    def show_view_output(self) -> None:
        self._stack.setCurrentIndex(self.IDX_VIEW_OUTPUT)

    def show_pose_studio(self) -> None:
        self._stack.setCurrentIndex(self.IDX_POSE_STUDIO)
        self.pose_studio_panel.on_panel_shown()
