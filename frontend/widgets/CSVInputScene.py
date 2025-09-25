from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize, QSizePolicy
from PyQt5.QtGui import QIcon

class CSVInputScene(QWidget):
    csv_selected = pyqtSignal(str)  # emits file path when selected

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        header = QLabel("CSV Input Scene")
        header.setAlignment(Qt.AlignHCenter)
        header.setSizePolicy(QSizePolicy.Fixed)
        layout.addWidget(header)

        # stored in object becaues path_field will be used by other methods
        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("No file selected")
        self.path_field.setReadOnly(True)

        self.button = QPushButton("Select CSV")
        self.button.setIcon(QIcon('../public/upload-button.png'))
        self.button.setIconSize(QSize(24,24))
        self.button.clicked.connect(self.select_file)

        layout.addWidget(self.path_field)
        layout.addWidget(self.button)
        self.setLayout(layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")

        if file_path:
            self.path_field.setText(file_path)
            self.csv_selected.emit(file_path)
