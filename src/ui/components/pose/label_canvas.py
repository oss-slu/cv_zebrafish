"""Square-crop labeling canvas with click-to-place, drag, zoom, and ghost point."""

from __future__ import annotations

import cv2
import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QImage, QPainter, QPainterPath, QPen, QPixmap, QColor
from PyQt5.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

_HIT_RADIUS = 12.0
_MIN_ZOOM = 0.25
_MAX_ZOOM = 8.0
_POINT_BLUE = QColor(90, 150, 230)
_GHOST_ALPHA = 72
_OUTLINE_ALPHA = 48
_ACTIVE_RADIUS = 6.0
_INACTIVE_RADIUS = 4.0


class _DraggablePoint(QGraphicsEllipseItem):
    def __init__(self, x: float, y: float, radius: float, bodypart: str, active: bool):
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.bodypart = bodypart
        self.setPos(x, y)
        self.setFlag(QGraphicsEllipseItem.ItemIsMovable, active)
        self.setZValue(10 if active else 5)
        self.setBrush(QBrush(_POINT_BLUE))
        self.setPen(QPen(Qt.NoPen))


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
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        self._pix_item: QGraphicsPixmapItem | None = None
        self._ghost_item: _GhostPoint | None = None
        self._outline_item: QGraphicsPathItem | None = None
        self._crop_w = 1
        self._crop_h = 1
        self._active_bodypart: str | None = None
        self._add_point_mode = False
        self._points_on_frame: dict[str, tuple[float, float]] = {}
        self._draggables: dict[str, _DraggablePoint] = {}
        self._zoom = 1.0

    def set_crop_frame(
        self, crop_bgr: np.ndarray | None, *, reset_view: bool = True
    ) -> None:
        self._scene.clear()
        self._draggables.clear()
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
        self._scene.setSceneRect(0, 0, w, h)
        self._redraw_points()
        if reset_view:
            self._apply_view()

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

    def _scene_radius(self, base: float) -> float:
        return base / max(self._zoom, 1e-6)

    def _hit_radius_sq(self) -> float:
        r = self._scene_radius(_HIT_RADIUS)
        return r * r

    def _update_zoom_scaled_graphics(self) -> None:
        if self._ghost_item is not None:
            pos = self._ghost_item.pos()
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = _GhostPoint(
                float(pos.x()), float(pos.y()), self._scene_radius(_ACTIVE_RADIUS)
            )
            self._scene.addItem(self._ghost_item)
        self._redraw_points()

    def _apply_view(self) -> None:
        self.resetTransform()
        if self._pix_item is None:
            return
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        if abs(self._zoom - 1.0) > 1e-6:
            self.scale(self._zoom, self._zoom)
        self._update_zoom_scaled_graphics()

    def _hit_bodypart_at(self, x: float, y: float) -> str | None:
        best: str | None = None
        best_d2 = self._hit_radius_sq()
        for name, (px, py) in self._points_on_frame.items():
            d2 = (px - x) ** 2 + (py - y) ** 2
            if d2 <= best_d2:
                best_d2 = d2
                best = name
        return best

    def _redraw_points(self) -> None:
        if self._pix_item is None:
            return
        for item in list(self._draggables.values()):
            self._scene.removeItem(item)
        self._draggables.clear()
        for name, (x, y) in self._points_on_frame.items():
            active = name == self._active_bodypart
            base = _ACTIVE_RADIUS if active else _INACTIVE_RADIUS
            radius = self._scene_radius(base)
            item = _DraggablePoint(x, y, radius, name, active)
            item.setFlag(item.ItemSendsGeometryChanges, True)
            self._scene.addItem(item)
            self._draggables[name] = item

    def wheelEvent(self, event) -> None:
        if self._pix_item is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        new_zoom = max(_MIN_ZOOM, min(_MAX_ZOOM, self._zoom * factor))
        factor = new_zoom / self._zoom
        self._zoom = new_zoom
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scale(factor, factor)
        self._update_zoom_scaled_graphics()
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._pix_item is not None:
            self._zoom = 1.0
            self._apply_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._pix_item is None:
            super().mousePressEvent(event)
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

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._active_bodypart and self._active_bodypart in self._draggables:
            item = self._draggables[self._active_bodypart]
            pos = item.pos()
            self.point_moved.emit(self._active_bodypart, float(pos.x()), float(pos.y()))
