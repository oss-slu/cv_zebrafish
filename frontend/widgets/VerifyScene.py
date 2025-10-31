from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit, QTextEdit, QHBoxLayout
)
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon
import json
import data_schema_validation.src.csv_verifier as input_verifier
import data_schema_validation.src.json_verifier as json_verifier


class VerifyScene(QWidget):
    """
    Combined scene for verifying both CSV and JSON input files.
    Displays two upload sections (CSV + JSON) and a shared console output for validation results.
    """

    csv_selected = pyqtSignal(str)
    json_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        # --- Header ---
        header = QLabel("Verify Input Files")
        header.setAlignment(Qt.AlignHCenter)
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #ddd;")
        main_layout.addWidget(header)

        # --- CSV Input Section ---
        csv_layout = QHBoxLayout()
        csv_label = QLabel("CSV File:")
        csv_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5fee55;")
        csv_layout.addWidget(csv_label)

        self.csv_path_field = QLineEdit()
        self.csv_path_field.setPlaceholderText("No CSV file selected")
        self.csv_path_field.setReadOnly(True)
        csv_layout.addWidget(self.csv_path_field)

        self.csv_button = QPushButton("Upload CSV")
        self.csv_button.setIcon(QIcon("public/upload-button.png"))
        self.csv_button.setIconSize(QSize(24, 24))
        self.csv_button.setCursor(Qt.PointingHandCursor)
        self.csv_button.clicked.connect(self.select_csv_file)
        csv_layout.addWidget(self.csv_button)

        main_layout.addLayout(csv_layout)

        # --- JSON Input Section ---
        json_layout = QHBoxLayout()
        json_label = QLabel("JSON File:")
        json_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #5f55ef;")
        json_layout.addWidget(json_label)

        self.json_path_field = QLineEdit()
        self.json_path_field.setPlaceholderText("No JSON file selected")
        self.json_path_field.setReadOnly(True)
        json_layout.addWidget(self.json_path_field)

        self.json_button = QPushButton("Upload JSON")
        self.json_button.setIcon(QIcon("public/upload-button.png"))
        self.json_button.setIconSize(QSize(24, 24))
        self.json_button.setCursor(Qt.PointingHandCursor)
        self.json_button.clicked.connect(self.select_json_file)
        json_layout.addWidget(self.json_button)

        main_layout.addLayout(json_layout)

        # --- Shared Console Output ---
        console_label = QLabel("Validation Console:")
        console_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #eee;")
        main_layout.addWidget(console_label)

        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(200)
        self.feedback_box.setStyleSheet("font-family: Consolas, monospace; font-size: 13px; color: #ddd;")
        main_layout.addWidget(self.feedback_box)

        self.setLayout(main_layout)

    # -------------------------
    # CSV Handling
    # -------------------------
    def select_csv_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select CSV File", "", "CSV Files (*.csv)"
        )

        if not file_path:
            self.feedback_box.append("⚠️ CSV file selection canceled.\n")
            return

        self.csv_path_field.setText(file_path)
        self.feedback_box.append(f"\n--- Validating CSV File ---\n{file_path}\n")

        if self.validate_csv(file_path):
            self.feedback_box.append("✅ CSV file passed all checks.\n")
            self.csv_selected.emit(file_path)
        else:
            self.feedback_box.append("❌ CSV file failed validation.\n")

    def validate_csv(self, file_path):
        try:
            errors, warnings = input_verifier.verify_deeplabcut_csv(file_path)
        except Exception as e:
            self.feedback_box.append(f"❌ Error reading CSV file:\n{e}\n")
            return False

        valid = True
        if errors:
            valid = False
            self.feedback_box.append("\n❌ Errors:")
            for err in errors:
                self.feedback_box.append(f" - {err}")
        if warnings:
            self.feedback_box.append("\n⚠️ Warnings:")
            for warn in warnings:
                self.feedback_box.append(f" - {warn}")

        if not errors and not warnings:
            self.feedback_box.append("✅ No issues found.\n")

        return valid

    # -------------------------
    # JSON Handling
    # -------------------------
    def select_json_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select JSON File", "", "JSON Files (*.json)"
        )

        if not file_path:
            self.feedback_box.append("⚠️ JSON file selection canceled.\n")
            return

        self.json_path_field.setText(file_path)
        self.feedback_box.append(f"\n--- Validating JSON File ---\n{file_path}\n")

        if self.validate_json(file_path):
            self.feedback_box.append("✅ JSON config file is valid.\n")
            self.json_selected.emit(file_path)
        else:
            self.feedback_box.append("❌ JSON file failed validation.\n")

    def validate_json(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            self.feedback_box.append(f"❌ Error reading JSON file:\n{e}\n")
            return False

        errors = json_verifier.validate_config(config, json_verifier.SCHEMA)
        if hasattr(json_verifier, "extra_checks"):
            errors.extend(json_verifier.extra_checks(config))

        valid = not errors
        if errors:
            self.feedback_box.append("\n❌ Validation failed with the following issues:")
            for e in errors:
                self.feedback_box.append(f" - {e}")
        else:
            self.feedback_box.append("\n✅ JSON structure matches schema.")

        if hasattr(json_verifier, "guidance_messages"):
            guidance = json_verifier.guidance_messages(config)
            if guidance:
                self.feedback_box.append("\nℹ️ Guidance:")
                for m in guidance:
                    self.feedback_box.append(f" - {m}")

        return valid
