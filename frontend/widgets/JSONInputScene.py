from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon
import importlib.util
from sys import modules
from os import getcwd, path
import json

# imports the csv_verifier module from the parent directory
module_name = "json_verifier"
parent_dir = path.abspath(path.join(getcwd(), path.pardir))
file_path = path.join(parent_dir, "data_schema_validation",
                      "src", module_name + ".py")

# loads the csv verification module
spec = importlib.util.spec_from_file_location(module_name, file_path)
json_verifier = importlib.util.module_from_spec(spec)
modules[module_name] = json_verifier
spec.loader.exec_module(json_verifier)
print("loading json verifier...")


class JSONInputScene(QWidget):
    json_selected = pyqtSignal(str)  # emits file path when selected

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        header = QLabel("Input JSON")
        header.setAlignment(Qt.AlignHCenter)
        layout.addWidget(header)

        # stored in object because path_field will be used by other methods
        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("No file selected")
        self.path_field.setReadOnly(True)
        layout.addWidget(self.path_field)

        # creates button and shows the upload icon
        self.button = QPushButton("Upload JSON")
        self.button.setIcon(QIcon("public/upload-button.png"))
        self.button.setIconSize(QSize(24, 24))
        self.button.setCursor(Qt.PointingHandCursor)
        # connects signal handler
        self.button.clicked.connect(self.select_file)
        layout.addWidget(self.button)

        self.setLayout(layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)")

        if file_path:
            self.path_field.setText(file_path)
            print(f"Validating selected file: {file_path}...")

            # checks for valid csv file format
            if (self.validate_json(file_path)):
                self.json_selected.emit(file_path)
            else:
                print("\nInvalid JSON file format (check schema validation readme)")
        else:
            print("File path error")

    def validate_json(self, file_path):
        # Load JSON file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"Error reading JSON file: {e}")
            return False

        # Validate against schema and run extra semantic checks
        errors = json_verifier.validate_config(config, json_verifier.SCHEMA)
        # extra_checks may not exist in older verifier versions
        if hasattr(json_verifier, "extra_checks"):
            errors.extend(json_verifier.extra_checks(config))

        if errors:
            print("❌ Validation failed with the following issues:")
            for e in errors:
                print(" -", e)
        else:
            print("✅ JSON config file is valid and matches the expected schema.")

        # Optional guidance messages (if provided by verifier)
        guidance = []
        if hasattr(json_verifier, "guidance_messages"):
            guidance = json_verifier.guidance_messages(config)
        if guidance:
            print("\nℹ️  Guidance:")
            for m in guidance:
                print(" -", m)

        return not errors
