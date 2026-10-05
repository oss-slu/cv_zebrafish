"""Mouse Analysis page: structure only, no analysis logic yet (issue #118).

Sections: header (title + Back), DeepLabCut input picker, parameters
placeholder, results/graphs placeholder. Integration points are marked with
``TODO(#118-followup)`` so they are easy to find when the mouse dataset and
measurements are confirmed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app_platform.paths import images_dir
from styles.ui_scale import scaled_px
from ui.components.scene_help import create_scene_help_button

UPLOAD_ICON = images_dir() / "upload-button.png"

# DeepLabCut writes pose estimates as .h5 (default) and optionally .csv.
DLC_FILE_FILTER = "DeepLabCut output (*.h5 *.csv);;HDF5 (*.h5);;CSV (*.csv)"


class MouseAnalysisPage(QWidget):
    """Placeholder mouse workflow page. Emits back_requested when Back is clicked."""

    back_requested = pyqtSignal()
    dlc_file_selected = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dlc_path: Optional[Path] = None

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

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

    # ----- sections -----

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)

        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("MouseAnalysisBackButton")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.setToolTip("Return to species selection")
        self.back_button.clicked.connect(self.back_requested.emit)
        row.addWidget(self.back_button, 0, Qt.AlignLeft | Qt.AlignVCenter)

        row.addStretch(1)
        header = QLabel("Mouse Analysis")
        header.setStyleSheet("font-size: 17px; font-weight: bold;")
        row.addWidget(header, 0, Qt.AlignVCenter)
        row.addStretch(1)

        row.addWidget(
            create_scene_help_button(
                self,
                title="Mouse Analysis",
                paragraph=(
                    "To start a mouse analysis: click Upload DLC File and pick the DeepLabCut output (.h5 or .csv) for your video. "
                    "Parameters and results are not available yet and will appear here in a future update. "
                    "Click Back to return to species selection."
                ),
            ),
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
        """Show the selected file. Parsing is not implemented yet."""
        path = Path(file_path)
        self._dlc_path = path
        # Show only the filename; keep the full path one hover away.
        self.dlc_path_field.setText(path.name)
        self.dlc_path_field.setToolTip(str(path))
        # TODO(#118-followup): parse and validate the DeepLabCut output here once
        # the single-/multi-mouse input formats are documented.
        self.dlc_file_selected.emit(str(path))
