"""Point and bone schema panel for labeling: rows, selection, add-point and bone tools."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QMimeData, QPoint
from PyQt5.QtGui import QColor, QDrag, QPainter, QPen
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.pose.labeling.schema import bone_display_name


class _DragHandle(QWidget):
    """Triple-bar grip for reordering point rows."""

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self._name = name
        self._press_pos = QPoint()
        self.setObjectName("SchemaDragHandle")
        self.setFixedWidth(20)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip("Drag to reorder")

    def set_enabled(self, enabled: bool) -> None:
        self.setEnabled(enabled)
        self.setCursor(Qt.SizeVerCursor if enabled else Qt.ArrowCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        color = QColor("#8899aa") if self.isEnabled() else QColor("#556677")
        pen = QPen(color, 2, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        cx = self.width() // 2
        for y in (7, 11, 15):
            painter.drawLine(cx - 5, y, cx + 5, y)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._press_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if not self.isEnabled() or not (event.buttons() & Qt.LeftButton):
            return
        if (event.pos() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self._name)
        drag.setMimeData(mime)
        drag.exec_(Qt.MoveAction)


class _PointsDropHost(QWidget):
    """Hosts point rows and accepts drag-drop reorder."""

    reorder_requested = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SchemaPointsHost")
        self.setAcceptDrops(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._drop_index: int | None = None

    def layout(self):
        return self._layout

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if not event.mimeData().hasText():
            return
        self._drop_index = self._index_for_pos(event.pos())
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._drop_index = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        name = event.mimeData().text().strip()
        if name:
            self.reorder_requested.emit(name, self._index_for_pos(event.pos()))
        self._drop_index = None
        self.update()
        event.acceptProposedAction()

    def _index_for_pos(self, pos: QPoint) -> int:
        for i in range(self._layout.count()):
            item = self._layout.itemAt(i)
            widget = item.widget() if item else None
            if widget is None:
                continue
            if pos.y() < widget.geometry().center().y():
                return i
        return max(0, self._layout.count() - 1)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self._drop_index is None:
            return
        y = self._y_for_index(self._drop_index)
        if y is None:
            return
        painter = QPainter(self)
        pen = QPen(QColor("#5a96e6"), 2)
        painter.setPen(pen)
        painter.drawLine(4, y, self.width() - 4, y)

    def _y_for_index(self, index: int) -> int | None:
        if index < self._layout.count():
            widget = self._layout.itemAt(index).widget()
            if widget is not None:
                return widget.geometry().top()
        if self._layout.count() > 0:
            widget = self._layout.itemAt(self._layout.count() - 1).widget()
            if widget is not None:
                return widget.geometry().bottom()
        return 0


class _PointRow(QWidget):
    """One bodypart row: selectable button + delete, optional animated dashed outline."""

    clicked_name = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    rename_requested = pyqtSignal(str)

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SchemaPointRow")
        self._name = name
        self._bone_pulse = False
        self._bone_pick_highlight = False
        self._dash_offset = 0.0

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        self._drag = _DragHandle(name)
        lay.addWidget(self._drag, 0)

        self._btn = QPushButton(name)
        self._btn.setObjectName("SchemaPointButton")
        self._btn.setCheckable(True)
        self._btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn.clicked.connect(self._on_btn_clicked)
        self._btn.installEventFilter(self)
        lay.addWidget(self._btn, stretch=1)

        self._delete = QToolButton()
        self._delete.setObjectName("SchemaRowDeleteButton")
        self._delete.setText("\u00d7")
        self._delete.setToolTip("Remove this point")
        self._delete.setCursor(Qt.PointingHandCursor)
        self._delete.clicked.connect(lambda: self.delete_requested.emit(self._name))
        lay.addWidget(self._delete, 0)

    @property
    def name(self) -> str:
        return self._name

    def set_name(self, name: str) -> None:
        self._name = name

    def set_label(self, text: str) -> None:
        self._btn.setText(text)

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag.set_enabled(enabled)

    def set_selected(self, selected: bool) -> None:
        self._btn.blockSignals(True)
        self._btn.setChecked(selected)
        self._btn.blockSignals(False)

    def set_bone_pulse(self, active: bool) -> None:
        if self._bone_pulse != active:
            self._bone_pulse = active
            self.update()

    def set_bone_pick_highlight(self, active: bool) -> None:
        if self._bone_pick_highlight != active:
            self._bone_pick_highlight = active
            self.update()

    def set_dash_offset(self, offset: float) -> None:
        self._dash_offset = offset
        if self._bone_pulse or self._bone_pick_highlight:
            self.update()

    def _on_btn_clicked(self) -> None:
        self.clicked_name.emit(self._name)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._btn and event.type() == QEvent.MouseButtonDblClick:
            self.rename_requested.emit(self._name)
            return True
        return super().eventFilter(obj, event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._bone_pulse and not self._bone_pick_highlight:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if self._bone_pick_highlight:
            pen = QPen(QColor("#ffb020"), 2, Qt.SolidLine)
        else:
            pen = QPen(QColor("#ffb020"), 2, Qt.DashLine)
            pen.setDashOffset(self._dash_offset)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 4, 4)


class _BoneRow(QWidget):
    delete_requested = pyqtSignal(str, str)

    def __init__(self, a: str, b: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SchemaBoneRow")
        self._a = a
        self._b = b

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        self._label = QLabel(bone_display_name(a, b))
        self._label.setObjectName("SchemaBoneLabel")
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(self._label, stretch=1)

        delete = QToolButton()
        delete.setObjectName("SchemaRowDeleteButton")
        delete.setText("\u00d7")
        delete.setToolTip("Remove this bone")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(lambda: self.delete_requested.emit(self._a, self._b))
        lay.addWidget(delete, 0)

    def set_names(self, a: str, b: str) -> None:
        self._a = a
        self._b = b
        self._label.setText(bone_display_name(a, b))


class BodypartLabelList(QWidget):
    bodypart_selected = pyqtSignal(str)
    bodypart_renamed = pyqtSignal(str, str)
    bodypart_removed = pyqtSignal(str)
    add_point_requested = pyqtSignal()
    clear_all_requested = pyqtSignal()
    bone_tool_requested = pyqtSignal()
    bone_tool_cancel_requested = pyqtSignal()
    bone_pair_requested = pyqtSignal(str, str)
    bone_removed = pyqtSignal(str, str)
    bodypart_reordered = pyqtSignal(str, int)

    _PULSE_MS = 80
    _DASH_STEP = 1.5
    MIN_WIDTH = 160
    DEFAULT_WIDTH = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BodypartLabelList")
        self.setMinimumWidth(self.MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self._names: list[str] = []
        self._selected_name: str | None = None
        self._bone_mode = False
        self._bone_pick: str | None = None
        self._point_rows: dict[str, _PointRow] = {}
        self._bone_rows: list[_BoneRow] = []
        self._dash_offset = 0.0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        panel_splitter = QSplitter(Qt.Vertical)
        panel_splitter.setObjectName("SchemaPanelSplitter")
        panel_splitter.setChildrenCollapsible(False)

        points_section = QWidget()
        points_section.setObjectName("SchemaPointsSection")
        points_section_lay = QVBoxLayout(points_section)
        points_section_lay.setContentsMargins(0, 0, 0, 0)
        points_section_lay.setSpacing(6)

        points_hdr = QLabel("Points")
        points_hdr.setObjectName("SchemaSectionHeader")
        points_section_lay.addWidget(points_hdr)

        self._points_host = _PointsDropHost()
        self._points_host.reorder_requested.connect(self._on_reorder_requested)
        self._points_layout = self._points_host.layout()

        points_scroll = QScrollArea()
        points_scroll.setObjectName("SchemaPointsScroll")
        points_scroll.setWidgetResizable(True)
        points_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        points_scroll.setWidget(self._points_host)
        points_section_lay.addWidget(points_scroll, stretch=1)

        tools = QHBoxLayout()
        self._add_btn = QPushButton("+ Add point")
        self._add_btn.setObjectName("BodypartAddPointButton")
        self._add_btn.setCheckable(True)
        self._add_btn.clicked.connect(self._on_add_clicked)
        tools.addWidget(self._add_btn)

        self._bone_btn = QPushButton("Bone tool")
        self._bone_btn.setObjectName("SchemaBoneToolButton")
        self._bone_btn.setCheckable(True)
        self._bone_btn.setToolTip(
            "Link two points with a bone. Click two point rows, or click again to cancel."
        )
        self._bone_btn.clicked.connect(self._on_bone_clicked)
        tools.addWidget(self._bone_btn)
        points_section_lay.addLayout(tools)

        self._clear_all_btn = QPushButton("Clear all")
        self._clear_all_btn.setObjectName("SchemaClearAllButton")
        self._clear_all_btn.setToolTip("Remove all bodyparts and labels")
        self._clear_all_btn.setVisible(False)
        self._clear_all_btn.clicked.connect(self.clear_all_requested.emit)
        points_section_lay.addWidget(self._clear_all_btn)

        bones_section = QWidget()
        bones_section.setObjectName("SchemaBonesSection")
        bones_section_lay = QVBoxLayout(bones_section)
        bones_section_lay.setContentsMargins(0, 0, 0, 0)
        bones_section_lay.setSpacing(6)

        bones_hdr = QLabel("Bones")
        bones_hdr.setObjectName("SchemaSectionHeader")
        bones_section_lay.addWidget(bones_hdr)

        self._bones_host = QWidget()
        self._bones_host.setObjectName("SchemaBonesHost")
        self._bones_layout = QVBoxLayout(self._bones_host)
        self._bones_layout.setContentsMargins(0, 0, 0, 0)
        self._bones_layout.setSpacing(2)
        self._bones_layout.addStretch(1)

        bones_scroll = QScrollArea()
        bones_scroll.setObjectName("SchemaBonesScroll")
        bones_scroll.setWidgetResizable(True)
        bones_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        bones_scroll.setWidget(self._bones_host)
        bones_section_lay.addWidget(bones_scroll, stretch=1)

        panel_splitter.addWidget(points_section)
        panel_splitter.addWidget(bones_section)
        panel_splitter.setStretchFactor(0, 3)
        panel_splitter.setStretchFactor(1, 2)
        panel_splitter.setSizes([480, 280])
        points_scroll.setMinimumHeight(220)
        bones_scroll.setMinimumHeight(180)
        root.addWidget(panel_splitter, stretch=1)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(self._PULSE_MS)
        self._pulse_timer.timeout.connect(self._advance_dash)

    def _advance_dash(self) -> None:
        self._dash_offset = (self._dash_offset + self._DASH_STEP) % 12.0
        for row in self._point_rows.values():
            row.set_dash_offset(self._dash_offset)

    def _on_add_clicked(self, checked: bool) -> None:
        if checked:
            self._bone_btn.blockSignals(True)
            self._bone_btn.setChecked(False)
            self._bone_btn.blockSignals(False)
            self._exit_bone_mode_local()
            self.bone_tool_cancel_requested.emit()
            self._clear_point_selection()
            self.add_point_requested.emit()
        else:
            self._add_btn.setChecked(False)

    def _on_bone_clicked(self, checked: bool) -> None:
        if checked:
            self._add_btn.blockSignals(True)
            self._add_btn.setChecked(False)
            self._add_btn.blockSignals(False)
            self._bone_mode = True
            self._bone_pick = None
            self._clear_point_selection()
            self._set_drag_enabled(False)
            self.bone_tool_requested.emit()
            self._apply_bone_visuals()
            self._pulse_timer.start()
        else:
            self.bone_tool_cancel_requested.emit()
            self._exit_bone_mode_local()

    def _exit_bone_mode_local(self) -> None:
        self._bone_mode = False
        self._bone_pick = None
        self._bone_btn.blockSignals(True)
        self._bone_btn.setChecked(False)
        self._bone_btn.blockSignals(False)
        self._pulse_timer.stop()
        self._set_drag_enabled(True)
        self._apply_bone_visuals()

    def _clear_point_selection(self) -> None:
        for row in self._point_rows.values():
            row.set_selected(False)

    def _apply_bone_visuals(self) -> None:
        for name, row in self._point_rows.items():
            row.set_bone_pulse(self._bone_mode)
            row.set_bone_pick_highlight(self._bone_mode and name == self._bone_pick)
            row.set_dash_offset(self._dash_offset)

    def _on_point_row_clicked(self, name: str) -> None:
        if self._bone_mode:
            if self._bone_pick is None:
                self._bone_pick = name
                self._apply_bone_visuals()
                return
            if name == self._bone_pick:
                return
            self.bone_pair_requested.emit(self._bone_pick, name)
            return

        self._selected_name = name
        for n, row in self._point_rows.items():
            row.set_selected(n == name)
        self._add_btn.blockSignals(True)
        self._add_btn.setChecked(False)
        self._add_btn.blockSignals(False)
        self.bodypart_selected.emit(name)

    def _on_point_delete(self, name: str) -> None:
        self.bodypart_removed.emit(name)

    def _on_point_rename(self, old_name: str) -> None:
        new_name, ok = QInputDialog.getText(
            self,
            "Rename bodypart",
            "New name:",
            text=old_name,
        )
        if ok and new_name and new_name.strip() != old_name:
            self.bodypart_renamed.emit(old_name, new_name.strip())

    def _on_bone_delete(self, a: str, b: str) -> None:
        self.bone_removed.emit(a, b)

    def _on_reorder_requested(self, name: str, target_index: int) -> None:
        self.bodypart_reordered.emit(name, target_index)

    def clear_bone_pick(self) -> None:
        self._bone_pick = None
        self._apply_bone_visuals()

    def _rebuild_point_rows(
        self,
        names: list[str],
        counts: dict[str, int],
        queue_len: int,
    ) -> None:
        old_selected = self._selected_name
        for row in list(self._point_rows.values()):
            self._points_layout.removeWidget(row)
            row.deleteLater()
        self._point_rows.clear()

        for name in names:
            row = _PointRow(name, self._points_host)
            row.set_label(f"{name}  {counts.get(name, 0)}/{queue_len}")
            row.clicked_name.connect(self._on_point_row_clicked)
            row.delete_requested.connect(self._on_point_delete)
            row.rename_requested.connect(self._on_point_rename)
            self._points_layout.addWidget(row)
            self._point_rows[name] = row

        if old_selected and old_selected in self._point_rows and not self._bone_mode:
            self._point_rows[old_selected].set_selected(True)
        self._set_drag_enabled(not self._bone_mode)
        self._apply_bone_visuals()

    def _set_drag_enabled(self, enabled: bool) -> None:
        for row in self._point_rows.values():
            row.set_drag_enabled(enabled)

    def _rebuild_bone_rows(self, pairs: list[tuple[str, str]]) -> None:
        for row in self._bone_rows:
            self._bones_layout.removeWidget(row)
            row.deleteLater()
        self._bone_rows.clear()
        stretch = self._bones_layout.takeAt(self._bones_layout.count() - 1)

        for a, b in pairs:
            row = _BoneRow(a, b, self._bones_host)
            row.delete_requested.connect(self._on_bone_delete)
            self._bones_layout.addWidget(row)
            self._bone_rows.append(row)

        if stretch is not None:
            self._bones_layout.addStretch(1)

    def set_bodyparts(
        self,
        names: list[str],
        counts: dict[str, int],
        queue_len: int,
        *,
        selected_name: str | None = None,
    ) -> None:
        if selected_name is not None:
            self._selected_name = selected_name
        if self._selected_name and self._selected_name not in names:
            self._selected_name = names[0] if names else None

        if names == self._names and set(self._point_rows.keys()) == set(names):
            for name in names:
                self._point_rows[name].set_label(
                    f"{name}  {counts.get(name, 0)}/{queue_len}"
                )
            if not self._bone_mode and self._selected_name:
                for n, row in self._point_rows.items():
                    row.set_selected(n == self._selected_name)
            self._set_drag_enabled(not self._bone_mode)
            self._apply_bone_visuals()
            return

        self._names = list(names)
        self._rebuild_point_rows(names, counts, queue_len)

    def set_bones(self, pairs: list[tuple[str, str]]) -> None:
        current = [(r._a, r._b) for r in self._bone_rows]
        if pairs == current:
            for row, (a, b) in zip(self._bone_rows, pairs):
                row.set_names(a, b)
            return
        self._rebuild_bone_rows(pairs)

    def set_add_point_mode(self, active: bool) -> None:
        self._add_btn.blockSignals(True)
        self._add_btn.setChecked(active)
        self._add_btn.blockSignals(False)
        if active:
            self._clear_point_selection()

    def set_bone_mode(self, active: bool) -> None:
        if active:
            self._bone_mode = True
            self._bone_btn.blockSignals(True)
            self._bone_btn.setChecked(True)
            self._bone_btn.blockSignals(False)
            self._set_drag_enabled(False)
            self._apply_bone_visuals()
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        else:
            self._exit_bone_mode_local()
            self.clear_bone_pick()
            self._clear_point_selection()
            if self._selected_name and self._selected_name in self._point_rows:
                self._point_rows[self._selected_name].set_selected(True)

    def set_clear_all_visible(self, visible: bool) -> None:
        """Show the Clear all button (e.g. Verify Labels tab)."""
        self._clear_all_btn.setVisible(visible)

    def select_bodypart(self, name: str | None) -> None:
        if not name:
            return
        self._selected_name = name
        for n, row in self._point_rows.items():
            row.set_selected(n == name)
