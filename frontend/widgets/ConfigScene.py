from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton, QVBoxLayout, QWidget

from .RangeSlider import RangeSlider

class ConfigScene(QWidget):
    '''
    
    The vision:
        ** this scene will block until the CSV is received and validated.
        ** Inputs will populate dymaically based on different CSVs.
        ** This scene will create a config file based off these inputs.

    '''

    config_generated = pyqtSignal(dict)  # Emits dict with config values

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Variable Configuration Scene"))

        # Range input
        self.slider_label = QLabel("Frame: 0 - 100")
        layout.addWidget(self.slider_label)

        self.range_slider = RangeSlider(0, 100)
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
        self.slider_label.setText(f"Frame: {low} - {high}")

    def emit_config(self):
        start = min(self.range_slider.start_slider.value(), self.range_slider.end_slider.value())
        end = max(self.range_slider.start_slider.value(), self.range_slider.end_slider.value())

        config = {
            "range": (start, end),
            "toggle": self.toggle.isChecked(),
            "dropdown": self.dropdown.currentText(),
        }

        self.config_generated.emit(config)
