import json
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cvzebrafish.core.validation import csv_verifier as input_verifier
from cvzebrafish.core.validation import json_verifier
from cvzebrafish.platform.paths import images_dir

UPLOAD_ICON = images_dir() / "upload-button.png"


class VerifyScene(QWidget):
    """
    Combined scene for verifying both CSV and JSON input files.
    Displays two upload sections (CSV + JSON) and a shared console output.
    """

    csv_selected = pyqtSignal(str)
    json_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        header = QLabel("Verify Input Files")
        header.setAlignment(Qt.AlignHCenter)
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #ddd;")
        main_layout.addWidget(header)

        csv_layout = QHBoxLayout()
        csv_label = QLabel("CSV File:")
        csv_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5fee55;")
        csv_layout.addWidget(csv_label)

        self.csv_path_field = QLineEdit()
        self.csv_path_field.setPlaceholderText("No CSV file selected")
        self.csv_path_field.setReadOnly(True)
        csv_layout.addWidget(self.csv_path_field)

        self.csv_button = QPushButton("Upload CSV")
        self.csv_button.setIcon(QIcon(str(UPLOAD_ICON)))
        self.csv_button.setIconSize(QSize(24, 24))
        self.csv_button.setCursor(Qt.PointingHandCursor)
        self.csv_button.clicked.connect(self.select_csv_file)
        csv_layout.addWidget(self.csv_button)
        main_layout.addLayout(csv_layout)

        json_layout = QHBoxLayout()
        json_label = QLabel("JSON File:")
        json_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5f55ef;")
        json_layout.addWidget(json_label)

        self.json_path_field = QLineEdit()
        self.json_path_field.setPlaceholderText("No JSON file selected")
        self.json_path_field.setReadOnly(True)
        json_layout.addWidget(self.json_path_field)

        self.json_button = QPushButton("Upload JSON")
        self.json_button.setIcon(QIcon(str(UPLOAD_ICON)))
        self.json_button.setIconSize(QSize(24, 24))
        self.json_button.setCursor(Qt.PointingHandCursor)
        self.json_button.clicked.connect(self.select_json_file)
        json_layout.addWidget(self.json_button)
        main_layout.addLayout(json_layout)

        console_label = QLabel("Validation Console:")
        console_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #eee;")
        main_layout.addWidget(console_label)

        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(200)
        self.feedback_box.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 13px; color: #ddd;"
        )
        main_layout.addWidget(self.feedback_box)

        self.setLayout(main_layout)

    # CSV handling
    def select_csv_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv)"
        )

        if not file_path:
            self.feedback_box.append("Warning: CSV file selection canceled.\n")
            return

        self.csv_path_field.setText(file_path)
        self.feedback_box.append(f"\n--- Validating CSV File ---\n{file_path}\n")

        if self.validate_csv(Path(file_path)):
            self.feedback_box.append("Success: CSV file passed all checks.\n")
            self.csv_selected.emit(file_path)
        else:
            self.feedback_box.append("Error: CSV file failed validation.\n")

    def validate_csv(self, file_path: Path) -> bool:
        try:
            errors, warnings = input_verifier.verify_deeplabcut_csv(str(file_path))
        except Exception as exc:
            self.feedback_box.append(f"Error reading CSV file:\n{exc}\n")
            return False

        valid = True
        if errors:
            valid = False
            self.feedback_box.append("\nErrors:")
            for err in errors:
                self.feedback_box.append(f" - {err}")
        if warnings:
            self.feedback_box.append("\nWarnings:")
            for warn in warnings:
                self.feedback_box.append(f" - {warn}")

        if not errors and not warnings:
            self.feedback_box.append("Success: No issues found.\n")

        return valid

    # JSON handling
    def select_json_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)"
        )

        if not file_path:
            self.feedback_box.append("Warning: JSON file selection canceled.\n")
            return

        self.json_path_field.setText(file_path)
        self.feedback_box.append(f"\n--- Validating JSON File ---\n{file_path}\n")

        if self.validate_json(Path(file_path)):
            self.feedback_box.append("Success: JSON config file is valid.\n")
            self.json_selected.emit(file_path)
        else:
            self.feedback_box.append("Error: JSON file failed validation.\n")

    def validate_json(self, file_path: Path) -> bool:
        try:
            with file_path.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
        except Exception as exc:
            self.feedback_box.append(f"Error reading JSON file:\n{exc}\n")
            return False

        errors = json_verifier.validate_config(config, json_verifier.SCHEMA)
        if hasattr(json_verifier, "extra_checks"):
            errors.extend(json_verifier.extra_checks(config))

        valid = not errors
        if errors:
            self.feedback_box.append(
                "\nError: Validation failed with the following issues:"
            )
            for err in errors:
                self.feedback_box.append(f" - {err}")
        else:
            self.feedback_box.append("\nSuccess: JSON structure matches schema.")

        if hasattr(json_verifier, "guidance_messages"):
            guidance = json_verifier.guidance_messages(config)
            if guidance:
                self.feedback_box.append("\nGuidance:")
                for message in guidance:
                    self.feedback_box.append(f" - {message}")

        return valid
