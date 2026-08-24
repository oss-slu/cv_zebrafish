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
    OUTSIDE_CROP_DOT = QColor(255, 140, 40)
    OUTLIER_DOT = QColor(255, 152, 50)

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
        self._outside_crop_frames: set[int] = set()
        self._outlier_frames: set[int] = set()
        self._review_mode = False
        self._review_hover_frame: int | None = None

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

    def _x_to_frame_index(self, x: int) -> int | None:
        if self._frame_count <= 0:
            return None
        margin_x, _y, width, _ = self._timeline_geometry()
        if width <= 0:
            return None
        frac = (x - margin_x) / width
        frac = max(0.0, min(1.0, frac))
        return int(round(frac * max(0, self._frame_count - 1)))

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

        if self._review_mode:
            if self._outlier_frames:
                painter.setPen(Qt.NoPen)
                painter.setBrush(self.OUTLIER_DOT)
                for fi in sorted(self._outlier_frames):
                    bx = self._frame_to_x(fi, margin_x, width)
                    painter.drawEllipse(bx - 3, y_mid + 10, 6, 6)
            if self._outside_crop_frames:
                painter.setBrush(self.OUTSIDE_CROP_DOT)
                for fi in sorted(self._outside_crop_frames):
                    bx = self._frame_to_x(fi, margin_x, width)
                    painter.drawEllipse(bx - 3, y_mid - 16, 6, 6)
            cur_fi = self._queue[self._current_index] if self._queue else 0
            if self._review_hover_frame is not None:
                hx = self._frame_to_x(self._review_hover_frame, margin_x, width)
                painter.setBrush(QColor(180, 200, 255))
                painter.drawRect(hx - 2, y_mid - self._BAR_HEIGHT // 2, 4, self._BAR_HEIGHT)
            cx = self._frame_to_x(cur_fi, margin_x, width)
            painter.setBrush(QColor(255, 120, 60))
            painter.setPen(Qt.NoPen)
            painter.drawRect(cx - 2, y_mid - self._BAR_HEIGHT // 2 - 2, 4, self._BAR_HEIGHT + 4)
            arrow = QPolygon(
                [
                    QPoint(cx, y_mid - self._BAR_HEIGHT // 2 - 12),
                    QPoint(cx - 6, y_mid - self._BAR_HEIGHT // 2 - 4),
                    QPoint(cx + 6, y_mid - self._BAR_HEIGHT // 2 - 4),
                ]
            )
            painter.drawPolygon(arrow)
            painter.end()
            return

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
            if fi in self._outside_crop_frames:
                dot_y = y_mid + bar_h // 2 + 5
                painter.setBrush(self.OUTSIDE_CROP_DOT)
                painter.drawEllipse(bx - 3, dot_y, 6, 6)

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
        if self._review_mode:
            fi = self._x_to_frame_index(int(event.pos().x()))
            if fi != self._review_hover_frame:
                self._review_hover_frame = fi
                self._timeline.update()
            if fi is not None:
                self._timeline.setToolTip(f"Frame {fi}")
                self._show_hover_preview(self._timeline.mapToGlobal(event.pos()), fi)
            else:
                self._timeline.setToolTip("")
                self._hover_popup.hide()
            return
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
        if self._review_mode:
            fi = self._x_to_frame_index(int(event.pos().x()))
            if fi is not None:
                self.frame_selected.emit(fi)
            return
        idx = self._x_to_queue_index(int(event.pos().x()))
        if idx is not None:
            self._current_index = idx
            self._timeline.update()
            self.frame_selected.emit(self._queue[idx])

    def _timeline_leave(self, _event) -> None:
        self._hover_queue_index = None
        self._review_hover_frame = None
        self._hover_popup.hide()
        self._timeline.update()

    def set_review_mode(self, enabled: bool) -> None:
        """Continuous full-video timeline (no per-queue bars)."""
        self._review_mode = bool(enabled)
        self._review_hover_frame = None
        self._hover_popup.hide()
        self._timeline.update()

    def set_outlier_frames(self, frame_indices: set[int] | frozenset[int]) -> None:
        """Orange dots on the review timeline for QC outlier frames."""
        self._outlier_frames = {int(i) for i in frame_indices}
        self._timeline.update()

    def clear_thumbnail_cache(self) -> None:
        self._thumb_cache.clear()

    def set_outside_crop_frames(self, frame_indices: set[int] | frozenset[int]) -> None:
        """Mark timeline bars whose labeled points fall outside the current crop."""
        self._outside_crop_frames = {int(i) for i in frame_indices}
        self._timeline.update()

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
