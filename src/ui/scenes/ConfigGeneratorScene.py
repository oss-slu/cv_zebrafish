from __future__ import annotations

import re

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.validation import generate_json
from app_platform.paths import sessions_dir


def _section_rule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class ConfigGeneratorScene(QWidget):
    """
    Generate Config content: left vertical tabs (spec ~20%), stacked pages, thin bottom bar.
    """

    config_generated = pyqtSignal()

    def __init__(self, csv_path=None, parent=None):
        super().__init__(parent)

        self.current_session = None
        self._session_connected = None

        self.csv_id = None
        self.csv_path = csv_path
        self.bodyparts = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        mid = QHBoxLayout()
        mid.setSpacing(12)

        self._tab_list = QListWidget()
        self._tab_list.setObjectName("GenerateConfigTabList")
        for label in ("Select CSV", "Body Parts", "Custom Calculations"):
            self._tab_list.addItem(QListWidgetItem(label))
        self._tab_list.setCurrentRow(0)
        self._tab_list.setFixedWidth(170)
        self._tab_list.setSpacing(4)

        self._stack = QStackedWidget()

        # ----- Tab: Select CSV -----
        page_csv = QWidget()
        lay_csv = QVBoxLayout(page_csv)
        lay_csv.setContentsMargins(0, 0, 0, 0)
        lay_csv.setSpacing(8)
        lay_csv.addWidget(QLabel("Session CSVs"))
        self.csv_list = QListWidget()
        self.csv_list.setMinimumHeight(160)
        self.csv_list.itemClicked.connect(self._on_csv_chosen)
        lay_csv.addWidget(self.csv_list, stretch=1)

        self.feedback_box = QTextEdit()
        self.feedback_box.setReadOnly(True)
        self.feedback_box.setMinimumHeight(140)
        lay_csv.addWidget(self.feedback_box, stretch=1)

        self._stack.addWidget(page_csv)

        # ----- Tab: Body Parts -----
        scroll_body = QScrollArea()
        scroll_body.setWidgetResizable(True)
        scroll_body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_body.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        body_content = QWidget()
        form = QVBoxLayout(body_content)
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 8, 0)

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
            form.addWidget(QLabel(label_text))
            form.addWidget(combo)

        form.addWidget(_section_rule())

        form.addWidget(QLabel("Spine Points"))
        self.spine_list = QListWidget()
        self.spine_list.setSelectionMode(QListWidget.MultiSelection)
        self.spine_list.setMinimumHeight(120)
        form.addWidget(self.spine_list)

        form.addWidget(_section_rule())

        form.addWidget(QLabel("Tail Points"))
        self.tail_list = QListWidget()
        self.tail_list.setSelectionMode(QListWidget.MultiSelection)
        self.tail_list.setMinimumHeight(120)
        form.addWidget(self.tail_list)

        form.addWidget(_section_rule())

        graphs_group = QGroupBox("Graphs to generate")
        graphs_layout = QGridLayout()
        self.chk_fin_tail = QCheckBox("Fin angles + tail distance")
        self.chk_fin_tail.setChecked(True)
        self.chk_spines = QCheckBox("Spines")
        self.chk_spines.setChecked(True)
        self.chk_dot_lf = QCheckBox("Dot: Tail vs left fin angle")
        self.chk_dot_lf.setChecked(True)
        self.chk_dot_rf = QCheckBox("Dot: Tail vs right fin angle")
        self.chk_dot_rf.setChecked(True)
        self.chk_dot_lf_mov = QCheckBox("Dot: Tail vs left fin (moving)")
        self.chk_dot_lf_mov.setChecked(False)
        self.chk_dot_rf_mov = QCheckBox("Dot: Tail vs right fin (moving)")
        self.chk_dot_rf_mov.setChecked(False)
        graphs_layout.addWidget(self.chk_fin_tail, 0, 0)
        graphs_layout.addWidget(self.chk_spines, 1, 0)
        graphs_layout.addWidget(self.chk_dot_lf, 0, 1)
        graphs_layout.addWidget(self.chk_dot_rf, 1, 1)
        graphs_layout.addWidget(self.chk_dot_lf_mov, 2, 1)
        graphs_layout.addWidget(self.chk_dot_rf_mov, 3, 1)
        graphs_group.setLayout(graphs_layout)
        form.addWidget(graphs_group)

        form.addStretch(1)
        scroll_body.setWidget(body_content)
        self._stack.addWidget(scroll_body)

        # ----- Tab: Custom Calculations -----
        page_custom = QWidget()
        lay_c = QVBoxLayout(page_custom)
        lay_c.setContentsMargins(0, 0, 0, 0)
        lay_c.setSpacing(8)

        self.angle_a = QComboBox()
        self.angle_b = QComboBox()
        self.angle_c = QComboBox()
        self.angle_ccw = QCheckBox("Counterclockwise")

        angle_group = QGroupBox("Three-point angle")
        angle_layout = QGridLayout()
        angle_layout.addWidget(QLabel("Point A"), 0, 0)
        angle_layout.addWidget(self.angle_a, 0, 1)
        angle_layout.addWidget(QLabel("Point B (vertex)"), 1, 0)
        angle_layout.addWidget(self.angle_b, 1, 1)
        angle_layout.addWidget(QLabel("Point C"), 2, 0)
        angle_layout.addWidget(self.angle_c, 2, 1)
        angle_layout.addWidget(self.angle_ccw, 3, 1)
        angle_group.setLayout(angle_layout)
        lay_c.addWidget(angle_group)

        self.angle_a.currentIndexChanged.connect(self._on_angle_changed)
        self.angle_b.currentIndexChanged.connect(self._on_angle_changed)
        self.angle_c.currentIndexChanged.connect(self._on_angle_changed)

        lay_c.addStretch(1)
        self._stack.addWidget(page_custom)

        self._tab_list.currentRowChanged.connect(self._stack.setCurrentIndex)

        mid.addWidget(self._tab_list, 0)
        mid.addWidget(self._stack, 1)
        root.addLayout(mid, stretch=1)

        # Bottom bar (spec: CSV path, name field, Create)
        bottom = QWidget()
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 4, 0, 0)
        bottom_layout.setSpacing(10)

        bottom_layout.addWidget(QLabel("CSV"))
        self._csv_display_label = QLabel("(none)")
        self._csv_display_label.setMinimumWidth(120)
        self._csv_display_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom_layout.addWidget(self._csv_display_label, stretch=1)

        bottom_layout.addWidget(QLabel("Name"))
        self.config_name_input = QLineEdit()
        self.config_name_input.setPlaceholderText("config")
        self.config_name_input.setMinimumWidth(160)
        bottom_layout.addWidget(self.config_name_input, stretch=0)

        self.gen_btn = QPushButton("Create")
        self.gen_btn.clicked.connect(self.generate_config)
        bottom_layout.addWidget(self.gen_btn, stretch=0)

        root.addWidget(bottom)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_csv_display()

    def _update_csv_display(self):
        path = (self.csv_id or self.csv_path or "").strip()
        if not path:
            self._csv_display_label.setText("(none)")
            self._csv_display_label.setToolTip("")
            return
        self._csv_display_label.setToolTip(path)
        w = self._csv_display_label.width()
        if w < 80:
            w = max(80, self.width() - 360)
        fm = self._csv_display_label.fontMetrics()
        self._csv_display_label.setText(fm.elidedText(path, Qt.ElideMiddle, w))

    def _user_message(self, text: str, tab: Optional[int] = None):
        self.feedback_box.setPlainText(text)
        if tab is not None:
            self._tab_list.setCurrentRow(tab)

    def _sync_config_name_placeholder(self):
        if not self.current_session:
            self.config_name_input.setPlaceholderText("config")
            return
        raw = (self.current_session.getName() or "").strip()
        if raw and re.fullmatch(r"[A-Za-z0-9_\-\. ]+", raw):
            self.config_name_input.setPlaceholderText(raw)
        else:
            self.config_name_input.setPlaceholderText("config")

    def _reset_body_state(self):
        self.csv_id = None
        self.csv_path = None
        self.bodyparts = []
        for combo in [
            self.fin_r_1,
            self.fin_r_2,
            self.fin_l_1,
            self.fin_l_2,
            self.head_1,
            self.head_2,
        ]:
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
        self.spine_list.clear()
        self.tail_list.clear()
        self._sync_angle_dropdowns(changed=None)
        self.angle_ccw.setChecked(False)
        self.feedback_box.clear()
        self.csv_list.clearSelection()
        self._update_csv_display()

    def load_csv(self):
        """Load DeepLabCut CSV and populate widgets."""
        if not self.csv_path:
            self.csv_path, _ = QFileDialog.getOpenFileName(
                self, "Select DeepLabCut CSV", "", "CSV Files (*.csv)"
            )
        if not self.csv_path:
            self._user_message("Warning: No file selected.", tab=0)
            return

        try:
            if self.current_session is not None and self.csv_id and self.current_session.is_folder_csv(self.csv_id):
                files = self.current_session.get_folder_files(self.csv_id)
                if not files:
                    self._user_message(
                        "Warning: This folder has no CSV files recorded in the session.",
                        tab=0,
                    )
                    return
                self.csv_path = files[0]
            else:
                if self.current_session is not None:
                    self.current_session.addCSV(self.csv_path)
                    self.current_session.save()

            self.bodyparts = generate_json.load_bodyparts_from_csv(self.csv_path)
        except Exception as exc:
            self._user_message(f"Error loading CSV:\n{exc}", tab=0)
            return

        self._user_message(
            f"Success: Loaded {len(self.bodyparts)} bodyparts:\n" + ", ".join(self.bodyparts),
            tab=0,
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

        self._sync_angle_dropdowns(changed=None)
        self.angle_ccw.setChecked(False)

        self.spine_list.clear()
        self.tail_list.clear()
        for bodypart in self.bodyparts:
            self.spine_list.addItem(QListWidgetItem(bodypart))
            self.tail_list.addItem(QListWidgetItem(bodypart))
        self._update_csv_display()

    def _set_angle_combo_items(self, combo: QComboBox, options, current_value: str):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("")
        for opt in options:
            combo.addItem(opt)
        idx = combo.findText(current_value or "")
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def _sync_angle_dropdowns(self, changed=None):
        bps = list(self.bodyparts or [])
        if not bps:
            for combo in (self.angle_a, self.angle_b, self.angle_c):
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("")
                combo.blockSignals(False)
            return

        current = {
            "a": self.angle_a.currentText(),
            "b": self.angle_b.currentText(),
            "c": self.angle_c.currentText(),
        }
        for key in list(current.keys()):
            if current[key] not in bps:
                current[key] = ""

        if changed in ("a", "b", "c"):
            vals = [v for v in current.values() if v]
            if len(vals) != len(set(vals)):
                current[changed] = ""

        a_val, b_val, c_val = current["a"], current["b"], current["c"]
        opts_a = [bp for bp in bps if (bp == a_val) or (bp not in {b_val, c_val})]
        opts_b = [bp for bp in bps if (bp == b_val) or (bp not in {a_val, c_val})]
        opts_c = [bp for bp in bps if (bp == c_val) or (bp not in {a_val, b_val})]

        self._set_angle_combo_items(self.angle_a, opts_a, a_val)
        self._set_angle_combo_items(self.angle_b, opts_b, b_val)
        self._set_angle_combo_items(self.angle_c, opts_c, c_val)

    def _on_angle_changed(self, _idx: int):
        sender = self.sender()
        changed = None
        if sender == self.angle_a:
            changed = "a"
        elif sender == self.angle_b:
            changed = "b"
        elif sender == self.angle_c:
            changed = "c"
        self._sync_angle_dropdowns(changed=changed)

    def _refresh_csv_list(self):
        self.csv_list.clear()

        if self.current_session is None:
            self.csv_list.addItem(QListWidgetItem("(No session loaded)"))
            self.csv_list.setEnabled(False)
            return

        self.csv_list.setEnabled(True)
        csvs = self.current_session.getAllCSVs()

        if not csvs:
            self.csv_list.addItem(QListWidgetItem("(No CSVs in session yet)"))
            self.csv_list.setEnabled(False)
            return

        for p in csvs:
            self.csv_list.addItem(QListWidgetItem(p))

    def _on_csv_chosen(self, item: QListWidgetItem):
        p = (item.text() or "").strip()
        if not p or p.startswith("("):
            return
        self.csv_id = p
        self.csv_path = p
        self.load_csv()

    def _resolved_config_name(self) -> str:
        t = self.config_name_input.text().strip()
        if t:
            return t
        p = (self.config_name_input.placeholderText() or "").strip()
        return p if p else "config"

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
        if not self.bodyparts:
            self._user_message("Warning: Load a CSV first (Select CSV tab).", tab=0)
            return

        if self.current_session is None:
            self._user_message("Warning: No session loaded. Start or load a session first.", tab=0)
            return

        spine_points = [item.text() for item in self.spine_list.selectedItems()]
        tail_points = [item.text() for item in self.tail_list.selectedItems()]

        if len(spine_points) < 2 or len(tail_points) < 2:
            self._user_message(
                "Warning: Please select at least two points for spine and tail (Body Parts tab).",
                tab=1,
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

        a = self.angle_a.currentText().strip()
        b = self.angle_b.currentText().strip()
        c = self.angle_c.currentText().strip()
        valid_three = bool(a and b and c and len({a, b, c}) == 3)
        config.setdefault("custom_calculations", {})["three_point_angle"] = {
            "enabled": valid_three,
            "points": [a, b, c] if valid_three else [],
            "direction": "ccw" if self.angle_ccw.isChecked() else "cw",
            "output_column": "ThreePointAngle",
        }

        so = config.setdefault("shown_outputs", {})
        so["show_angle_and_distance_plot"] = self.chk_fin_tail.isChecked()
        so["show_spines"] = self.chk_spines.isChecked()
        so["show_tail_left_fin_angle_dot_plot"] = self.chk_dot_lf.isChecked()
        so["show_tail_right_fin_angle_dot_plot"] = self.chk_dot_rf.isChecked()
        so["show_tail_left_fin_moving_dot_plot"] = self.chk_dot_lf_mov.isChecked()
        so["show_tail_right_fin_moving_dot_plot"] = self.chk_dot_rf_mov.isChecked()

        session_name = self.current_session.getName()
        session_folder = Path(sessions_dir()) / session_name
        session_folder.mkdir(parents=True, exist_ok=True)

        config_name = self._resolved_config_name()
        ok, msg = self._validate_config_name(config_name)
        if not ok:
            self._user_message(f"Warning: {msg}", tab=0)
            return

        save_path = self._next_available_path(session_folder, config_name)
        save_path = str(save_path)

        try:
            generate_json.save_config_json(config, save_path)
            try:
                csv_target = self.csv_id or self.csv_path
                self.current_session.addConfigToCSV(csv_target, save_path)
                self.current_session.save()
            except Exception:
                pass

        except Exception as exc:
            self._user_message(f"Error saving file:\n{exc}", tab=0)
            return

        self._user_message(f"Success: Configuration saved to:\n{save_path}", tab=0)
        self.config_generated.emit()

    def load_session(self, session):
        if self._session_connected is not None:
            try:
                self._session_connected.session_updated.disconnect(self._refresh_csv_list)
            except (TypeError, RuntimeError):
                pass
            self._session_connected = None

        self.current_session = session
        self._session_connected = session

        self._reset_body_state()
        self._sync_config_name_placeholder()
        self.config_name_input.clear()

        if session is not None:
            try:
                session.session_updated.connect(self._refresh_csv_list)
            except Exception:
                pass

        self._refresh_csv_list()
        self._tab_list.setCurrentRow(0)
