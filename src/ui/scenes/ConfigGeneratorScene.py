from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.validation import generate_json


class ConfigGeneratorScene(QWidget):
    def __init__(self, csv_path=None, parent=None):
        super().__init__(parent)

        self.current_session = None

        self.csv_path = csv_path
        self.bodyparts = []

        layout = QVBoxLayout()
        header = QLabel("Auto-generate JSON Config")
        header.setAlignment(Qt.AlignHCenter)
        layout.addWidget(header)

        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(150)
        layout.addWidget(self.feedback_box)

        self.load_btn = QPushButton("Load CSV")
        self.load_btn.clicked.connect(self.load_csv)
        layout.addWidget(self.load_btn)

        self.fin_r_1 = QComboBox()
        self.fin_r_2 = QComboBox()
        self.fin_l_1 = QComboBox()
        self.fin_l_2 = QComboBox()
        self.head_1 = QComboBox()
        self.head_2 = QComboBox()

        for combo, label_text in [
            (self.fin_r_1, "Right Fin #1"),
            (self.fin_r_2, "Right Fin #2"),
            (self.fin_l_1, "Left Fin #1"),
            (self.fin_l_2, "Left Fin #2"),
            (self.head_1, "Head pt1"),
            (self.head_2, "Head pt2"),
        ]:
            layout.addWidget(QLabel(label_text))
            layout.addWidget(combo)

        layout.addWidget(QLabel("Spine Points"))
        self.spine_list = QListWidget()
        self.spine_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.spine_list)

        layout.addWidget(QLabel("Tail Points"))
        self.tail_list = QListWidget()
        self.tail_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.tail_list)

        self.gen_btn = QPushButton("Generate Config")
        self.gen_btn.clicked.connect(self.generate_config)
        layout.addWidget(self.gen_btn)

        self.setLayout(layout)

    def load_csv(self):
        """Load DeepLabCut CSV and populate widgets."""
        if not self.csv_path:
            self.csv_path, _ = QFileDialog.getOpenFileName(
                self, "Select DeepLabCut CSV", "", "CSV Files (*.csv)"
            )
        if not self.csv_path:
            self.feedback_box.setText("Warning: No file selected.")
            return

        try:
            # adds csv to session
            if self.current_session is not None:
                self.current_session.addCSV(self.csv_path)
                self.current_session.save()

            self.bodyparts = generate_json.load_bodyparts_from_csv(self.csv_path)
        except Exception as exc:
            self.feedback_box.setText(f"Error loading CSV:\n{exc}")
            return

        self.feedback_box.setText(
            f"Success: Loaded {len(self.bodyparts)} bodyparts:\n"
            + ", ".join(self.bodyparts)
        )

        for combo in [
            self.fin_r_1,
            self.fin_r_2,
            self.fin_l_1,
            self.fin_l_2,
            self.head_1,
            self.head_2,
        ]:
            combo.clear()
            combo.addItems(self.bodyparts)

        self.spine_list.clear()
        self.tail_list.clear()
        for bodypart in self.bodyparts:
            self.spine_list.addItem(QListWidgetItem(bodypart))
            self.tail_list.addItem(QListWidgetItem(bodypart))

    def generate_config(self):
        """Collect selections and write JSON config."""
        if not self.bodyparts:
            self.feedback_box.setText("Warning: Load a CSV first.")
            return

        spine_points = [item.text() for item in self.spine_list.selectedItems()]
        tail_points = [item.text() for item in self.tail_list.selectedItems()]

        if len(spine_points) < 2 or len(tail_points) < 2:
            self.feedback_box.setText(
                "Warning: Please select at least two points for spine and tail."
            )
            return

        points = {
            "right_fin": [self.fin_r_1.currentText(), self.fin_r_2.currentText()],
            "left_fin": [self.fin_l_1.currentText(), self.fin_l_2.currentText()],
            "head": {"pt1": self.head_1.currentText(), "pt2": self.head_2.currentText()},
            "spine": spine_points,
            "tail": tail_points,
        }

        config = generate_json.build_config(points, generate_json.BASE_CONFIG)
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Config JSON", str(Path.cwd()), "JSON Files (*.json)"
        )
        if not save_path:
            return

        try:
            generate_json.save_config_json(config, save_path)
            try:
                self.current_session.addConfigToCSV(self.csv_path, save_path)
                self.current_session.save()
            except Exception as exc:
                pass
                
        except Exception as exc:
            self.feedback_box.setText(f"Error saving file:\n{exc}")
            return

        self.feedback_box.setText(f"Success: Configuration saved to:\n{save_path}")

    def load_session(self, session):
        """Load previous session data."""
        self.current_session = session
