"""Verify Upload main panel: CSV / JSON validation and session hooks."""

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

import pandas as pd

from app_platform.paths import images_dir
from core.validation import csv_verifier as input_verifier
from core.validation import json_verifier

UPLOAD_ICON = images_dir() / "upload-button.png"
FOLDER_ICON = images_dir() / "folder-black.svg"


class VerifyWorkspace(QWidget):
    """
    Verifies CSV and JSON input files (same behavior as the former Verify scene).
    Displays two upload sections plus a shared validation console.
    """

    csv_selected = pyqtSignal(str)
    csv_folder_selected = pyqtSignal(str, object)  # (folder_path, [csv_files])
    json_selected = pyqtSignal(str)
    generate_json_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(20)

        header = QLabel("Verify Input Files")
        header.setAlignment(Qt.AlignHCenter)
        header.setStyleSheet("font-size: 20px; font-weight: bold;")
        main_layout.addWidget(header)

        csv_layout = QHBoxLayout()
        csv_label = QLabel("CSV File:")
        csv_label.setObjectName("VerifyFieldLabel")
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

        self.csv_folder_button = QPushButton("Upload Multiple CSV")
        self.csv_folder_button.setIcon(QIcon(str(FOLDER_ICON)))
        self.csv_folder_button.setIconSize(QSize(24, 24))
        self.csv_folder_button.setCursor(Qt.PointingHandCursor)
        self.csv_folder_button.clicked.connect(self.select_csv_folder)
        csv_layout.addWidget(self.csv_folder_button)
        main_layout.addLayout(csv_layout)

        json_layout = QHBoxLayout()
        json_label = QLabel("JSON File:")
        json_label.setObjectName("VerifyFieldLabel")
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

        self.generate_json_button = QPushButton("Generate JSON")
        self.generate_json_button.setCursor(Qt.PointingHandCursor)
        self.generate_json_button.clicked.connect(self.generate_json_requested.emit)
        json_layout.addWidget(self.generate_json_button)
        main_layout.addLayout(json_layout)

        console_label = QLabel("Validation Console:")
        console_label.setObjectName("VerifyConsoleLabel")
        main_layout.addWidget(console_label)

        self.feedback_box = QTextEdit()
        self.feedback_box.setObjectName("VerifyFeedbackBox")
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(200)
        self.feedback_box.setAttribute(Qt.WA_StyledBackground, True)
        main_layout.addWidget(self.feedback_box)

        self.setLayout(main_layout)

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

    def select_csv_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder of CSV Files", "")
        if not folder:
            self.feedback_box.append("Warning: Folder selection canceled.\n")
            return

        folder_path = Path(folder)
        self.csv_path_field.setText(str(folder_path))
        self.feedback_box.append(f"\n--- Validating CSV Folder ---\n{folder_path}\n")

        subdirs = [p for p in folder_path.iterdir() if p.is_dir()]
        if subdirs:
            self.feedback_box.append(
                "Error: Selected folder contains subfolders. Please select a folder with only CSV files.\n"
            )
            for sd in subdirs:
                self.feedback_box.append(f" - Subfolder: {sd.name}")
            return

        csv_files = sorted(
            [p for p in folder_path.iterdir() if p.is_file() and p.suffix.lower() == ".csv"]
        )
        if not csv_files:
            self.feedback_box.append("Error: No .csv files found in the selected folder.\n")
            return

        all_errors: list[str] = []
        all_warnings: list[str] = []

        base_sig = None
        base_name = None

        for p in csv_files:
            try:
                errors, warnings = input_verifier.verify_deeplabcut_csv(str(p))
            except Exception as exc:
                errors, warnings = [f"[ERROR] Failed to read CSV: {exc}"], []

            if errors:
                all_errors.append(f"{p.name}:")
                all_errors.extend([f"  {e}" for e in errors])
            if warnings:
                all_warnings.append(f"{p.name}:")
                all_warnings.extend([f"  {w}" for w in warnings])

            try:
                df_head = pd.read_csv(str(p), nrows=2)
                sig = (
                    tuple(df_head.columns[1:]),
                    tuple(df_head.iloc[0, 1:].tolist()),
                    tuple(df_head.iloc[1, 1:].tolist()),
                )
            except Exception as exc:
                all_errors.append(f"{p.name}:")
                all_errors.append(f"  [ERROR] Failed to read header rows for format check: {exc}")
                continue

            if base_sig is None:
                base_sig = sig
                base_name = p.name
            elif sig != base_sig:
                all_errors.append(f"{p.name}:")
                all_errors.append(
                    f"  [ERROR] CSV format does not match the first file ({base_name}). "
                    "Ensure all CSVs are exported with the same DLC bodyparts/columns."
                )

        if all_errors:
            self.feedback_box.append("\nErrors:")
            for line in all_errors:
                self.feedback_box.append(f" - {line}" if not line.startswith("  ") else line)
        if all_warnings:
            self.feedback_box.append("\nWarnings:")
            for line in all_warnings:
                self.feedback_box.append(f" - {line}" if not line.startswith("  ") else line)

        if all_errors:
            self.feedback_box.append("\nError: Folder failed validation.\n")
            return

        self.feedback_box.append(
            f"Success: Folder passed validation. {len(csv_files)} files ready.\n"
        )
        self.csv_folder_selected.emit(str(folder_path), [str(p) for p in csv_files])

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
            self.feedback_box.append("\nError: Validation failed with the following issues:")
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


class VerifyPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.verify = VerifyWorkspace()
        layout.addWidget(self.verify)
