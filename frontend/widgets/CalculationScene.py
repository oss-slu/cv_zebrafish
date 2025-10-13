from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon

class CalculationScene(QWidget):
    @pyqtSignal(str)
    def __init__(self):
        super().__init__()

        self.csv_path = None
        self.config = None

        layout = QVBoxLayout()

        self.label = QLabel("Calculation Scene")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)


    
    def set_csv_path(self, path):
        self.csv_path = path

    def set_config(self, config):
        self.config = config