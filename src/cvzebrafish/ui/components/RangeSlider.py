'''
A custom range slider widget for PyQt5.
Allows users to select a range between a minimum and maximum value.
Created by ChatGPT

Define the widget with RangeSlider(min, max), optionally set orientation (default is horizontal) and parent.
    -Like range_slider = RangeSlider(0, 100)

Then add the widget to the layout like any other widget.
The slider emits rangeChanged(low, high) signal on value changes.
    -range_slider.rangeChanged.connect(handler_function)
Where handler_function is a function you define to accept the two new range values. 
'''

from PyQt5.QtCore import QRect, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen
from PyQt5.QtWidgets import QSlider

class RangeSlider(QSlider):
    rangeChanged = pyqtSignal(int, int)  # low, high

    def __init__(self, min, max, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)

        self._low = min 
        self._high = max
        self._handle_radius = 7
        self._moving_low = False
        self._moving_high = False

        self.setTickPosition(QSlider.NoTicks)
        self.setMouseTracking(True)

    def lowValue(self):
        return self._low

    def highValue(self):
        return self._high

    def setLowValue(self, value):
        self._low = max(self.minimum(), min(value, self._high))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def setHighValue(self, value):
        self._high = min(self.maximum(), max(value, self._low))
        self.update()
        self.rangeChanged.emit(self._low, self._high)

    def pixelPosToRangeValue(self, pos):
        """Convert pixel x position into slider value"""
        slider_min = self._handle_radius
        slider_max = self.width() - self._handle_radius
        if self.orientation() == Qt.Vertical:
            slider_min = self._handle_radius
            slider_max = self.height() - self._handle_radius
            return int(self.minimum() + (self.maximum() - self.minimum()) *
                       (1 - (pos - slider_min) / (slider_max - slider_min)))
        else:
            return int(self.minimum() + (self.maximum() - self.minimum()) *
                       ((pos - slider_min) / (slider_max - slider_min)))

    def mousePressEvent(self, event):
        pos_value = self.pixelPosToRangeValue(event.pos().x())
        low_dist = abs(pos_value - self._low)
        high_dist = abs(pos_value - self._high)

        if low_dist < high_dist:
            self._moving_low = True
        else:
            self._moving_high = True

    def mouseMoveEvent(self, event):
        if self._moving_low or self._moving_high:
            pos_value = self.pixelPosToRangeValue(event.pos().x())
            if self._moving_low:
                self.setLowValue(min(pos_value, self._high))
            elif self._moving_high:
                self.setHighValue(max(pos_value, self._low))

    def mouseReleaseEvent(self, event):
        self._moving_low = False
        self._moving_high = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Background line
        track_rect = QRect(self._handle_radius, self.height() // 2 - 2,
                           self.width() - 2 * self._handle_radius, 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(200, 200, 200)))
        painter.drawRect(track_rect)

        # Selected range line
        min_pos = self.valueToPixelPos(self._low)
        max_pos = self.valueToPixelPos(self._high)
        selected_rect = QRect(min_pos, self.height() // 2 - 2,
                              max_pos - min_pos, 4)
        painter.setBrush(QBrush(QColor(100, 150, 250)))
        painter.drawRect(selected_rect)

        # Handles
        painter.setBrush(QBrush(QColor(50, 100, 200)))
        painter.setPen(QPen(Qt.black, 1))
        painter.drawEllipse(self.valueToPixelPos(self._low) - self._handle_radius,
                            self.height() // 2 - self._handle_radius,
                            2 * self._handle_radius, 2 * self._handle_radius)
        painter.drawEllipse(self.valueToPixelPos(self._high) - self._handle_radius,
                            self.height() // 2 - self._handle_radius,
                            2 * self._handle_radius, 2 * self._handle_radius)

    def valueToPixelPos(self, value):
        slider_min = self._handle_radius
        slider_max = self.width() - self._handle_radius
        return int(slider_min + (value - self.minimum()) /
                   (self.maximum() - self.minimum()) * (slider_max - slider_min))
