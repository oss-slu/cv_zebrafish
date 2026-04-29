"""
Bodypart chip pools for Generate Config: two palette lists and two ordered spine/tail lists.

* **Add (palette):** `set_add_callback` — `config_generator` calls `add_name` then refills the Available pool.
* **Spine / tail:** Drag to reorder. Drag a block onto the paired **Available** list to return it, or
  **click without dragging** on a block to return it. Names appear in Available *or* Spine/Tail, not both
  (see `_refill_available_pools` in `config_generator_widget`).
"""

from __future__ import annotations

from collections.abc import Callable
from PyQt5.QtCore import QRect, QTimer, Qt
from PyQt5.QtGui import QCursor, QFont, QFontMetrics
from PyQt5.QtWidgets import QApplication, QListView, QListWidget, QListWidgetItem, QToolTip, QWidget

BP_MIME = "application/x-cv-zebrafish-bp"


class ChipDelegate:
    """Long-label tooltips when the label is wider than the list viewport."""

    def __init__(self, list_widget: QListWidget) -> None:
        self.lw = list_widget
        self.lw.setMouseTracking(True)
        self.lw.itemEntered.connect(self._on_item_entered)

    def _on_item_entered(self, item: QListWidgetItem) -> None:
        t = (item.text() or "").strip()
        if not t:
            return
        fm = self.lw.fontMetrics()
        cell_w = max(1, self.lw.width() - 32)
        if fm.horizontalAdvance(t) > cell_w:
            QToolTip.showText(QCursor.pos(), t, self.lw, QRect(), 6000)
        else:
            QToolTip.hideText()


def _refit_list_height(lw: QListWidget) -> None:
    n = max(0, lw.count())
    fm = lw.fontMetrics()
    row_h = max(32, fm.height() + 12)
    max_rows = 10
    if n == 0:
        h = 64
    else:
        h = min(n, max_rows) * row_h + 16
    lw.setMinimumHeight(h)
    lw.setMaximumHeight(1_000_000)


