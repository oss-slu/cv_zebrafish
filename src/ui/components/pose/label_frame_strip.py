"""Timeline strip for the labeling frame queue — bars on a line, hover for crop preview."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap, QPolygon
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget


class LabelFrameStrip(QWidget):
    """Horizontal timeline with vertical bars; hover shows fish crop, click selects."""

    frame_selected = pyqtSignal(int)

    # Match PoseLabelScanProgress in themes.py
    BAR_COLOR = QColor(90, 150, 230)
    BAR_COLOR_LIVE = QColor(120, 190, 255)

    _BAR_HIT_PX = 8
    _TIMELINE_HEIGHT = 44
    _BAR_HEIGHT = 22

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LabelFrameStrip")
        self.setMinimumHeight(self._TIMELINE_HEIGHT + 8)
        self.setMouseTracking(True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self._progress = QLabel("")
        self._progress.setObjectName("SettingsHintLabel")
        lay.addWidget(self._progress)

        self._timeline = QWidget()
        self._timeline.setMinimumHeight(self._TIMELINE_HEIGHT)
        self._timeline.setMouseTracking(True)
        self._timeline.paintEvent = self._paint_timeline  # type: ignore[method-assign]
        self._timeline.mouseMoveEvent = self._timeline_mouse_move  # type: ignore[method-assign]
        self._timeline.mousePressEvent = self._timeline_mouse_press  # type: ignore[method-assign]
        self._timeline.leaveEvent = self._timeline_leave  # type: ignore[method-assign]
        lay.addWidget(self._timeline, stretch=1)

        self._queue: list[int] = []
        self._current_index = 0
        self._frame_count = 1
        self._thumbnail_for: Callable[[int], QPixmap | None] | None = None
        self._hover_queue_index: int | None = None
        self._thumb_cache: dict[int, QPixmap] = {}
        self._live_build = False

        self._hover_popup = QLabel(self, Qt.ToolTip)
        self._hover_popup.setObjectName("LabelFrameHoverPreview")
        self._hover_popup.hide()

    def _timeline_geometry(self) -> tuple[int, int, int, int]:
        margin_x = 10
        w = max(1, self._timeline.width() - 2 * margin_x)
        y_mid = self._timeline.height() // 2
        return margin_x, y_mid, w, margin_x

    def _frame_to_x(self, frame_index: int, margin_x: int, width: int) -> int:
        if self._frame_count <= 1:
            return margin_x
        frac = frame_index / max(1, self._frame_count - 1)
        return margin_x + int(round(frac * width))

    def _x_to_queue_index(self, x: int) -> int | None:
        if not self._queue:
            return None
        margin_x, _y, width, _ = self._timeline_geometry()
        best_i: int | None = None
        best_d = self._BAR_HIT_PX + 1
        for i, fi in enumerate(self._queue):
            bx = self._frame_to_x(fi, margin_x, width)
            d = abs(x - bx)
            if d <= self._BAR_HIT_PX and d < best_d:
                best_d = d
                best_i = i
        return best_i

    def _paint_timeline(self, _event) -> None:
        painter = QPainter(self._timeline)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self._timeline.rect()
        painter.fillRect(rect, self._timeline.palette().window())

        margin_x, y_mid, width, _ = self._timeline_geometry()
        x0 = margin_x
        x1 = margin_x + width
        baseline_pen = QPen(QColor(120, 130, 150), 2)
        painter.setPen(baseline_pen)
        painter.drawLine(x0, y_mid, x1, y_mid)

        if not self._queue:
            painter.end()
            return

        for i, fi in enumerate(self._queue):
            bx = self._frame_to_x(fi, margin_x, width)
            is_current = i == self._current_index
            is_hover = i == self._hover_queue_index
            if is_current:
                color = QColor(255, 120, 60)
                bar_h = self._BAR_HEIGHT + 4
            elif is_hover:
                color = QColor(180, 200, 255)
                bar_h = self._BAR_HEIGHT + 2
            else:
                color = self.BAR_COLOR_LIVE if self._live_build else self.BAR_COLOR
                bar_h = self._BAR_HEIGHT
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRect(bx - 2, y_mid - bar_h // 2, 4, bar_h)

        if 0 <= self._current_index < len(self._queue):
            cx = self._frame_to_x(self._queue[self._current_index], margin_x, width)
            arrow = QPolygon(
                [
                    QPoint(cx, y_mid - self._BAR_HEIGHT // 2 - 10),
                    QPoint(cx - 6, y_mid - self._BAR_HEIGHT // 2 - 2),
                    QPoint(cx + 6, y_mid - self._BAR_HEIGHT // 2 - 2),
                ]
            )
            painter.setBrush(QColor(255, 120, 60))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(arrow)

        painter.end()

    def _show_hover_preview(self, global_pos: QPoint, frame_index: int) -> None:
        if self._thumbnail_for is None:
            return
        pix = self._thumb_cache.get(frame_index)
        if pix is None:
            pix = self._thumbnail_for(frame_index)
            if pix is not None and not pix.isNull():
                self._thumb_cache[frame_index] = pix
        if pix is None or pix.isNull():
            self._hover_popup.hide()
            return
        scaled = pix.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._hover_popup.setPixmap(scaled)
        self._hover_popup.resize(scaled.size())
        self._hover_popup.move(global_pos + QPoint(12, 12))
        self._hover_popup.show()

    def _timeline_mouse_move(self, event) -> None:
        idx = self._x_to_queue_index(int(event.pos().x()))
        if idx != self._hover_queue_index:
            self._hover_queue_index = idx
            self._timeline.update()
        if idx is not None:
            fi = self._queue[idx]
            self._timeline.setToolTip(f"Frame {fi}")
            self._show_hover_preview(self._timeline.mapToGlobal(event.pos()), fi)
        else:
            self._timeline.setToolTip("")
            self._hover_popup.hide()

    def _timeline_mouse_press(self, event) -> None:
        if event.button() != Qt.LeftButton:
            return
        idx = self._x_to_queue_index(int(event.pos().x()))
        if idx is not None:
            self._current_index = idx
            self._timeline.update()
            self.frame_selected.emit(self._queue[idx])

    def _timeline_leave(self, _event) -> None:
        self._hover_queue_index = None
        self._hover_popup.hide()
        self._timeline.update()

    def clear_thumbnail_cache(self) -> None:
        self._thumb_cache.clear()

    def set_live_queue(
        self,
        frame_indices: list[int],
        *,
        frame_count: int | None = None,
    ) -> None:
        """Update timeline bars while the diverse queue is being assembled."""
        self._queue = list(frame_indices)
        self._live_build = True
        if frame_count is not None and frame_count > 0:
            self._frame_count = frame_count
        self._hover_popup.hide()
        self._timeline.update()

    def set_queue(
        self,
        frame_indices: list[int],
        current_index: int,
        progress_text: str,
        *,
        frame_count: int | None = None,
        thumbnail_for: Callable[[int], QPixmap | None] | None = None,
    ) -> None:
        self._progress.setText(progress_text)
        self._queue = list(frame_indices)
        self._current_index = max(0, min(current_index, max(0, len(self._queue) - 1)))
        if frame_count is not None and frame_count > 0:
            self._frame_count = frame_count
        elif self._queue:
            self._frame_count = max(self._frame_count, max(self._queue) + 1)
        self._thumbnail_for = thumbnail_for
        self._live_build = False
        self._hover_popup.hide()
        self._timeline.update()

    def sizeHint(self) -> QSize:
        return QSize(400, self._TIMELINE_HEIGHT + 8)
