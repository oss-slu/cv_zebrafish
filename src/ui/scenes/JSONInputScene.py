import json

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.validation import json_verifier
from app_platform.paths import images_dir

UPLOAD_ICON = images_dir() / "upload-button.png"


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
        self.button.setIcon(QIcon(str(UPLOAD_ICON)))
        self.button.setIconSize(QSize(24, 24))
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self.select_file)
        layout.addWidget(self.button)

        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(120)
        layout.addWidget(self.feedback_box)

        self.setLayout(layout)

    def select_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)"
        )

        if not file_path:
            self.feedback_box.setText("Warning: File path error.")
            return

        self.path_field.setText(file_path)
        self.feedback_box.setText(f"Validating selected file:\n{file_path}\n")

        if self.validate_json(file_path):
            self.feedback_box.append(
                "Success: JSON config file is valid and matches the expected schema."
            )
            self.json_selected.emit(file_path)
        else:
            self.feedback_box.append(
                "Error: Invalid JSON file format (check schema validation readme)."
            )

    def validate_json(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as exc:
            self.feedback_box.append(f"Error reading JSON file:\n{exc}")
            return False

        errors = json_verifier.validate_config(config, json_verifier.SCHEMA)
        if hasattr(json_verifier, "extra_checks"):
            errors.extend(json_verifier.extra_checks(config))

        if errors:
            self.feedback_box.append(
                "\nError: Validation failed with the following issues:"
            )
            for err in errors:
                self.feedback_box.append(f" - {err}")
        else:
            self.feedback_box.append("\nSuccess: JSON structure is valid.")

        if hasattr(json_verifier, "guidance_messages"):
            guidance = json_verifier.guidance_messages(config)
            if guidance:
                self.feedback_box.append("\nGuidance:")
                for message in guidance:
                    self.feedback_box.append(f" - {message}")

        return not errors
