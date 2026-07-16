"""Square-crop labeling canvas with click-to-place, drag, zoom, and ghost point."""

from __future__ import annotations

import math
import time

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer, pyqtSignal, QRectF
from PyQt5.QtGui import (
    QBrush,
    QImage,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QColor,
)
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

_HIT_RADIUS = 12.0
_MIN_ZOOM = 0.5
_MAX_ZOOM = 8.0
_MAX_SCENE_RADIUS = 48.0
_POINT_BLUE = QColor(90, 150, 230)
_OUTLIER_ORANGE = QColor(255, 152, 50)
_GHOST_ALPHA = 72
_OUTLINE_ALPHA = 48
_ACTIVE_RADIUS = 6.0
_INACTIVE_RADIUS = 4.0
_BONE_WIDTH = 2.0
_BONE_HIT_WIDTH = 14.0
_HOVER_POINT_SCALE = 1.35
_HOVER_LINE_SCALE = 1.6
# Log-scale zoom per wheel notch at momentum=1 (~3.5% change — gentler than fixed 1.15×).
_WHEEL_LOG_STEP = 0.035
# Trackpad pixel deltas arrive often; use a smaller per-step coefficient.
_WHEEL_LOG_STEP_PIXEL = 0.010
_WHEEL_MOMENTUM_MAX = 2.5
_WHEEL_MOMENTUM_GAIN = 0.28
_WHEEL_MOMENTUM_WINDOW_S = 0.14
# Cap per-event log step (~22% max change) to avoid runaway after direction reversals.
_WHEEL_LOG_STEP_MAX = 0.20
# While scrolling, apply accumulated zoom at most this often (~10 Hz).
_WHEEL_FLUSH_INTERVAL_MS = 100
_ZOOM_EPS = 1e-6
_MIN_SCENE_PAD_PX = 200.0


def scene_padding_for_image(width: int, height: int) -> float:
    """Empty margin around the image so the view can pan past the crop edges."""
    return max(_MIN_SCENE_PAD_PX, float(max(width, height)))


class _DraggablePoint(QGraphicsEllipseItem):
    def __init__(
        self,
        x: float,
        y: float,
        radius: float,
        bodypart: str,
        active: bool,
        canvas: LabelCanvas,
        *,
        outlier: bool = False,
    ):
        super().__init__()
        self.bodypart = bodypart
        self._canvas = canvas
        self._base_radius = radius
        self._hovered = False
        self._outlier = outlier
        self.setPos(x, y)
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, active)
        self.setAcceptHoverEvents(True)
        self.setZValue(10 if active else 5)
        self._apply_brush()
        self.setPen(QPen(Qt.NoPen))
        self._apply_radius()

    def _apply_brush(self) -> None:
        color = _OUTLIER_ORANGE if self._outlier else _POINT_BLUE
        self.setBrush(QBrush(color))

    def _apply_radius(self) -> None:
        scale = _HOVER_POINT_SCALE if self._hovered else 1.0
        r = self._base_radius * scale
        self.setRect(-r, -r, r * 2, r * 2)

    def set_scene_radius(self, radius: float) -> None:
        self._base_radius = radius
        self._apply_radius()

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self._apply_radius()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_radius()
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if (
            change == QGraphicsEllipseItem.ItemPositionHasChanged
            and not self._canvas._suppress_geometry_updates
            and not self._canvas._redrawing_bones
        ):
            self._canvas._update_bone_lines()
        return super().itemChange(change, value)


class _BoneLineItem(QGraphicsLineItem):
    def __init__(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        canvas: LabelCanvas,
        pair: tuple[str, str] | None = None,
        *,
        outlier: bool = False,
    ):
        super().__init__(x1, y1, x2, y2)
        self._canvas = canvas
        self._pair = pair
        self._hovered = False
        self._outlier = outlier
        self.setAcceptHoverEvents(True)
        self.setZValue(3)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self._apply_pen()

    def _line_width(self) -> float:
        width = _BONE_WIDTH
        if self._hovered:
            width *= _HOVER_LINE_SCALE
        z = max(self._canvas._zoom, _MIN_ZOOM)
        return min(width / z, _MAX_SCENE_RADIUS)

    def _apply_pen(self) -> None:
        color = _OUTLIER_ORANGE if self._outlier else _POINT_BLUE
        pen = QPen(color, self._line_width())
        pen.setCosmetic(True)
        self.setPen(pen)

    def shape(self):
        stroker = QPainterPathStroker()
        z = max(self._canvas._zoom, _MIN_ZOOM)
        stroker.setWidth(min(_BONE_HIT_WIDTH / z, _MAX_SCENE_RADIUS * 2))
        stroker.setCapStyle(Qt.RoundCap)
        path = QPainterPath()
        line = self.line()
        path.moveTo(line.p1())
        path.lineTo(line.p2())
        return stroker.createStroke(path)

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self._apply_pen()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self._apply_pen()
        super().hoverLeaveEvent(event)


