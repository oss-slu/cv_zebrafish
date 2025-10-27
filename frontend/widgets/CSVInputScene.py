from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit, QTextEdit
from PyQt5.QtCore import pyqtSignal, Qt, QSize
from PyQt5.QtGui import QIcon
import data_schema_validation.src.csv_verifier as input_verifier

class CSVInputScene(QWidget):
    csv_selected = pyqtSignal(str)  # emits file path when selected

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
            self, "Select CSV File", "", "CSV Files (*.csv)")

        if file_path:
            self.path_field.setText(file_path)
            self.feedback_box.setText(
                f"Validating selected file:\n{file_path}\n")

            if self.validate_csv(file_path):
                self.feedback_box.append("✅ File passed all checks.")
                self.csv_selected.emit(file_path)
            else:
                self.feedback_box.append(
                    "❌ Invalid CSV file format (see schema validation readme).")
        else:
            self.feedback_box.setText("⚠️ File path error.")

    def validate_csv(self, file_path):
        try:
            errors, warnings = input_verifier.verify_deeplabcut_csv(file_path)
        except Exception as e:
            self.feedback_box.append(f"❌ Error reading CSV file:\n{e}")
            return False

        if not errors and not warnings:
            self.feedback_box.append("✅ No issues found.")
        else:
            if errors:
                self.feedback_box.append("\n❌ Errors:")
                for err in errors:
                    self.feedback_box.append(f" - {err}")
            if warnings:
                self.feedback_box.append("\n⚠️ Warnings:")
                for warn in warnings:
                    self.feedback_box.append(f" - {warn}")

        return not errors  # returns True only if no errors
