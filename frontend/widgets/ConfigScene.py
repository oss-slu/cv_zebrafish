from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QSlider, QHBoxLayout, QCheckBox, QComboBox, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal

from PyQt5.QtWidgets import QSlider
from PyQt5.QtCore import Qt, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor


class RangeSlider(QSlider):
    rangeChanged = pyqtSignal(int, int)  # emits (low, high)

    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)

        self._low = self.minimum()
        self._high = self.maximum()
        self._handle_radius = 8
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


class ConfigScene(QWidget):
    config_generated = pyqtSignal(dict)  # Emits dict with config values

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Variable Configuration Scene"))

        # Range input
        self.slider_label = QLabel("Range: 0 - 100")
        layout.addWidget(self.slider_label)

        self.range_slider = RangeSlider()
        self.range_slider.setMinimum(0)
        self.range_slider.setMaximum(500)
        self.range_slider.setLowValue(50)
        self.range_slider.setHighValue(300)
        self.range_slider.rangeChanged.connect(self.update_label)
        layout.addWidget(self.range_slider)

        # Toggle input
        self.toggle = QCheckBox("Enable Feature")
        layout.addWidget(self.toggle)

        # Dropdown menu
        self.dropdown = QComboBox()
        self.dropdown.addItems(["Option A", "Option B", "Option C"])
        layout.addWidget(self.dropdown)

        # Generate button
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.clicked.connect(self.emit_config)
        layout.addWidget(self.generate_btn)

        layout.addStretch()
        self.setLayout(layout)

    def update_label(self, low, high):
        self.slider_label.setText(f"Range: {low} - {high}")

    def emit_config(self):
        start = min(self.range_slider.start_slider.value(), self.range_slider.end_slider.value())
        end = max(self.range_slider.start_slider.value(), self.range_slider.end_slider.value())
        config = {
            "range": (start, end),
            "toggle": self.toggle.isChecked(),
            "dropdown": self.dropdown.currentText(),
        }
        self.config_generated.emit(config)
