from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from mouse import MouseAnalysisPage
from ui.main_panels.empty_session_panel import EmptySessionPanel
from ui.main_panels.select_run_panel import SelectRunPanel
from ui.main_panels.species_select_panel import SpeciesSelectPanel
from ui.main_panels.verify_panel import VerifyPanel
from ui.main_panels.view_output_panel import ViewOutputPanel


class WorkspaceWidget(QWidget):
    """
    Hosts main-panel views.
    Indices: 0 species select, 1 empty session, 2 verify, 3 select/run,
    4 view output, 5 mouse analysis.
    """

    IDX_SPECIES = 0
    IDX_EMPTY = 1
    IDX_VERIFY = 2
    IDX_SELECT_RUN = 3
    IDX_VIEW_OUTPUT = 4
    IDX_MOUSE = 5

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

        self.species_panel = SpeciesSelectPanel()
        self._stack.addWidget(self.species_panel)

        self.empty_panel = EmptySessionPanel()
        self._stack.addWidget(self.empty_panel)

        self.verify_panel = VerifyPanel()
        self._stack.addWidget(self.verify_panel)
        self.select_run_panel = SelectRunPanel()
        self._stack.addWidget(self.select_run_panel)
        self.view_output_panel = ViewOutputPanel()
        self._stack.addWidget(self.view_output_panel)

        self.mouse_panel = MouseAnalysisPage()
        self._stack.addWidget(self.mouse_panel)

    def current_panel(self) -> QWidget:
        """The panel currently shown (compare with e.g. ``species_panel``)."""
        return self._stack.currentWidget()

    def show_species(self) -> None:
        self._stack.setCurrentIndex(self.IDX_SPECIES)

    def show_empty(self) -> None:
        self._stack.setCurrentIndex(self.IDX_EMPTY)

    def show_verify(self) -> None:
        self._stack.setCurrentIndex(self.IDX_VERIFY)

    def show_select_run(self) -> None:
        self._stack.setCurrentIndex(self.IDX_SELECT_RUN)

    def show_view_output(self) -> None:
        self._stack.setCurrentIndex(self.IDX_VIEW_OUTPUT)

    def show_mouse(self) -> None:
        self._stack.setCurrentIndex(self.IDX_MOUSE)
