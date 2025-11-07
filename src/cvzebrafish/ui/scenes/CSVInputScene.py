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

from cvzebrafish.core.validation import csv_verifier as input_verifier
from cvzebrafish.platform.paths import images_dir

UPLOAD_ICON = images_dir() / "upload-button.png"


class CSVInputScene(QWidget):
    csv_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        header = QLabel("Input CSV")
        header.setAlignment(Qt.AlignHCenter)
        layout.addWidget(header)

        self.path_field = QLineEdit()
        self.path_field.setPlaceholderText("No file selected")
        self.path_field.setReadOnly(True)
        layout.addWidget(self.path_field)

        self.button = QPushButton("Upload CSV")
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
            self, "Select CSV File", "", "CSV Files (*.csv)"
        )

        if not file_path:
            self.feedback_box.setText("Warning: File path error.")
            return

        self.path_field.setText(file_path)
        self.feedback_box.setText(f"Validating selected file:\n{file_path}\n")

        if self.validate_csv(file_path):
            self.feedback_box.append("Success: File passed all checks.")
            self.csv_selected.emit(file_path)
        else:
            self.feedback_box.append(
                "Error: Invalid CSV file format (see schema validation readme)."
            )

    def validate_csv(self, file_path):
        try:
            errors, warnings = input_verifier.verify_deeplabcut_csv(file_path)
        except Exception as exc:
            self.feedback_box.append(f"Error reading CSV file:\n{exc}")
            return False

        if not errors and not warnings:
            self.feedback_box.append("Success: No issues found.")
        else:
            if errors:
                self.feedback_box.append("\nErrors:")
                for err in errors:
                    self.feedback_box.append(f" - {err}")
            if warnings:
                self.feedback_box.append("\nWarnings:")
                for warn in warnings:
                    self.feedback_box.append(f" - {warn}")

        return not errors
