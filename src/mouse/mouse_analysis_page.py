"""Mouse Analysis page: structure only, no analysis logic yet (issue #118).

Follows the zebrafish flow in two steps:

1. Load step: large mouse logo + "+ Load DLC File"; clicking anywhere opens the
   DeepLabCut file picker (same pattern as the zebrafish empty-session panel).
2. Analysis step: header (title + Back), DeepLabCut input row, parameters
   placeholder, results/graphs placeholder.

Integration points are marked with ``TODO(#118-followup)`` so they are easy to
find when the mouse dataset and measurements are confirmed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app_platform.paths import images_dir
from styles.ui_scale import scaled_px
from ui.components.branding import mouse_pixmap
from ui.components.scene_help import create_scene_help_button

UPLOAD_ICON = images_dir() / "upload-button.png"

# DeepLabCut writes pose estimates as .h5 (default) and optionally .csv.
DLC_FILE_FILTER = "DeepLabCut output (*.h5 *.csv);;HDF5 (*.h5);;CSV (*.csv)"

_HELP_PARAGRAPH = (
    "To start a mouse analysis: click anywhere on the load screen, or click Upload DLC File, "
    "and pick the DeepLabCut output (.h5 or .csv) for your video. "
    "Parameters and results are not available yet and will appear here in a future update. "
    "Click Back to return to species selection."
)


def _back_button(object_name: str) -> QPushButton:
    btn = QPushButton("Back")
    btn.setObjectName(object_name)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setToolTip("Return to species selection")
    return btn


class MouseLoadPanel(QWidget):
    """No file yet: large mouse logo + message; entire area opens the DLC file picker when clicked."""

    load_requested = pyqtSignal()
    back_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.back_button = _back_button("MouseLoadBackButton")
        self.back_button.clicked.connect(self.back_requested.emit)
        top.addWidget(self.back_button, 0, Qt.AlignLeft | Qt.AlignTop)
        top.addStretch(1)
        top.addWidget(
            create_scene_help_button(self, title="Mouse Analysis", paragraph=_HELP_PARAGRAPH),
            0,
            Qt.AlignRight | Qt.AlignTop,
        )
        layout.addLayout(top)

        layout.addStretch(2)

        self.logo = QLabel()
        self.logo.setObjectName("MouseLoadLogo")
        self.logo.setPixmap(mouse_pixmap(150))
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.logo, 0, Qt.AlignHCenter)

        hint = QLabel("+ Load DLC File")
        hint.setAlignment(Qt.AlignCenter)
        f = QFont()
        f.setPointSize(15)
        hint.setFont(f)
        hint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(hint)

        layout.addStretch(3)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.load_requested.emit()
        super().mousePressEvent(event)


class MouseAnalysisPage(QWidget):
    """Placeholder mouse workflow page. Emits back_requested when Back is clicked."""

    back_requested = pyqtSignal()
    dlc_file_selected = pyqtSignal(str)

    IDX_LOAD = 0
    IDX_ANALYSIS = 1

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dlc_path: Optional[Path] = None

        self.load_panel = MouseLoadPanel()
        self.load_panel.load_requested.connect(self.select_dlc_file)
        self.load_panel.back_requested.connect(self._on_back)

        self._stack = QStackedWidget()
        self._stack.addWidget(self.load_panel)
        self._stack.addWidget(self._build_analysis_view())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._stack)

    def current_step(self) -> int:
        return self._stack.currentIndex()

    def reset(self) -> None:
        """Clear the selected file and return to the load step."""
        self._dlc_path = None
        self.dlc_path_field.clear()
        self.dlc_path_field.setToolTip("")
        self._stack.setCurrentIndex(self.IDX_LOAD)

    def _on_back(self) -> None:
        # Start fresh next time Mouse is chosen, like a new zebrafish session.
        self.reset()
        self.back_requested.emit()

    # ----- analysis step -----

    def _build_analysis_view(self) -> QScrollArea:
        inner = QWidget()
        inner.setObjectName("MouseAnalysisInner")
        main_layout = QVBoxLayout(inner)
        mg = scaled_px(40)
        vs = scaled_px(30)
        main_layout.setContentsMargins(mg, vs, mg, vs)
        main_layout.setSpacing(scaled_px(20))

        main_layout.addLayout(self._build_header())
        main_layout.addLayout(self._build_input_row())
        main_layout.addWidget(self._build_parameters_group())
        main_layout.addWidget(self._build_results_group(), 1)

        scroll = QScrollArea()
        scroll.setObjectName("MouseAnalysisScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(inner)
        return scroll

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self.back_button = _back_button("MouseAnalysisBackButton")
        self.back_button.clicked.connect(self._on_back)
        row.addWidget(self.back_button, 0, Qt.AlignLeft | Qt.AlignVCenter)

        row.addStretch(1)
        header = QLabel("Mouse Analysis")
        header.setStyleSheet("font-size: 17px; font-weight: bold;")
        row.addWidget(header, 0, Qt.AlignVCenter)
        row.addStretch(1)

        row.addWidget(
            create_scene_help_button(self, title="Mouse Analysis", paragraph=_HELP_PARAGRAPH),
            0,
            Qt.AlignRight | Qt.AlignTop,
        )
        return row

    def _build_input_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        label = QLabel("DeepLabCut File:")
        label.setObjectName("VerifyFieldLabel")  # shared field-label style from app.qss
        row.addWidget(label)

        self.dlc_path_field = QLineEdit()
        self.dlc_path_field.setObjectName("MouseDlcPathField")
        self.dlc_path_field.setPlaceholderText("No DeepLabCut file selected")
        self.dlc_path_field.setReadOnly(True)
        row.addWidget(self.dlc_path_field)

        self.dlc_button = QPushButton("Upload DLC File")
        self.dlc_button.setObjectName("MouseDlcUploadButton")
        self.dlc_button.setIcon(QIcon(str(UPLOAD_ICON)))
        self.dlc_button.setIconSize(QSize(scaled_px(24), scaled_px(24)))
        self.dlc_button.setCursor(Qt.PointingHandCursor)
        self.dlc_button.clicked.connect(self.select_dlc_file)
        row.addWidget(self.dlc_button)
        return row

    def _build_parameters_group(self) -> QGroupBox:
        group = QGroupBox("Parameters (coming soon)")
        group.setObjectName("MouseParametersGroup")
        layout = QVBoxLayout(group)
        # TODO(#118-followup): add mouse measurement parameters once the client
        # confirms which measurements are needed.
        layout.addStretch(1)
        group.setMinimumHeight(scaled_px(100))
        return group

    def _build_results_group(self) -> QGroupBox:
        group = QGroupBox("Results")
        group.setObjectName("MouseResultsGroup")
        layout = QVBoxLayout(group)
        # TODO(#118-followup): replace this label with measurement tables and
        # graphs. Reuse shared graph widgets (ui.components) rather than the
        # zebrafish GraphViewerScene.
        self.results_placeholder = QLabel("Results will appear here")
        self.results_placeholder.setObjectName("MouseResultsPlaceholder")
        self.results_placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.results_placeholder)
        group.setMinimumHeight(scaled_px(240))
        return group

    # ----- input -----

    @property
    def dlc_path(self) -> Optional[Path]:
        """Path of the selected DeepLabCut file, or None if nothing is selected."""
        return self._dlc_path

    def select_dlc_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select DeepLabCut Output", "", DLC_FILE_FILTER
        )
        if not file_path:
            return
        self.set_dlc_file(file_path)

    def set_dlc_file(self, file_path: str) -> None:
        """Show the selected file and move to the analysis step. Parsing is not implemented yet."""
        path = Path(file_path)
        self._dlc_path = path
        # Show only the filename; keep the full path one hover away.
        self.dlc_path_field.setText(path.name)
        self.dlc_path_field.setToolTip(str(path))
        self._stack.setCurrentIndex(self.IDX_ANALYSIS)
        # TODO(#118-followup): parse and validate the DeepLabCut output here once
        # the single-/multi-mouse input formats are documented.
        self.dlc_file_selected.emit(str(path))
