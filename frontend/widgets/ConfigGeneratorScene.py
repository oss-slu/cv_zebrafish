from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QPushButton,
    QTextEdit, QComboBox, QFileDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
import os
import importlib.util
from os import getcwd, path
from sys import modules


class ConfigGeneratorScene(QWidget):
    def __init__(self, csv_path=None, parent=None):
        super().__init__(parent)

        # --- Load backend dynamically ---
        module_name = "generate_json"
        parent_dir = path.abspath(path.join(getcwd(), path.pardir))
        file_path = path.join(
            parent_dir, "data_schema_validation", "src", module_name + ".py")
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        self.json_utils = importlib.util.module_from_spec(spec)
        modules[module_name] = self.json_utils
        spec.loader.exec_module(self.json_utils)

        self.csv_path = csv_path
        self.bodyparts = []

        layout = QVBoxLayout()
        header = QLabel("Auto-generate JSON Config")
        header.setAlignment(Qt.AlignHCenter)
        layout.addWidget(header)

        # Feedback
        self.feedback_box = QTextEdit(readOnly=True)
        self.feedback_box.setMinimumHeight(150)
        layout.addWidget(self.feedback_box)

        # Load CSV
        self.load_btn = QPushButton("Load CSV")
        self.load_btn.clicked.connect(self.load_csv)
        layout.addWidget(self.load_btn)

        # Dropdowns
        self.fin_r_1 = QComboBox()
        self.fin_r_2 = QComboBox()
        self.fin_l_1 = QComboBox()
        self.fin_l_2 = QComboBox()
        self.head_1 = QComboBox()
        self.head_2 = QComboBox()

        for cb, label_text in [
            (self.fin_r_1, "Right Fin #1"), (self.fin_r_2, "Right Fin #2"),
            (self.fin_l_1, "Left Fin #1"), (self.fin_l_2, "Left Fin #2"),
            (self.head_1, "Head pt1"), (self.head_2, "Head pt2")
        ]:
            layout.addWidget(QLabel(label_text))
            layout.addWidget(cb)

        # Spine and tail use QListWidget
        layout.addWidget(QLabel("Spine Points"))
        self.spine_list = QListWidget()
        self.spine_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.spine_list)

        layout.addWidget(QLabel("Tail Points"))
        self.tail_list = QListWidget()
        self.tail_list.setSelectionMode(QListWidget.MultiSelection)
        layout.addWidget(self.tail_list)

        # Generate button
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
            self.feedback_box.setText("⚠️ No file selected.")
            return

        try:
            self.bodyparts = self.json_utils.load_bodyparts_from_csv(
                self.csv_path)
            self.feedback_box.setText(
                f"✅ Loaded {len(self.bodyparts)} bodyparts:\n" +
                ", ".join(self.bodyparts)
            )

            # Fill dropdowns
            for cb in [self.fin_r_1, self.fin_r_2, self.fin_l_1, self.fin_l_2, self.head_1, self.head_2]:
                cb.clear()
                cb.addItems(self.bodyparts)

            # Fill spine/tail lists
            self.spine_list.clear()
            self.tail_list.clear()
            for bp in self.bodyparts:
                self.spine_list.addItem(QListWidgetItem(bp))
                self.tail_list.addItem(QListWidgetItem(bp))

        except Exception as e:
            self.feedback_box.setText(f"❌ Error loading CSV:\n{e}")

    def generate_config(self):
        """Collect selections and write JSON config."""
        if not self.bodyparts:
            self.feedback_box.setText("⚠️ Load a CSV first.")
            return

        spine_points = [item.text()
                        for item in self.spine_list.selectedItems()]
        tail_points = [item.text() for item in self.tail_list.selectedItems()]

        if len(spine_points) < 2 or len(tail_points) < 2:
            self.feedback_box.setText(
                "⚠️ Please select at least two points for spine and tail.")
            return

        points = {
            "right_fin": [self.fin_r_1.currentText(), self.fin_r_2.currentText()],
            "left_fin": [self.fin_l_1.currentText(), self.fin_l_2.currentText()],
            "head": {"pt1": self.head_1.currentText(), "pt2": self.head_2.currentText()},
            "spine": spine_points,
            "tail": tail_points
        }

        try:
            config = self.json_utils.build_config(
                points, self.json_utils.BASE_CONFIG)
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Config JSON", os.getcwd(), "JSON Files (*.json)"
            )
            if not save_path:
                return

            self.json_utils.save_config_json(config, save_path)
            self.feedback_box.setText(
                f"✅ Configuration saved to:\n{save_path}")

        except Exception as e:
            self.feedback_box.setText(f"❌ Error saving file:\n{e}")
