from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QSlider, QHBoxLayout, QCheckBox, QComboBox, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal


class RangeSlider(QWidget):
    """Custom double-ended range slider for selecting frame ranges."""
    range_changed = pyqtSignal(int, int)

    def __init__(self, minimum=0, maximum=100, start=10, end=90):
        super().__init__()
        layout = QVBoxLayout()

        self.label = QLabel(f"Range: {start} - {end}")
        layout.addWidget(self.label)

        slider_layout = QHBoxLayout()
        self.start_slider = QSlider(Qt.Horizontal)
        self.start_slider.setRange(minimum, maximum)
        self.start_slider.setValue(start)

        self.end_slider = QSlider(Qt.Horizontal)
        self.end_slider.setRange(minimum, maximum)
        self.end_slider.setValue(end)

        self.start_slider.valueChanged.connect(self.update_label)
        self.end_slider.valueChanged.connect(self.update_label)

        slider_layout.addWidget(self.start_slider)
        slider_layout.addWidget(self.end_slider)

        layout.addLayout(slider_layout)
        self.setLayout(layout)

    def update_label(self):
        start = min(self.start_slider.value(), self.end_slider.value())
        end = max(self.start_slider.value(), self.end_slider.value())
        self.label.setText(f"Range: {start} - {end}")
        self.range_changed.emit(start, end)


class ConfigScene(QWidget):
    config_generated = pyqtSignal(dict)  # Emits dict with config values

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Variable Configuration Scene"))

        # Range input
        self.range_slider = RangeSlider(0, 500, 50, 300)
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

    def emit_config(self):
        start = min(self.range_slider.start_slider.value(), self.range_slider.end_slider.value())
        end = max(self.range_slider.start_slider.value(), self.range_slider.end_slider.value())
        config = {
            "range": (start, end),
            "toggle": self.toggle.isChecked(),
            "dropdown": self.dropdown.currentText(),
        }
        self.config_generated.emit(config)
