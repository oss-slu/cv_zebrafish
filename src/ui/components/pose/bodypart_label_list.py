"""Bodypart list for labeling: counts, selection, add-point mode, rename."""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class BodypartLabelList(QWidget):
    bodypart_selected = pyqtSignal(str)
    bodypart_renamed = pyqtSignal(str, str)
    bodypart_removed = pyqtSignal(str)
    add_point_requested = pyqtSignal()
    clear_all_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BodypartLabelList")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        self._list.setObjectName("BodypartLabelListInner")
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        lay.addWidget(self._list, stretch=1)
        self._add_btn = QPushButton("+ Add point")
        self._add_btn.setObjectName("BodypartAddPointButton")
        self._add_btn.setCheckable(True)
        self._add_btn.clicked.connect(self._on_add_clicked)
        lay.addWidget(self._add_btn)
        self._clear_btn = QPushButton("Clear all points")
        self._clear_btn.clicked.connect(self.clear_all_requested.emit)
        lay.addWidget(self._clear_btn)
        self._remove_btn = QPushButton("Remove bodypart")
        self._remove_btn.setToolTip(
            "Drop this bodypart from the schema (e.g. remove T4 and T5 for a 3-point tail)."
        )
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        lay.addWidget(self._remove_btn)
        self._names: list[str] = []
        self._selected_name: str | None = None

    def _bodypart_name_from_item(self, item: QListWidgetItem) -> str:
        return item.data(Qt.UserRole) or item.text().split()[0]

    def _on_add_clicked(self, checked: bool) -> None:
        if checked:
            self._list.clearSelection()
            self.add_point_requested.emit()
        else:
            self._add_btn.setChecked(False)

    def _on_item_changed(self, current: QListWidgetItem | None, _prev) -> None:
        if current is not None:
            self._add_btn.setChecked(False)
            self._selected_name = self._bodypart_name_from_item(current)
            self.bodypart_selected.emit(self._selected_name)

    def _on_remove_clicked(self) -> None:
        item = self._list.currentItem()
        if item is not None:
            self.bodypart_removed.emit(self._bodypart_name_from_item(item))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        old_name = self._bodypart_name_from_item(item)
        new_name, ok = QInputDialog.getText(
            self,
            "Rename bodypart",
            "New name:",
            text=old_name,
        )
        if ok and new_name and new_name.strip() != old_name:
            self.bodypart_renamed.emit(old_name, new_name.strip())

    def set_bodyparts(
        self,
        names: list[str],
        counts: dict[str, int],
        queue_len: int,
        *,
        selected_name: str | None = None,
    ) -> None:
        self._names = list(names)
        keep = selected_name if selected_name is not None else self._selected_name
        self._selected_name = keep
        self._list.blockSignals(True)
        self._list.clear()
        selected_row = -1
        for name in names:
            c = counts.get(name, 0)
            text = f"{name}  {c}/{queue_len}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, name)
            self._list.addItem(item)
            if keep is not None and name == keep:
                selected_row = self._list.count() - 1
        if selected_row >= 0:
            self._list.setCurrentRow(selected_row)
        elif self._list.count() > 0:
            self._list.setCurrentRow(0)
            self._selected_name = self._bodypart_name_from_item(self._list.currentItem())
        self._list.blockSignals(False)

    def set_add_point_mode(self, active: bool) -> None:
        self._add_btn.blockSignals(True)
        self._add_btn.setChecked(active)
        if active:
            self._list.clearSelection()
            self._list.setCurrentRow(-1)
        elif self._selected_name:
            self.select_bodypart(self._selected_name)
        self._add_btn.blockSignals(False)

    def select_bodypart(self, name: str | None) -> None:
        if not name:
            return
        self._selected_name = name
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item and self._bodypart_name_from_item(item) == name:
                self._list.setCurrentRow(i)
                return
