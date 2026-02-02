import re

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
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
    QLineEdit,
)

from core.validation import generate_json
from app_platform.paths import sessions_dir



class ConfigGeneratorScene(QWidget):

    config_generated = pyqtSignal()

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

        layout.addWidget(QLabel("Config Name"))
        self.config_name_input = QLineEdit()
        self.config_name_input.setPlaceholderText("config")
        layout.addWidget(self.config_name_input)

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

    def _validate_config_name(self, name: str) -> tuple[bool, str]:
        name = (name or "").strip()

        if not name:
            return False, "Config name can’t be empty."

        if not re.fullmatch(r"[A-Za-z0-9_\-\. ]+", name):
            return False, "Config name may only contain letters, numbers, spaces, underscore (_), dash (-), and dot (.)"

        if any(ch in name for ch in '<>:"/\\|?*'):
            return False, 'Config name contains invalid characters: <>:"/\\|?*'

        return True, ""

    def _next_available_path(self, folder: Path, base: str) -> Path:
        # ensure .json extension
        if not base.lower().endswith(".json"):
            base = base + ".json"

        candidate = folder / base
        if not candidate.exists():
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        i = 2
        while True:
            cand = folder / f"{stem}_{i}{suffix}"
            if not cand.exists():
                return cand
            i += 1

    def generate_config(self):
        """Collect selections and write JSON config."""
        if not self.bodyparts:
            self.feedback_box.setText("Warning: Load a CSV first.")
            return

        if self.current_session is None:
            self.feedback_box.setText("Warning: No session loaded. Start or load a session first.")
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

        session_name = self.current_session.getName()
        session_folder = Path(sessions_dir()) / session_name
        session_folder.mkdir(parents=True, exist_ok=True)

        config_name = self.config_name_input.text().strip()
        ok, msg = self._validate_config_name(config_name)
        if not ok:
            self.feedback_box.setText(f"Warning: {msg}")
            return

        save_path = self._next_available_path(session_folder, self.config_name_input.text())
        save_path = str(save_path)

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
        self.config_generated.emit()

    def load_session(self, session):
        """Load previous session data."""
        self.current_session = session