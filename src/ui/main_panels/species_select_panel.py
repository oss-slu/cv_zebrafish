"""Landing page: choose a species before entering a workflow (issue #117)."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.app_platform.species import Species


class SpeciesSelectPanel(QWidget):
    """Species dropdown + Continue button. Emits species_selected(Species)."""

    species_selected = pyqtSignal(Species)

    # Order here is the dropdown order; index 0 is the default (Zebrafish).
    _OPTIONS = (Species.ZEBRAFISH, Species.MOUSE)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        layout.addStretch(2)

        label = QLabel("Species")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        self.species_combo = QComboBox()
        self.species_combo.setObjectName("SpeciesSelectCombo")
        for species in self._OPTIONS:
            self.species_combo.addItem(species.display_name, species)
        self.species_combo.setCurrentIndex(0)  # Zebrafish default (issue requirement)

        # Size the closed box to fit the longest option ("Zebrafish"), not whichever
        # item happens to be current. AdjustToContentsOnFirstShow can otherwise pick
        # a narrower width and clip text when switching selections.
        self.species_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.species_combo.setMinimumContentsLength(
            max(len(s.display_name) for s in self._OPTIONS)
        )
        
        combo_row = QHBoxLayout()
        combo_row.addStretch(1)
        combo_row.addWidget(self.species_combo)
        combo_row.addStretch(1)
        layout.addLayout(combo_row)

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setObjectName("SpeciesSelectContinueButton")
        self.continue_btn.clicked.connect(self._on_continue_clicked)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(self.continue_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        layout.addStretch(3)

        self.species_combo.currentIndexChanged.connect(self._refresh_continue_enabled)
        self._refresh_continue_enabled()

    def current_species(self) -> Optional[Species]:
        """Currently selected species, or None if the combo has no valid selection."""
        return self.species_combo.currentData()

    def _refresh_continue_enabled(self, *_args) -> None:
        # Guard for future options (issue requirement): Continue only enabled
        # when the combo holds a real Species value.
        self.continue_btn.setEnabled(self.current_species() is not None)

    def _on_continue_clicked(self) -> None:
        species = self.current_species()
        if species is not None:
            self.species_selected.emit(species)