"""Arena region picker — main arena + exclusion rows for the Video panel."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.pose.detection.arena import MAIN_ARENA_ID, ArenaRegion


class _RegionRow(QWidget):
    clicked_id = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, region_id: str, label: str, *, deletable: bool, parent=None):
        super().__init__(parent)
        self._region_id = region_id
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        self._btn = QPushButton(label)
        self._btn.setObjectName("ArenaRegionButton")
        self._btn.setCheckable(True)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.clicked.connect(lambda: self.clicked_id.emit(self._region_id))
        lay.addWidget(self._btn, stretch=1)

        self._delete = QToolButton()
        self._delete.setObjectName("SchemaRowDeleteButton")
        self._delete.setText("\u00d7")
        self._delete.setToolTip("Remove this exclusion")
        self._delete.setCursor(Qt.PointingHandCursor)
        self._delete.setVisible(deletable)
        if deletable:
            self._delete.clicked.connect(
                lambda: self.delete_requested.emit(self._region_id)
            )
        lay.addWidget(self._delete, 0)

    def set_selected(self, selected: bool) -> None:
        self._btn.blockSignals(True)
        self._btn.setChecked(selected)
        self._btn.blockSignals(False)


class ArenaRegionList(QWidget):
    """Main arena + exclusions list (bodypart-row style)."""

    region_selected = pyqtSignal(str)
    exclusion_added = pyqtSignal()
    exclusion_removed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ArenaRegionList")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        scroll = QScrollArea()
        scroll.setObjectName("ArenaRegionScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._host = QWidget()
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(0, 0, 0, 0)
        self._host_layout.setSpacing(2)
        scroll.setWidget(self._host)
        root.addWidget(scroll, stretch=1)

        self._add_btn = QPushButton("+ Add new Exclusion")
        self._add_btn.setObjectName("ArenaRegionAddButton")
        self._add_btn.clicked.connect(self.exclusion_added.emit)
        root.addWidget(self._add_btn)

        self._rows: dict[str, _RegionRow] = {}
        self._active_id = MAIN_ARENA_ID
        self._list_enabled = False
        self.set_list_enabled(False)

    def set_list_enabled(self, enabled: bool) -> None:
        self._list_enabled = bool(enabled)
        self.setEnabled(self._list_enabled)
        self._add_btn.setEnabled(self._list_enabled)
        for row in self._rows.values():
            row.setEnabled(self._list_enabled)

    def set_regions(
        self,
        exclusions: list[ArenaRegion],
        *,
        active_id: str,
    ) -> None:
        self._active_id = active_id
        while self._host_layout.count():
            item = self._host_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

        main_row = _RegionRow(MAIN_ARENA_ID, "Main Arena", deletable=False)
        main_row.clicked_id.connect(self.region_selected.emit)
        main_row.set_selected(active_id == MAIN_ARENA_ID)
        main_row.setEnabled(self._list_enabled)
        self._host_layout.addWidget(main_row)
        self._rows[MAIN_ARENA_ID] = main_row

        for exclusion in exclusions:
            row = _RegionRow(exclusion.id, exclusion.name, deletable=True)
            row.clicked_id.connect(self.region_selected.emit)
            row.delete_requested.connect(self.exclusion_removed.emit)
            row.set_selected(active_id == exclusion.id)
            row.setEnabled(self._list_enabled)
            self._host_layout.addWidget(row)
            self._rows[exclusion.id] = row

        self._host_layout.addStretch(1)
