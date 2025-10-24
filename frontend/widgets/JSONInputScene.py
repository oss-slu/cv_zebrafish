from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit, QTextEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon
import json
import data_schema_validation.src.json_verifier as json_verifier

class JSONInputScene(QWidget):
    json_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        header = QLabel("Input JSON")
        header.setAlignment(Qt.AlignHCenter)
        layout.addWidget(header)

        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("No file selected")
        self.path_field.setReadOnly(True)
        layout.addWidget(self.path_field)

        self.button = QPushButton("Upload JSON")
        self.button.setIcon(QIcon("public/upload-button.png"))
        self.button.setIconSize(QSize(24, 24))
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.select_file)
        layout.addWidget(self.button)

        # --- NEW: feedback display box ---
        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(120)
        layout.addWidget(self.feedback_box)

        self.setLayout(layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)")

        if file_path:
            self.path_field.setText(file_path)
            self.feedback_box.setText(
                f"Validating selected file:\n{file_path}\n")

            if self.validate_json(file_path):
                self.feedback_box.append(
                    "✅ JSON config file is valid and matches the expected schema.")
                self.json_selected.emit(file_path)
            else:
                self.feedback_box.append(
                    "❌ Invalid JSON file format (check schema validation readme).")
        else:
            self.feedback_box.setText("⚠️ File path error.")

    def validate_json(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            self.feedback_box.append(f"Error reading JSON file:\n{e}")
            return False

        errors = json_verifier.validate_config(config, json_verifier.SCHEMA)
        if hasattr(json_verifier, "extra_checks"):
            errors.extend(json_verifier.extra_checks(config))

        if errors:
            self.feedback_box.append(
                "\n❌ Validation failed with the following issues:")
            for e in errors:
                self.feedback_box.append(f" - {e}")
        else:
            self.feedback_box.append("\n✅ JSON structure is valid.")

        if hasattr(json_verifier, "guidance_messages"):
            guidance = json_verifier.guidance_messages(config)
            if guidance:
                self.feedback_box.append("\nℹ️ Guidance:")
                for m in guidance:
                    self.feedback_box.append(f" - {m}")

        return not errors