class _GhostPoint(QGraphicsEllipseItem):
    def __init__(self, x: float, y: float, radius: float = _ACTIVE_RADIUS):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.setPos(x, y)
        self.setZValue(4)
        ghost = QColor(_POINT_BLUE)
        ghost.setAlpha(_GHOST_ALPHA)
        self.setBrush(QBrush(ghost))
        self.setPen(QPen(Qt.NoPen))
        self.setAcceptedMouseButtons(Qt.NoButton)

    def set_scene_radius(self, radius: float) -> None:
        self.setRect(-radius, -radius, radius * 2, radius * 2)


class LabelCanvas(QGraphicsView):
    point_placed = pyqtSignal(float, float)
    point_moved = pyqtSignal(str, float, float)
    point_delete_requested = pyqtSignal()
    add_point_at = pyqtSignal(float, float)
    bodypart_hit = pyqtSignal(str)
    drag_started = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LabelCanvas")
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.NoAnchor)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self._pix_item: QGraphicsPixmapItem | None = None
        self._ghost_item: _GhostPoint | None = None
        self._outline_item: QGraphicsPathItem | None = None
        self._crop_w = 1
        self._crop_h = 1
        self._active_bodypart: str | None = None
        self._add_point_mode = False
        self._points_on_frame: dict[str, tuple[float, float]] = {}
        self._bone_pairs: list[tuple[str, str]] = []
        self._outlier_bodyparts: set[str] = set()
        self._outlier_bones: set[tuple[str, str]] = set()
        self._draggables: dict[str, _DraggablePoint] = {}
        self._bone_lines: list[_BoneLineItem] = []
        self._zoom = 1.0
        self._suppress_geometry_updates = False
        self._wheel_momentum = 1.0
        self._wheel_last_ts = 0.0
        self._wheel_last_dir = 0.0
        self._pending_wheel_log = 0.0
        self._pending_wheel_anchor: QPointF | None = None
        self._wheel_coalesce = QTimer(self)
        self._wheel_coalesce.setInterval(_WHEEL_FLUSH_INTERVAL_MS)
        self._wheel_coalesce.timeout.connect(self._flush_wheel_zoom)
        self._redrawing_bones = False
        self._setting_zoom = False
        self._pan_active = False
        self._pan_last: QPoint | None = None

    def hideEvent(self, event) -> None:  # noqa: N802
        self._reset_wheel_state()
        self._end_pan()
        super().hideEvent(event)

    def set_crop_frame(
        self, crop_bgr: np.ndarray | None, *, reset_view: bool = True
    ) -> None:
        self._reset_wheel_state()
        self._end_pan()
        self._scene.clear()
        self._draggables.clear()
        self._bone_lines.clear()
        self._ghost_item = None
        self._outline_item = None
        self._pix_item = None
        if crop_bgr is None or crop_bgr.size == 0:
            return
        self._crop_h, self._crop_w = crop_bgr.shape[:2]
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        self._pix_item = self._scene.addPixmap(QPixmap.fromImage(qimg))
        self._pix_item.setZValue(0)
        pad = scene_padding_for_image(w, h)
        self._scene.setSceneRect(-pad, -pad, w + 2 * pad, h + 2 * pad)
        self._redraw_points()
        if reset_view:
            self._fit_image_to_view()

    def set_fish_outline(self, mask_u8: np.ndarray | None) -> None:
        if self._outline_item is not None:
            self._scene.removeItem(self._outline_item)
            self._outline_item = None
        if mask_u8 is None or mask_u8.size == 0 or self._pix_item is None:
            return
        contours, _ = cv2.findContours(
            mask_u8.astype(np.uint8),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        if not contours:
            return
        path = QPainterPath()
        for cnt in contours:
            if len(cnt) < 3:
                continue
            path.moveTo(float(cnt[0][0][0]), float(cnt[0][0][1]))
            for p in cnt[1:]:
                path.lineTo(float(p[0][0]), float(p[0][1]))
            path.closeSubpath()
        item = QGraphicsPathItem(path)
        item.setZValue(2)
        outline = QColor(70, 255, 120)
        outline.setAlpha(_OUTLINE_ALPHA)
        item.setPen(QPen(outline, 1.5))
        item.setBrush(QBrush(Qt.NoBrush))
        self._scene.addItem(item)
        self._outline_item = item

    def set_display_points(
        self,
        points_crop: dict[str, tuple[float, float] | None],
        active_bodypart: str | None,
    ) -> None:
        self._points_on_frame = {
            k: v for k, v in points_crop.items() if v is not None
        }
        self._active_bodypart = active_bodypart
        self._redraw_points()

    def set_display_bones(self, pairs: list[tuple[str, str]]) -> None:
        self._bone_pairs = list(pairs)
        self._redraw_bones()

    def set_outlier_highlight(
        self,
        bodyparts: set[str] | None = None,
        bones: set[tuple[str, str]] | None = None,
    ) -> None:
        """Mark bodyparts and bones orange on the current frame (QC outliers)."""
        self._outlier_bodyparts = set(bodyparts or ())
        normalized_bones: set[tuple[str, str]] = set()
        for a, b in bones or ():
            normalized_bones.add((a, b) if a <= b else (b, a))
        self._outlier_bones = normalized_bones
        self._redraw_points()

    def set_ghost_point(self, pos: tuple[float, float] | None) -> None:
        if self._ghost_item is not None:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None
        if pos is None or self._pix_item is None:
            return
        x, y = pos
        if x < 0 or y < 0 or x >= self._crop_w or y >= self._crop_h:
            return
        self._ghost_item = _GhostPoint(x, y, self._scene_radius(_ACTIVE_RADIUS))
        self._scene.addItem(self._ghost_item)

    def set_add_point_mode(self, enabled: bool) -> None:
        self._add_point_mode = enabled

    def _image_rect(self) -> QRectF:
        return QRectF(0.0, 0.0, float(self._crop_w), float(self._crop_h))

    def _viewport_usable(self) -> bool:
        vp = self.viewport().rect()
        return vp.width() >= 2 and vp.height() >= 2

    def _scene_radius(self, base: float) -> float:
        z = max(self._zoom, _MIN_ZOOM)
        return min(base / z, _MAX_SCENE_RADIUS)

    def _hit_radius_sq(self) -> float:
        r = self._scene_radius(_HIT_RADIUS)
        return r * r

    def _sync_zoom_graphics(self) -> None:
        """Resize point/ghost/line cosmetics for the current zoom without rebuilding items."""
        if self._ghost_item is not None:
            self._ghost_item.set_scene_radius(self._scene_radius(_ACTIVE_RADIUS))
        for name, item in self._draggables.items():
            active = name == self._active_bodypart
            base = _ACTIVE_RADIUS if active else _INACTIVE_RADIUS
            item.set_scene_radius(self._scene_radius(base))
        for line in self._bone_lines:
            line._apply_pen()

    def _fit_image_to_view(self) -> None:
        """One-time fit of the image into the viewport (double-click / first load)."""
        if self._pix_item is None or self._setting_zoom:
            return
        if not self._viewport_usable():
            return
        self._setting_zoom = True
        try:
            self.resetTransform()
            self._zoom = 1.0
            self.fitInView(self._image_rect(), Qt.KeepAspectRatio)
            if not self.transform().isInvertible():
                self.resetTransform()
                return
            self._sync_zoom_graphics()
        except Exception:
            self.resetTransform()
            self._zoom = 1.0
        finally:
            self._setting_zoom = False

    def _end_pan(self) -> None:
        self._pan_active = False
        self._pan_last = None
        self.setCursor(Qt.ArrowCursor)

    def _at_zoom_limit(self, direction: float) -> bool:
        if direction > 0 and self._zoom >= _MAX_ZOOM - _ZOOM_EPS:
            return True
        if direction < 0 and self._zoom <= _MIN_ZOOM + _ZOOM_EPS:
            return True
        return False

    def _set_zoom(self, new_zoom: float, anchor_view: QPointF | None = None) -> bool:
        """Scale around a view-pixel anchor without refitting the image."""
        if self._pix_item is None or self._setting_zoom:
            return False
        if not self._viewport_usable():
            return False
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, new_zoom))
        if not math.isfinite(new_zoom) or new_zoom <= 0:
            return False
        if abs(new_zoom - self._zoom) < _ZOOM_EPS:
            return False

        if anchor_view is None:
            center = self.viewport().rect().center()
            anchor_view = QPointF(float(center.x()), float(center.y()))

        factor = new_zoom / self._zoom
        if not math.isfinite(factor) or factor <= 0:
            return False

        self._setting_zoom = True
        try:
            anchor_scene = self.mapToScene(anchor_view.toPoint())
            self.scale(factor, factor)
            delta = anchor_scene - self.mapToScene(anchor_view.toPoint())
            if math.isfinite(delta.x()) and math.isfinite(delta.y()):
                self.translate(delta.x(), delta.y())
            if not self.transform().isInvertible():
                self._reset_wheel_state()
                self._fit_image_to_view()
                return False
            self._zoom = new_zoom
            self._sync_zoom_graphics()
            return True
        except Exception:
            self._reset_wheel_state()
            self._fit_image_to_view()
            return False
        finally:
            self._setting_zoom = False

    def _hit_bodypart_at(self, x: float, y: float) -> str | None:
        best: str | None = None
        best_d2 = self._hit_radius_sq()
        for name, (px, py) in self._points_on_frame.items():
            d2 = (px - x) ** 2 + (py - y) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = name
        return best

    def _point_pos(self, name: str) -> tuple[float, float] | None:
        item = self._draggables.get(name)
        if item is not None:
            pos = item.pos()
            return float(pos.x()), float(pos.y())
        return self._points_on_frame.get(name)

    def _update_bone_lines(self) -> None:
        """Move bone endpoints without rebuilding items (safe during point drag)."""
        if self._redrawing_bones:
            return
        for line in self._bone_lines:
            if line._pair is None:
                continue
            a, b = line._pair
            pa = self._point_pos(a)
            pb = self._point_pos(b)
            if pa is None or pb is None:
                continue
            line.setLine(pa[0], pa[1], pb[0], pb[1])

    def _redraw_bones(self) -> None:
        if self._redrawing_bones:
            return
        self._redrawing_bones = True
        try:
            for item in self._bone_lines:
                self._scene.removeItem(item)
            self._bone_lines.clear()
            if self._pix_item is None:
                return
            for a, b in self._bone_pairs:
                pa = self._point_pos(a)
                pb = self._point_pos(b)
                if pa is None or pb is None:
                    continue
                bone_key = (a, b) if a <= b else (b, a)
                outlier = bone_key in self._outlier_bones
                line = _BoneLineItem(
                    pa[0], pa[1], pb[0], pb[1], self, pair=(a, b), outlier=outlier
                )
                self._scene.addItem(line)
                self._bone_lines.append(line)
        finally:
            self._redrawing_bones = False

    def _redraw_points(self) -> None:
        if self._pix_item is None:
            return
        for item in list(self._draggables.values()):
            self._scene.removeItem(item)
        self._draggables.clear()
        self._suppress_geometry_updates = True
        try:
            for name, (x, y) in self._points_on_frame.items():
                active = name == self._active_bodypart
                base = _ACTIVE_RADIUS if active else _INACTIVE_RADIUS
                radius = self._scene_radius(base)
                item = _DraggablePoint(
                    x,
                    y,
                    radius,
                    name,
                    active,
                    self,
                    outlier=name in self._outlier_bodyparts,
                )
                item.setFlag(item.ItemSendsGeometryChanges, True)
                self._scene.addItem(item)
                self._draggables[name] = item
        finally:
            self._suppress_geometry_updates = False
        self._redraw_bones()

    def _reset_wheel_state(self) -> None:
        self._wheel_momentum = 1.0
        self._wheel_last_ts = 0.0
        self._wheel_last_dir = 0.0
        self._pending_wheel_log = 0.0
        self._pending_wheel_anchor = None
        self._wheel_coalesce.stop()

    def _wheel_notches(self, event) -> tuple[float, bool]:
        """Return signed notch count and whether the delta came from pixelDelta."""
        pixel = event.pixelDelta()
        if not pixel.isNull() and pixel.y() != 0:
            return (-pixel.y() / 80.0, True)
        angle_y = event.angleDelta().y()
        if angle_y == 0:
            return (0.0, False)
        return (angle_y / 120.0, False)

    def _zoom_softness(self, direction: float) -> float:
        """Ease zoom steps near min/max so the view does not slam into limits."""
        span = _MAX_ZOOM - _MIN_ZOOM
        if span <= 0:
            return 1.0
        ratio = (self._zoom - _MIN_ZOOM) / span
        if direction > 0 and ratio > 0.72:
            return max(0.1, (1.0 - ratio) / 0.28)
        if direction < 0 and ratio < 0.28:
            return max(0.1, ratio / 0.28)
        return 1.0

    def _log_step_for_wheel(self, notches: float, *, pixel_source: bool) -> float:
        direction = 1.0 if notches > 0 else -1.0 if notches < 0 else 0.0
        if direction == 0.0:
            return 0.0
        softness = self._zoom_softness(direction)
        if pixel_source:
            step = _WHEEL_LOG_STEP_PIXEL * notches * softness
            return max(-_WHEEL_LOG_STEP_MAX, min(_WHEEL_LOG_STEP_MAX, step))
        now = time.monotonic()
        if (
            self._wheel_last_ts > 0.0
            and (now - self._wheel_last_ts) <= _WHEEL_MOMENTUM_WINDOW_S
            and direction == self._wheel_last_dir
        ):
            self._wheel_momentum = min(
                _WHEEL_MOMENTUM_MAX,
                self._wheel_momentum + _WHEEL_MOMENTUM_GAIN,
            )
        else:
            self._wheel_momentum = 1.0
        self._wheel_last_ts = now
        self._wheel_last_dir = direction
        step = (
            _WHEEL_LOG_STEP * abs(notches) * self._wheel_momentum * direction * softness
        )
        return max(-_WHEEL_LOG_STEP_MAX, min(_WHEEL_LOG_STEP_MAX, step))

    def _flush_wheel_zoom(self) -> None:
        if abs(self._pending_wheel_log) < 1e-9:
            self._wheel_coalesce.stop()
            return
        log_step = self._pending_wheel_log
        anchor = self._pending_wheel_anchor
        self._pending_wheel_log = 0.0
        self._pending_wheel_anchor = None
        if self._pix_item is None or anchor is None:
            self._wheel_coalesce.stop()
            return
        direction = 1.0 if log_step > 0 else -1.0 if log_step < 0 else 0.0
        if direction != 0.0 and self._at_zoom_limit(direction):
            self._reset_wheel_state()
            return
        log_zoom = math.log(max(self._zoom, _MIN_ZOOM))
        log_new = max(
            math.log(_MIN_ZOOM),
            min(math.log(_MAX_ZOOM), log_zoom + log_step),
        )
        if abs(log_new - log_zoom) < 1e-9:
            self._reset_wheel_state()
            return
        try:
            self._set_zoom(math.exp(log_new), anchor_view=anchor)
        except Exception:
            self._reset_wheel_state()
            self._fit_image_to_view()

    def wheelEvent(self, event) -> None:
        if self._pix_item is None or self._pan_active:
            super().wheelEvent(event)
            return
        try:
            notches, pixel_source = self._wheel_notches(event)
            if abs(notches) < 1e-6:
                return
            if not pixel_source:
                notches = max(-3.0, min(3.0, notches))
            log_step = self._log_step_for_wheel(notches, pixel_source=pixel_source)
            if abs(log_step) < 1e-9:
                event.accept()
                return
            direction = 1.0 if log_step > 0 else -1.0
            if self._at_zoom_limit(direction):
                self._reset_wheel_state()
                event.accept()
                return
            self._pending_wheel_log += log_step
            self._pending_wheel_anchor = QPointF(
                float(event.pos().x()), float(event.pos().y())
            )
            if not self._wheel_coalesce.isActive():
                self._flush_wheel_zoom()
            if not self._wheel_coalesce.isActive():
                self._wheel_coalesce.start()
            event.accept()
        except Exception:
            self._reset_wheel_state()
            event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._pix_item is not None:
            self._reset_wheel_state()
            self._fit_image_to_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._pix_item is None:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MiddleButton:
            self._pan_active = True
            self._pan_last = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.RightButton:
            self.point_delete_requested.emit()
            event.accept()
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        scene_pos = self.mapToScene(event.pos())
        x, y = float(scene_pos.x()), float(scene_pos.y())
        if x < 0 or y < 0 or x >= self._crop_w or y >= self._crop_h:
            return

        hit = self._hit_bodypart_at(x, y)
        if hit:
            if hit != self._active_bodypart:
                self.bodypart_hit.emit(hit)
            if hit in self._draggables:
                self.drag_started.emit(hit)
            super().mousePressEvent(event)
            return

        if self._add_point_mode or self._active_bodypart is None:
            self.add_point_at.emit(x, y)
            return
        if self._active_bodypart:
            self.point_placed.emit(x, y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._pan_active and self._pan_last is not None:
            delta = event.pos() - self._pan_last
            self._pan_last = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MiddleButton and self._pan_active:
            self._end_pan()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if self._active_bodypart and self._active_bodypart in self._draggables:
            item = self._draggables[self._active_bodypart]
            pos = item.pos()
            self.point_moved.emit(self._active_bodypart, float(pos.x()), float(pos.y()))
