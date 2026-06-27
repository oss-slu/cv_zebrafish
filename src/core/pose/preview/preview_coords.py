"""Map between widget display coords and frame pixel / normalized arena coords."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import QRect, QSize, Qt


@dataclass
class DisplayMapping:
    """How the frame pixmap is drawn inside a QLabel (KeepAspectRatio, centered)."""

    frame_w: int
    frame_h: int
    widget_w: int
    widget_h: int
    draw_x: int
    draw_y: int
    draw_w: int
    draw_h: int

    @classmethod
    def from_sizes(cls, frame_w: int, frame_h: int, widget_w: int, widget_h: int) -> "DisplayMapping":
        if frame_w <= 0 or frame_h <= 0 or widget_w <= 0 or widget_h <= 0:
            return cls(frame_w, frame_h, widget_w, widget_h, 0, 0, 0, 0)
        scaled = QSize(frame_w, frame_h).scaled(widget_w, widget_h, Qt.KeepAspectRatio)
        draw_w = max(1, scaled.width())
        draw_h = max(1, scaled.height())
        draw_x = (widget_w - draw_w) // 2
        draw_y = (widget_h - draw_h) // 2
        return cls(frame_w, frame_h, widget_w, widget_h, draw_x, draw_y, draw_w, draw_h)

    def widget_to_frame(self, wx: float, wy: float) -> tuple[float, float] | None:
        if self.draw_w <= 0 or self.draw_h <= 0:
            return None
        lx = wx - self.draw_x
        ly = wy - self.draw_y
        if lx < 0 or ly < 0 or lx > self.draw_w or ly > self.draw_h:
            return None
        fx = lx * self.frame_w / self.draw_w
        fy = ly * self.frame_h / self.draw_h
        return fx, fy

    def widget_to_normalized(self, wx: float, wy: float) -> tuple[float, float] | None:
        pt = self.widget_to_frame(wx, wy)
        if pt is None or self.frame_w <= 0 or self.frame_h <= 0:
            return None
        return pt[0] / self.frame_w, pt[1] / self.frame_h

    def frame_to_widget(self, fx: float, fy: float) -> tuple[float, float]:
        if self.frame_w <= 0 or self.frame_h <= 0:
            return 0.0, 0.0
        lx = fx * self.draw_w / self.frame_w
        ly = fy * self.draw_h / self.frame_h
        return self.draw_x + lx, self.draw_y + ly

    def hit_rect(self) -> QRect:
        return QRect(self.draw_x, self.draw_y, self.draw_w, self.draw_h)


def wheel_arena_size_delta(angle_delta_y: int) -> float:
    """
    Scroll-wheel arena resize step with accelerating magnitude.

    Small notches → fine adjustment; large/fast scroll → coarser steps.
    """
    notches = angle_delta_y / 120.0
    magnitude = abs(notches)
    if magnitude < 1.5:
        step = 0.008
    elif magnitude < 3.5:
        step = 0.02
    else:
        step = 0.045
    sign = 1.0 if notches > 0 else -1.0
    return sign * step * min(magnitude, 4.0)
