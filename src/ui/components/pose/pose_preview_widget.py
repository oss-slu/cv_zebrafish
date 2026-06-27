"""OpenCV frame preview with arena, blob mask, and square crop overlays."""

from __future__ import annotations

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QPoint, pyqtSignal
from PyQt5.QtGui import QImage, QPainter, QPen, QColor, QPolygon
from PyQt5.QtWidgets import QLabel

from core.pose.detection.arena import ArenaConfig, arena_mask, arena_rect_pixels
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop
from core.pose.cache.playback_blob_cache import PlaybackBlobEntry
from core.pose.preview.preview_coords import DisplayMapping, wheel_arena_size_delta
from core.pose.video.video_reader import downscale_frame


class PosePreviewWidget(QLabel):
    """Frame preview; optional interactive arena editing on the Setup tab."""

    arena_changed = pyqtSignal(object)

    _EDGE_HIT_FRAC = 0.06
    _MIN_RECT_FRAC = 0.05

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PosePreviewWidget")
        self.setMinimumSize(320, 240)
        self.setAlignment(Qt.AlignCenter)
        self.setText("No frame")
        self.setMouseTracking(True)
        self._frame_bgr: np.ndarray | None = None
        self._frame_bgr_source: np.ndarray | None = None
        self._display_scale = 1.0
        self._arena = ArenaConfig()
        self._blob_params = BlobParams()
        self._blob: BlobResult | None = None
        self._show_mask = True
        self._show_crop = True
        self._blob_enabled = False
        self._dim_outside_arena = False
        self._arena_editable = False
        self._preview_max_edge: int | None = None
        self._drag_mode: str | None = None
        self._drag_start_norm: tuple[float, float] | None = None
        self._arena_at_drag_start: ArenaConfig | None = None
        self._last_mapping = DisplayMapping(0, 0, 0, 0, 0, 0, 0, 0)
        self._playback_mode = False
        self._playback_entry: PlaybackBlobEntry | None = None
        self._last_paint_size: tuple[int, int] | None = None

    def set_arena_editable(self, enabled: bool) -> None:
        self._arena_editable = enabled
        self.setCursor(Qt.OpenHandCursor if enabled and self._frame_bgr is not None else Qt.ArrowCursor)

    def set_preview_max_edge(self, edge: int | None) -> None:
        self._preview_max_edge = int(edge) if edge else None

    def set_blob_enabled(self, enabled: bool) -> None:
        self._blob_enabled = bool(enabled)
        self._recompute_blob()
        self._paint()

    def set_dim_outside_arena(self, enabled: bool) -> None:
        self._dim_outside_arena = bool(enabled)
        self._paint()

    def set_playback_mode(self, enabled: bool) -> None:
        self._playback_mode = bool(enabled)
        if not enabled:
            self._playback_entry = None

    def set_frame_bgr(
        self,
        frame: np.ndarray | None,
        *,
        update_blob: bool = True,
        blob: BlobResult | None = None,
        playback_entry: PlaybackBlobEntry | None = None,
        playback: bool = False,
    ) -> None:
        self._playback_mode = playback
        self._playback_entry = playback_entry
        self._frame_bgr_source = frame
        display = frame
        self._display_scale = 1.0
        if frame is not None and self._preview_max_edge:
            display = downscale_frame(frame, self._preview_max_edge)
            sh, sw = display.shape[:2]
            fh, fw = frame.shape[:2]
            if fw > 0:
                self._display_scale = sw / fw
        self._frame_bgr = display
        if frame is not None and self._arena.is_rectangle():
            fh, fw = frame.shape[:2]
            self._arena.ensure_explicit_rect(fw, fh)
        if blob is not None:
            self._blob = blob
        elif update_blob:
            self._recompute_blob()
        else:
            self._blob = None
        self._paint()

    def clear_frame(self) -> None:
        """Drop any displayed frame and overlays (e.g. when switching sessions)."""
        self._frame_bgr_source = None
        self._frame_bgr = None
        self._blob = None
        self._display_scale = 1.0
        self._drag_mode = None
        self._drag_start_norm = None
        self._arena_at_drag_start = None
        self._playback_mode = False
        self._playback_entry = None
        self._last_paint_size = None
        QLabel.clear(self)
        self.setText("No frame")

    def set_arena(self, arena: ArenaConfig) -> None:
        self._arena = arena
        if self._frame_bgr is not None and self._arena.is_rectangle():
            fh, fw = self._frame_bgr.shape[:2]
            self._arena.ensure_explicit_rect(fw, fh)
        self._recompute_blob()
        self._paint()

    def set_blob_params(self, params: BlobParams) -> None:
        self._blob_params = params
        self._recompute_blob()
        self._paint()

    def _mapping(self) -> DisplayMapping:
        if self._frame_bgr is None:
            return DisplayMapping(0, 0, self.width(), self.height(), 0, 0, 0, 0)
        h, w = self._frame_bgr.shape[:2]
        return DisplayMapping.from_sizes(w, h, self.width(), self.height())

    def _frame_size(self) -> tuple[int, int]:
        if self._frame_bgr is None:
            return 0, 0
        h, w = self._frame_bgr.shape[:2]
        return w, h

    def _rect_bounds_px(self) -> tuple[int, int, int, int]:
        w, h = self._frame_size()
        return arena_rect_pixels(h, w, self._arena)

    def _edge_threshold_px(self, x0: int, y0: int, x1: int, y1: int) -> float:
        side = max(1.0, min(x1 - x0, y1 - y0))
        return max(10.0, side * self._EDGE_HIT_FRAC)

    def _hit_circle_center(self, nx: float, ny: float) -> bool:
        if self._frame_bgr is None or self._arena.shape != "circle":
            return False
        w, h = self._frame_size()
        min_edge = min(h, w)
        cx = self._arena.center_x * w
        cy = self._arena.center_y * h
        half = self._arena.size * min_edge / 2.0
        thresh = max(12.0, half * 0.12)
        dx = nx * w - cx
        dy = ny * h - cy
        return (dx * dx + dy * dy) ** 0.5 <= thresh

    def _pick_rectangle_drag_mode(self, nx: float, ny: float) -> str | None:
        if self._frame_bgr is None or not self._arena.is_rectangle():
            return None
        w, h = self._frame_size()
        fx, fy = nx * w, ny * h
        x0, y0, x1, y1 = self._rect_bounds_px()
        thresh = self._edge_threshold_px(x0, y0, x1, y1)
        near_l = abs(fx - x0) <= thresh
        near_r = abs(fx - x1) <= thresh
        near_t = abs(fy - y0) <= thresh
        near_b = abs(fy - y1) <= thresh
        inside_x = x0 + thresh < fx < x1 - thresh
        inside_y = y0 + thresh < fy < y1 - thresh
        if inside_x and inside_y:
            return "move"
        if near_l and near_t:
            return "resize_tl"
        if near_r and near_t:
            return "resize_tr"
        if near_l and near_b:
            return "resize_bl"
        if near_r and near_b:
            return "resize_br"
        if near_l and y0 - thresh <= fy <= y1 + thresh:
            return "resize_l"
        if near_r and y0 - thresh <= fy <= y1 + thresh:
            return "resize_r"
        if near_t and x0 - thresh <= fx <= x1 + thresh:
            return "resize_t"
        if near_b and x0 - thresh <= fx <= x1 + thresh:
            return "resize_b"
        return None

    def _cursor_for_drag_mode(self, mode: str | None):
        mapping = {
            "move": Qt.OpenHandCursor,
            "resize_l": Qt.SizeHorCursor,
            "resize_r": Qt.SizeHorCursor,
            "resize_t": Qt.SizeVerCursor,
            "resize_b": Qt.SizeVerCursor,
            "resize_tl": Qt.SizeFDiagCursor,
            "resize_br": Qt.SizeFDiagCursor,
            "resize_tr": Qt.SizeBDiagCursor,
            "resize_bl": Qt.SizeBDiagCursor,
            "circle_resize": Qt.SizeFDiagCursor,
        }
        return mapping.get(mode or "", Qt.ArrowCursor)

    def _apply_rectangle_drag(self, nx: float, ny: float) -> None:
        assert self._arena_at_drag_start is not None
        start = self._arena_at_drag_start
        w, h = self._frame_size()
        sx0 = start.rect_x
        sy0 = start.rect_y
        sw = start.rect_w
        sh = start.rect_h
        min_f = self._MIN_RECT_FRAC
        mode = self._drag_mode or ""
        if mode == "move":
            dx = nx - (self._drag_start_norm or (0, 0))[0]
            dy = ny - (self._drag_start_norm or (0, 0))[1]
            self._arena.rect_x = max(0.0, min(1.0 - sw, sx0 + dx))
            self._arena.rect_y = max(0.0, min(1.0 - sh, sy0 + dy))
        elif mode == "resize_l":
            x1 = sx0 + sw
            new_x = max(0.0, min(x1 - min_f, nx))
            self._arena.rect_x = new_x
            self._arena.rect_w = max(min_f, x1 - new_x)
        elif mode == "resize_r":
            self._arena.rect_w = max(min_f, min(1.0 - sx0, nx - sx0))
        elif mode == "resize_t":
            y1 = sy0 + sh
            new_y = max(0.0, min(y1 - min_f, ny))
            self._arena.rect_y = new_y
            self._arena.rect_h = max(min_f, y1 - new_y)
        elif mode == "resize_b":
            self._arena.rect_h = max(min_f, min(1.0 - sy0, ny - sy0))
        elif mode == "resize_tl":
            x1, y1 = sx0 + sw, sy0 + sh
            new_x = max(0.0, min(x1 - min_f, nx))
            new_y = max(0.0, min(y1 - min_f, ny))
            self._arena.rect_x = new_x
            self._arena.rect_y = new_y
            self._arena.rect_w = max(min_f, x1 - new_x)
            self._arena.rect_h = max(min_f, y1 - new_y)
        elif mode == "resize_tr":
            y1 = sy0 + sh
            new_y = max(0.0, min(y1 - min_f, ny))
            self._arena.rect_y = new_y
            self._arena.rect_w = max(min_f, min(1.0 - sx0, nx - sx0))
            self._arena.rect_h = max(min_f, y1 - new_y)
        elif mode == "resize_bl":
            x1 = sx0 + sw
            new_x = max(0.0, min(x1 - min_f, nx))
            self._arena.rect_x = new_x
            self._arena.rect_w = max(min_f, x1 - new_x)
            self._arena.rect_h = max(min_f, min(1.0 - sy0, ny - sy0))
        elif mode == "resize_br":
            self._arena.rect_w = max(min_f, min(1.0 - sx0, nx - sx0))
            self._arena.rect_h = max(min_f, min(1.0 - sy0, ny - sy0))
        self._arena.uses_rect = True
        self._arena.clamp_rectangle()

    def _recompute_blob(self) -> None:
        if self._frame_bgr is None or not self._blob_enabled:
            self._blob = None
            return
        self._blob = detect_blob_square_crop(
            self._frame_bgr, self._arena, self._blob_params
        )

    def _apply_mask_tint(self, disp: np.ndarray, h: int, w: int) -> None:
        if not self._blob_enabled or not self._show_mask or self._blob is None or not self._blob.found:
            return
        mask_small = self._blob.mask
        if mask_small.size == 0:
            return
        if mask_small.shape[:2] != (h, w):
            mask_small = (
                cv2.resize(
                    mask_small.astype(np.uint8),
                    (w, h),
                    interpolation=cv2.INTER_NEAREST,
                )
                > 0
            )
        overlay = disp.copy()
        overlay[mask_small] = (0, 160, 60)
        blended = cv2.addWeighted(disp, 0.88, overlay, 0.12, 0)
        disp[:] = blended

    def _draw_playback_overlays(self, painter: QPainter) -> None:
        """Fallback outlines when no mask bitmap is available."""
        entry = self._playback_entry
        if entry is None or not entry.found:
            return
        painter.setPen(QPen(QColor(70, 255, 120), 2))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(
            entry.fish_x0,
            entry.fish_y0,
            entry.fish_x1 - entry.fish_x0,
            entry.fish_y1 - entry.fish_y0,
        )
        if self._show_crop:
            painter.setPen(QPen(QColor(255, 200, 60), 2, Qt.DashLine))
            painter.drawRect(entry.crop_x0, entry.crop_y0, entry.crop_side, entry.crop_side)

    def _draw_blob_outline(self, painter: QPainter) -> None:
        if not self._blob_enabled or self._blob is None or not self._blob.found:
            return
        mask_u8 = self._blob.mask.astype(np.uint8)
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return
        painter.setPen(QPen(QColor(70, 255, 120), 2))
        painter.setBrush(Qt.NoBrush)
        for cnt in contours:
            if len(cnt) < 3:
                continue
            poly = QPolygon(
                [QPoint(int(p[0][0]), int(p[0][1])) for p in cnt]
            )
            painter.drawPolygon(poly)

    def _blob_has_mask(self) -> bool:
        return (
            self._blob is not None
            and self._blob.found
            and self._blob.mask.size > 1
        )

    def _paint(self) -> None:
        if self._frame_bgr is None:
            self.clear()
            self.setText("No frame")
            return
        h, w = self._frame_bgr.shape[:2]
        needs_copy = (
            (not self._playback_mode and self._dim_outside_arena)
            or (self._blob_enabled and self._show_mask and self._blob_has_mask())
        )
        disp = self._frame_bgr.copy() if needs_copy else self._frame_bgr
        if not self._playback_mode and self._dim_outside_arena:
            mask = arena_mask(h, w, self._arena)
            outside = ~mask
            disp[outside] = (disp[outside].astype(np.float32) * 0.28).astype(np.uint8)
        if self._blob_enabled and self._show_mask and self._blob_has_mask():
            self._apply_mask_tint(disp, h, w)
        rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        from PyQt5.QtGui import QPixmap

        pix = QPixmap.fromImage(qimg)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        pen_arena = QPen(QColor(80, 160, 255), 2)
        painter.setPen(pen_arena)
        if self._arena.shape == "circle":
            x0, y0, x1, y1 = arena_rect_pixels(h, w, self._arena)
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            half = (x1 - x0) / 2.0
            painter.drawEllipse(int(cx - half), int(cy - half), int(2 * half), int(2 * half))
        else:
            x0, y0, x1, y1 = arena_rect_pixels(h, w, self._arena)
            painter.drawRect(x0, y0, x1 - x0, y1 - y0)
        if self._playback_mode:
            if self._blob_enabled:
                if self._blob_has_mask():
                    self._draw_blob_outline(painter)
                else:
                    self._draw_playback_overlays(painter)
                if self._show_crop and self._blob is not None and self._blob.found:
                    pen_crop = QPen(QColor(255, 200, 60), 2, Qt.DashLine)
                    painter.setPen(pen_crop)
                    painter.drawRect(self._blob.x0, self._blob.y0, self._blob.side, self._blob.side)
        else:
            self._draw_blob_outline(painter)
            if self._blob_enabled and self._show_crop and self._blob is not None and self._blob.found:
                pen_crop = QPen(QColor(255, 200, 60), 2, Qt.DashLine)
                painter.setPen(pen_crop)
                painter.drawRect(self._blob.x0, self._blob.y0, self._blob.side, self._blob.side)
        painter.end()
        self._last_mapping = self._mapping()
        target = self.size()
        if self._playback_mode and self._last_paint_size == (target.width(), target.height()):
            self.setPixmap(pix.scaled(target, Qt.KeepAspectRatio, Qt.FastTransformation))
        else:
            self.setPixmap(pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._last_paint_size = (target.width(), target.height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._playback_mode:
            self._paint()

    def mousePressEvent(self, event) -> None:
        if not self._arena_editable or self._frame_bgr is None or event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        norm = self._last_mapping.widget_to_normalized(event.x(), event.y())
        if norm is None:
            return
        nx, ny = norm
        mode: str | None = None
        if self._arena.shape == "circle":
            if self._hit_circle_center(nx, ny):
                mode = "move"
            else:
                mode = "circle_resize"
        else:
            mode = self._pick_rectangle_drag_mode(nx, ny)
        if mode is None:
            return
        self._drag_mode = mode
        self._drag_start_norm = (nx, ny)
        self._arena_at_drag_start = self._arena.clone()
        self.setCursor(
            Qt.ClosedHandCursor if mode == "move" else self._cursor_for_drag_mode(mode)
        )
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_mode and self._drag_start_norm and self._arena_at_drag_start:
            norm = self._last_mapping.widget_to_normalized(event.x(), event.y())
            if norm is None:
                return
            nx, ny = norm
            if self._arena.shape == "circle":
                if self._drag_mode == "move":
                    dx = nx - self._drag_start_norm[0]
                    dy = ny - self._drag_start_norm[1]
                    self._arena.center_x = max(0.05, min(0.95, self._arena_at_drag_start.center_x + dx))
                    self._arena.center_y = max(0.05, min(0.95, self._arena_at_drag_start.center_y + dy))
                elif self._drag_mode == "circle_resize":
                    w, h = self._frame_size()
                    min_edge = min(h, w)
                    cx = self._arena_at_drag_start.center_x * w
                    cy = self._arena_at_drag_start.center_y * h
                    fx, fy = nx * w, ny * h
                    half_px = max(abs(fx - cx), abs(fy - cy))
                    self._arena.size = max(0.1, min(1.0, (2.0 * half_px) / min_edge))
            else:
                self._apply_rectangle_drag(nx, ny)
            self._recompute_blob()
            self._paint()
            self.arena_changed.emit(self._arena)
            event.accept()
            return
        if self._arena_editable and self._frame_bgr is not None:
            norm = self._last_mapping.widget_to_normalized(event.x(), event.y())
            if norm:
                if self._arena.shape == "circle":
                    mode = "move" if self._hit_circle_center(norm[0], norm[1]) else "circle_resize"
                else:
                    mode = self._pick_rectangle_drag_mode(norm[0], norm[1])
                self.setCursor(self._cursor_for_drag_mode(mode))
            else:
                self.setCursor(Qt.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._drag_mode:
            self._drag_mode = None
            self._drag_start_norm = None
            self._arena_at_drag_start = None
            self.setCursor(Qt.OpenHandCursor if self._arena_editable else Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        if self._arena_editable and self._frame_bgr is not None and self._arena.shape == "circle":
            delta = wheel_arena_size_delta(event.angleDelta().y())
            self._arena.size = max(0.1, min(1.0, self._arena.size + delta))
            self._recompute_blob()
            self._paint()
            self.arena_changed.emit(self._arena)
            event.accept()
            return
        super().wheelEvent(event)
