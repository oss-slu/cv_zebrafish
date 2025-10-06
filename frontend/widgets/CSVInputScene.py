from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon

# imports the input_verifier module from the parent directory 
from os import getcwd, path
module_name = "input_verifier"
parent_dir = path.abspath(path.join(getcwd(), path.pardir))
file_path = path.join(parent_dir, "data_schema_validation", "src", module_name + ".py")

import importlib.util
from sys import modules

# loads the csv verification module
spec = importlib.util.spec_from_file_location(module_name, file_path)
input_verifier = importlib.util.module_from_spec(spec)
modules[module_name] = input_verifier
spec.loader.exec_module(input_verifier)

class CSVInputScene(QWidget):
    csv_selected = pyqtSignal(str)  # emits file path when selected

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        header = QLabel("Input CSV")
        header.setAlignment(Qt.AlignHCenter)
        layout.addWidget(header)

        # stored in object because path_field will be used by other methods
        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("No file selected")
        self.path_field.setReadOnly(True)
        layout.addWidget(self.path_field)

        # creates button and shows the upload icon
        self.button = QPushButton("Upload CSV")
        self.button.setIcon(QIcon("public/upload-button.png"))
        self.button.setIconSize(QSize(24,24))
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.select_file) # connects signal handler
        layout.addWidget(self.button)
        
        self.setLayout(layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select CSV File", "", "CSV Files (*.csv)")

        if file_path:
            self.path_field.setText(file_path)
            print(f"Validating selected file: {file_path}...")

            # checks for valid csv file format
            if (self.validate_csv(file_path)):
                self.csv_selected.emit(file_path)
            else:
                print("\nInvalid CSV file format (check schema validation readme)")
        else:
            print("File path error")

    def validate_csv(self, file_path):
        errors, warnings = input_verifier.verify_deeplabcut_csv(file_path)

        if not errors and not warnings:
            print("✅ File passed all checks.")
        else:
            print("\n".join(errors + warnings))

        return not errors  # returns True if no errors