class BodypartSequenceList(QListWidget):
    """Ordered spine or tail; internal drag to reorder; drop from palette; drag to palette removes."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BodypartPoolSequence")
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setViewMode(QListView.ListMode)
        self.setFlow(QListView.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.Fixed)
        self.setSpacing(4)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QListWidget.DragDrop)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTextElideMode(Qt.ElideNone)
        self.setMinimumHeight(64)
        self.setUniformItemSizes(False)
        self.setCursor(Qt.OpenHandCursor)
        self._palette: BodypartPaletteList | None = None
        self._dnd_from_row: int = -1
        self._chip_delegate: ChipDelegate | None = None
        self._return_callback: Callable[[str], None] | None = None
        self._press_item: QListWidgetItem | None = None
        self._click_origin = None
        self._did_real_drag: bool = False
        m = self.model()
        m.rowsInserted.connect(self._on_rows_change)
        m.rowsRemoved.connect(self._on_rows_change)
        m.modelReset.connect(self._on_rows_change)

    def set_palette(self, pal: "BodypartPaletteList") -> None:
        self._palette = pal

    def set_chip_delegate(self, d: ChipDelegate) -> None:
        self._chip_delegate = d

    def set_return_callback(self, fn: Callable[[str], None] | None) -> None:
        """On a short left click (no drag) on a row, the row is removed and fn(name) is called (e.g. to refill Available)."""
        self._return_callback = fn

    def _on_rows_change(self, *_a) -> None:
        _refit_list_height(self)

    def _names(self) -> set[str]:
        return {(self.item(i).text() or "").strip() for i in range(self.count()) if self.item(i)}

    def has_name(self, name: str) -> bool:
        n = (name or "").strip()
        return n in self._names()

    def add_name(self, name: str) -> bool:
        n = (name or "").strip()
        if not n or self.has_name(n):
            return False
        it = QListWidgetItem(n)
        it.setData(Qt.UserRole, n)
        self.addItem(it)
        _refit_list_height(self)
        return True

    def startDrag(self, supportedActions) -> None:  # noqa: N802
        self._did_real_drag = True
        self._dnd_from_row = self.currentRow()
        super().startDrag(supportedActions)
        self._dnd_from_row = -1

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        m = event.mimeData()
        if m and m.hasFormat(BP_MIME) and self._palette and event.source() is self._palette:
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        m = event.mimeData()
        if m and m.hasFormat(BP_MIME) and self._palette and event.source() is self._palette:
            event.setDropAction(Qt.CopyAction)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        md = event.mimeData()
        if md is not None and md.hasFormat(BP_MIME) and self._palette and event.source() is self._palette:
            t = str(bytes(md.data(BP_MIME)).decode("utf-8", errors="replace")).strip()
            if t:
                self.add_name(t)
            event.setDropAction(Qt.CopyAction)
            event.accept()
            _refit_list_height(self)
            return
        super().dropEvent(event)
        _refit_list_height(self)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.LeftButton:
            self._did_real_drag = False
            self._click_origin = e.pos()
            self._press_item = self.itemAt(e.pos())
        it = self._press_item
        if it is not None:
            self.setCurrentItem(it)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        super().mouseReleaseEvent(e)
        if (
            e.button() == Qt.LeftButton
            and self._return_callback
            and self._press_item is not None
            and self._click_origin is not None
            and not self._did_real_drag
        ):
            if (e.pos() - self._click_origin).manhattanLength() > QApplication.startDragDistance():
                pass
            else:
                it = self.itemAt(e.pos())
                if it is self._press_item:
                    n = (it.text() or "").strip()
                    row = self.row(it)
                    if n and row >= 0:
                        self.takeItem(row)
                        self._return_callback(n)
                    _refit_list_height(self)
        self._press_item = None
        self._did_real_drag = False

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        _refit_list_height(self)

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        QTimer.singleShot(0, lambda: _refit_list_height(self))

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        it = self.itemAt(e.pos())
        if it is not None:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().mouseMoveEvent(e)


class BodypartPaletteList(QListWidget):
    """
    All bodypart names. Click a row to add to the active spine or tail (see set_add_callback).
    Dragging *from* this list is off; you may drop spine/tail items here to remove them.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BodypartPoolPalette")
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setViewMode(QListView.ListMode)
        self.setFlow(QListView.TopToBottom)
        self.setWrapping(False)
        self.setResizeMode(QListView.Fixed)
        self.setSpacing(4)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setDragEnabled(False)
        self.setDragDropMode(QListWidget.DropOnly)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setTextElideMode(Qt.ElideNone)
        self.setMinimumHeight(64)
        self.setUniformItemSizes(False)
        self.setCursor(Qt.PointingHandCursor)
        self._add_callback: Callable[[str], None] | None = None
        self._chip_delegate: ChipDelegate | None = None
        self._after_sequence_drop: Callable[[], None] | None = None
        m = self.model()
        m.rowsInserted.connect(self._on_rows_change)
        m.rowsRemoved.connect(self._on_rows_change)
        m.modelReset.connect(self._on_rows_change)

    def set_chip_delegate(self, d: ChipDelegate) -> None:
        self._chip_delegate = d

    def set_after_sequence_drop(self, fn: Callable[[], None] | None) -> None:
        self._after_sequence_drop = fn

    def set_add_callback(self, fn: Callable[[str], None] | None) -> None:
        self._add_callback = fn

    def _on_rows_change(self, *_a) -> None:
        _refit_list_height(self)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        it = self.itemAt(e.pos())
        if e.button() == Qt.LeftButton and it is not None and self._add_callback:
            t = (it.text() or "").strip()
            if t:
                self._add_callback(t)
        if it is not None:
            self.setCurrentItem(it)
        super().mousePressEvent(e)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if isinstance(event.source(), BodypartSequenceList):
            event.setDropAction(Qt.MoveAction)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if isinstance(event.source(), BodypartSequenceList):
            event.setDropAction(Qt.MoveAction)
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        src = event.source()
        if isinstance(src, BodypartSequenceList):
            r = int(getattr(src, "_dnd_from_row", -1))
            if 0 <= r < src.count():
                src.takeItem(r)
            if self._after_sequence_drop:
                self._after_sequence_drop()
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        _refit_list_height(self)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        _refit_list_height(self)

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        QTimer.singleShot(0, lambda: _refit_list_height(self))

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        it = self.itemAt(e.pos())
        if it is not None:
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().mouseMoveEvent(e)
