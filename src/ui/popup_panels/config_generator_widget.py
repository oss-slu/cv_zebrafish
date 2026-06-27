from __future__ import annotations

import json
import re
import sys

from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal, QRect
from PyQt5.QtGui import QCursor, QFontMetrics
from PyQt5.QtWidgets import (
    QButtonGroup,
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
    QDoubleSpinBox,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyle,
    QStyleOptionComboBox,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from core.validation import generate_json
from ui.components.pose.bodypart_pool_list import BodypartPaletteList, BodypartSequenceList, ChipDelegate
from app_platform.paths import sessions_dir
from ui.components.widgets.wide_popup_combo import WidePopupComboBox
from ui.elide_tooltip import update_label_elide_tooltip, update_pushbutton_elide_tooltip

def _section_rule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line


class ConfigGeneratorScene(QWidget):
    """
    Generate Config content: left floating tab buttons, stacked pages, thin bottom bar.
    """

    config_generated = pyqtSignal()
    # (title, short_body) for shell ErrorToast; full text always printed to stderr.
    toast_requested = pyqtSignal(str, str)

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
        mid.setSpacing(16)

        self._tab_strip = QWidget()
        self._tab_strip.setObjectName("GenerateConfigTabStrip")
        strip_layout = QVBoxLayout(self._tab_strip)
        strip_layout.setContentsMargins(0, 4, 0, 4)
        strip_layout.setSpacing(10)

        self._tab_buttons: list[QPushButton] = []
        self._tab_group = QButtonGroup(self)
        self._tab_group.setExclusive(True)
        for label in ("Select CSV", "Body Parts", "Custom Calculations", "Low-Res Analysis"):
            btn = QPushButton(label)
            btn.setObjectName("GenerateConfigTabButton")
            btn.setCheckable(True)
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            btn.setCursor(Qt.PointingHandCursor)
            self._tab_group.addButton(btn)
            strip_layout.addWidget(btn)
            self._tab_buttons.append(btn)
        self._tab_buttons[0].setChecked(True)
        self._tab_group.buttonClicked.connect(self._on_tab_button_clicked)
        strip_layout.addStretch(1)

        self._tab_strip.setFixedWidth(188)
        self._update_tab_button_tooltips()

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ----- Tab: Select CSV -----
        page_csv = QWidget()
        lay_csv = QVBoxLayout(page_csv)
        lay_csv.setContentsMargins(0, 0, 0, 0)
        lay_csv.setSpacing(8)
        lay_csv.addWidget(QLabel("Session CSVs"))
        self.csv_list = QListWidget()
        self.csv_list.setMinimumHeight(160)
        self.csv_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.csv_list.setTextElideMode(Qt.ElideLeft)
        self.csv_list.itemClicked.connect(self._on_csv_chosen)
        lay_csv.addWidget(self.csv_list, stretch=1)

        self._stack.addWidget(page_csv)

        # ----- Tab: Body Parts -----
        scroll_body = QScrollArea()
        scroll_body.setObjectName("GenerateConfigScrollBody")
        scroll_body.setWidgetResizable(True)
        scroll_body.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_body.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_body.setFrameShape(QFrame.NoFrame)

        body_content = QWidget()
        body_content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._body_form_content = body_content
        self._scroll_body = scroll_body
        form = QVBoxLayout(body_content)
        form.setSpacing(10)
        form.setContentsMargins(0, 0, 0, 0)

        self.fin_r_1 = WidePopupComboBox()
        self.fin_r_2 = WidePopupComboBox()
        self.fin_l_1 = WidePopupComboBox()
        self.fin_l_2 = WidePopupComboBox()
        self.head_1 = WidePopupComboBox()
        self.head_2 = WidePopupComboBox()
        self._body_part_combos = (
            self.fin_r_1,
            self.fin_r_2,
            self.fin_l_1,
            self.fin_l_2,
            self.head_1,
            self.head_2,
        )

        for combo, label_text in [
            (self.fin_r_1, "Right Fin #1"),
            (self.fin_r_2, "Right Fin #2"),
            (self.fin_l_1, "Left Fin #1"),
            (self.fin_l_2, "Left Fin #2"),
            (self.head_1, "Head pt1"),
            (self.head_2, "Head pt2"),
        ]:
            form.addWidget(QLabel(label_text))
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(combo, 0)
            row.addStretch(1)
            form.addLayout(row)

        form.addWidget(_section_rule())

        # 2×2: each row = [Available] [Spine|Tail] so it’s clear which palette feeds which list.
        self.bp_available_spine = BodypartPaletteList()
        self.bp_available_tail = BodypartPaletteList()
        self.spine_list = BodypartSequenceList()
        self.tail_list = BodypartSequenceList()
        self.spine_list.set_palette(self.bp_available_spine)
        self.tail_list.set_palette(self.bp_available_tail)
        self.bp_available_spine.set_add_callback(self._on_palette_add_spine)
        self.bp_available_tail.set_add_callback(self._on_palette_add_tail)
        self.spine_list.set_return_callback(lambda _n: self._refill_available_pools())
        self.tail_list.set_return_callback(lambda _n: self._refill_available_pools())
        self.bp_available_spine.set_after_sequence_drop(self._refill_available_pools)
        self.bp_available_tail.set_after_sequence_drop(self._refill_available_pools)
        self.bp_pool_delegate_av1 = ChipDelegate(self.bp_available_spine)
        self.bp_pool_delegate_av2 = ChipDelegate(self.bp_available_tail)
        self.bp_pool_delegate_s = ChipDelegate(self.spine_list)
        self.bp_pool_delegate_t = ChipDelegate(self.tail_list)
        self.bp_available_spine.set_chip_delegate(self.bp_pool_delegate_av1)
        self.bp_available_tail.set_chip_delegate(self.bp_pool_delegate_av2)
        self.spine_list.set_chip_delegate(self.bp_pool_delegate_s)
        self.tail_list.set_chip_delegate(self.bp_pool_delegate_t)

        pools = QGridLayout()
        pools.setHorizontalSpacing(12)
        pools.setVerticalSpacing(10)
        pools.addWidget(QLabel("Available (spine)"), 0, 0, Qt.AlignHCenter)
        pools.addWidget(self.bp_available_spine, 1, 0)
        pools.addWidget(QLabel("Spine (top → down)"), 0, 1, Qt.AlignHCenter)
        pools.addWidget(self.spine_list, 1, 1)
        pools.addWidget(QLabel("Available (tail)"), 2, 0, Qt.AlignHCenter)
        pools.addWidget(self.bp_available_tail, 3, 0)
        pools.addWidget(QLabel("Tail (top → down)"), 2, 1, Qt.AlignHCenter)
        pools.addWidget(self.tail_list, 3, 1)
        for c in (0, 1):
            pools.setColumnStretch(c, 1)
        form.addLayout(pools)
        self._apply_chip_pool_styles()
        self._apply_bodypart_field_widths()
        self._polish_bodypart_combos()

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

        self.angle_a = WidePopupComboBox()
        self.angle_b = WidePopupComboBox()
        self.angle_c = WidePopupComboBox()
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

        # ----- Tab: Low-Res Analysis -----
        scroll_low_res = QScrollArea()
        scroll_low_res.setWidgetResizable(True)
        scroll_low_res.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_low_res.setFrameShape(QFrame.NoFrame)
        low_res_content = QWidget()
        low_res_form = QVBoxLayout(low_res_content)
        low_res_form.setSpacing(10)
        low_res_form.setContentsMargins(0, 0, 0, 0)

        dist_group = QGroupBox("Distance & speed")
        dist_layout = QGridLayout()
        self.lr_track_dist_speed = WidePopupComboBox()
        dist_layout.addWidget(QLabel("Track point"), 0, 0)
        dist_layout.addWidget(self.lr_track_dist_speed, 0, 1)
        dist_group.setLayout(dist_layout)
        low_res_form.addWidget(dist_group)

        ar_group = QGroupBox("Active / rest bouts")
        ar_layout = QGridLayout()
        self.lr_track_active_rest = WidePopupComboBox()
        self.lr_min_total_move = QDoubleSpinBox()
        self.lr_min_total_move.setDecimals(6)
        self.lr_min_total_move.setRange(0.0, 1.0)
        self.lr_min_total_move.setSingleStep(0.0005)
        self.lr_min_total_move.setValue(0.002)
        self.lr_min_frame_disp = QDoubleSpinBox()
        self.lr_min_frame_disp.setDecimals(6)
        self.lr_min_frame_disp.setRange(0.0, 0.01)
        self.lr_min_frame_disp.setSingleStep(0.00001)
        self.lr_min_frame_disp.setValue(0.00008)
        self.lr_move_fraction = QDoubleSpinBox()
        self.lr_move_fraction.setDecimals(2)
        self.lr_move_fraction.setRange(0.0, 5.0)
        self.lr_move_fraction.setSingleStep(0.05)
        self.lr_move_fraction.setValue(0.5)
        self.lr_min_rest_frames = QSpinBox()
        self.lr_min_rest_frames.setRange(0, 500)
        self.lr_min_rest_frames.setValue(12)
        self.chk_lr_active_rest_plot = QCheckBox("Show active/rest plot in graph viewer")
        self.chk_lr_active_rest_plot.setChecked(True)

        ar_layout.addWidget(QLabel("Track point"), 0, 0)
        ar_layout.addWidget(self.lr_track_active_rest, 0, 1)
        ar_layout.addWidget(QLabel("Min total movement (m)"), 1, 0)
        ar_layout.addWidget(self.lr_min_total_move, 1, 1)
        ar_layout.addWidget(QLabel("Min frame displacement (m)"), 2, 0)
        ar_layout.addWidget(self.lr_min_frame_disp, 2, 1)
        ar_layout.addWidget(QLabel("Movement fraction of mean step"), 3, 0)
        ar_layout.addWidget(self.lr_move_fraction, 3, 1)
        ar_layout.addWidget(QLabel("Min rest frames to split bout"), 4, 0)
        ar_layout.addWidget(self.lr_min_rest_frames, 4, 1)
        ar_layout.addWidget(self.chk_lr_active_rest_plot, 5, 1)
        ar_group.setLayout(ar_layout)
        low_res_form.addWidget(ar_group)
        low_res_form.addStretch(1)
        scroll_low_res.setWidget(low_res_content)
        self._stack.addWidget(scroll_low_res)

        mid.addWidget(self._tab_strip, 0)
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
        self._csv_display_label.setWordWrap(False)
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

    def _on_tab_button_clicked(self, button: QPushButton) -> None:
        try:
            idx = self._tab_buttons.index(button)
        except ValueError:
            return
        self._stack.setCurrentIndex(idx)

    def _set_tab_index(self, index: int) -> None:
        if not self._tab_buttons:
            return
        index = max(0, min(index, len(self._tab_buttons) - 1))
        if index > 0 and not self._tab_buttons[index].isEnabled():
            index = 0
        self._tab_group.blockSignals(True)
        self._tab_buttons[index].setChecked(True)
        self._tab_group.blockSignals(False)
        self._stack.setCurrentIndex(index)

    def _update_tab_enabled_state(self) -> None:
        ready = bool(self.bodyparts)
        if len(self._tab_buttons) >= 4:
            self._tab_buttons[1].setEnabled(ready)
            self._tab_buttons[2].setEnabled(ready)
            self._tab_buttons[3].setEnabled(ready)
        if not ready and self._stack.currentIndex() > 0:
            self._set_tab_index(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_csv_display()
        self._apply_bodypart_field_widths()
        self._update_tab_button_tooltips()

    def _update_tab_button_tooltips(self) -> None:
        for btn in self._tab_buttons:
            update_pushbutton_elide_tooltip(btn)

    def _update_csv_display(self):
        path = (self.csv_id or self.csv_path or "").strip()
        if not path:
            self._csv_display_label.setText("(none)")
            self._csv_display_label.setToolTip("")
            return
        w = self._csv_display_label.width()
        if w < 80:
            w = max(80, self.width() - 360)
        fm = self._csv_display_label.fontMetrics()
        self._csv_display_label.setText(fm.elidedText(path, Qt.ElideLeft, w))
        update_label_elide_tooltip(
            self._csv_display_label, path, Qt.ElideLeft, elide_width=w
        )

    @staticmethod
    def _message_to_toast(full_text: str) -> tuple[str, str]:
        """Short title + body for the floating toast; full log stays on stderr."""
        text = (full_text or "").strip()
        if not text:
            return ("Notice", "")
        lines = text.split("\n")
        first = lines[0].strip()
        rest = "\n".join(lines[1:]).strip()
        low = first.lower()
        if low.startswith("warning:"):
            body = first.split(":", 1)[1].strip() if ":" in first else first
            return ("Warning", body)
        if low.startswith("error"):
            body = first if not rest else f"{first}\n{rest}"
            if len(body) > 300:
                body = body[:297] + "..."
            return ("Error", body)
        if low.startswith("success:"):
            tail = first[8:].strip() if len(first) > 8 else first
            if len(tail) > 180:
                tail = tail[:177] + "..."
            return ("Success", tail)
        if low.startswith("could not load"):
            b = first if len(first) < 220 else first[:217] + "..."
            return ("Config template", b)
        if low.startswith("loaded settings from:"):
            path = first.split(":", 1)[-1].strip() if ":" in first else first
            return ("Loaded", (path or first)[:200])
        one = first[:220] + ("…" if len(first) > 220 else "")
        return ("Generate Config", one)

    def _user_message(self, text: str, tab: Optional[int] = None):
        raw = (text or "").strip()
        print(raw, file=sys.stderr, flush=True)
        low = raw.lower()
        # Toast only for problems — successes stay on stderr / View Console only.
        if not (low.startswith("success:") or low.startswith("loaded settings from:")):
            title, short = self._message_to_toast(raw)
            self.toast_requested.emit(title, short)
        if tab is not None:
            t = tab
            if t > 0 and not self.bodyparts:
                t = 0
            self._set_tab_index(t)

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
        self.bp_available_spine.clear()
        self.bp_available_tail.clear()
        self.spine_list.clear()
        self.tail_list.clear()
        self._sync_angle_dropdowns(changed=None)
        self.angle_ccw.setChecked(False)
        for combo in (self.lr_track_dist_speed, self.lr_track_active_rest):
            combo.blockSignals(True)
            combo.clear()
            combo.blockSignals(False)
        self.csv_list.clearSelection()
        self._update_csv_display()
        self._update_tab_enabled_state()

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

        self._rebuild_bodypart_pools()
        self._update_csv_display()
        self._update_tab_enabled_state()

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
            it = QListWidgetItem(p)
            it.setToolTip(p)
            self.csv_list.addItem(it)

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

    def _body_content_width(self) -> int:
        w = 400
        if self._body_form_content is not None and self._body_form_content.width() > 80:
            w = self._body_form_content.width()
        elif self._stack.width() > 120:
            w = max(200, self._stack.width() - 220)
        return w

    def _apply_bodypart_field_widths(self) -> None:
        w = self._body_content_width()
        fm = self.fontMetrics()
        ch8 = max(1, fm.horizontalAdvance("0" * 8)) + 48
        # Previously ~0.33*w; 3x that ≈ use most of the row; floor at ~8 chars.
        min_wide = int(w * 0.33) * 3
        combo_max = min(w - 16, max(ch8, min(w - 8, min_wide)))
        for c in self._body_part_combos:
            c.setMaximumWidth(16777215)  # reset
            c.setMinimumWidth(ch8)
            c.setMaximumWidth(combo_max)
        col = max(160, (w - 32) // 2)
        # Don’t cap pool lists too hard — a tight max+min pair made columns effectively zero-wide in edge layouts.
        for pl in (self.bp_available_spine, self.bp_available_tail, self.spine_list, self.tail_list):
            pl.setMaximumWidth(16777215)
            pl.setMinimumWidth(min(220, col))

    def _apply_chip_pool_styles(self) -> None:
        """Rounded chip look + pool surface; :hover / :selected differ so clicks read as feedback."""
        for obj in (self.bp_available_spine, self.bp_available_tail, self.spine_list, self.tail_list):
            obj.setStyleSheet(
                """
                QListWidget {
                    background-color: rgba(40, 40, 48, 0.85);
                    border: 1px solid rgba(100, 100, 120, 0.9);
                    border-radius: 8px;
                    padding: 6px;
                    outline: none;
                }
                QListWidget::item {
                    background-color: rgba(50, 50, 60, 0.95);
                    border: 1px solid rgba(120, 120, 140, 0.85);
                    border-radius: 6px;
                    padding: 4px 8px;
                    margin: 2px;
                }
                QListWidget::item:hover {
                    background-color: rgba(70, 72, 90, 0.98);
                    border: 1px solid rgba(160, 165, 200, 0.95);
                }
                QListWidget::item:selected, QListWidget::item:selected:active {
                    background-color: rgba(60, 90, 150, 0.85);
                    border: 1px solid rgba(140, 180, 255, 0.9);
                }
                QListWidget::item:pressed {
                    background-color: rgba(90, 100, 140, 0.95);
                }
            """
            )

    def _polish_bodypart_combos(self) -> None:
        def _tip_from_elide(cc: QComboBox, t: str) -> None:
            t = t or ""
            if not t:
                cc.setToolTip("")
                return
            opt = QStyleOptionComboBox()
            opt.initFrom(cc)
            opt.editable = False
            opt.currentText = t
            ar = self.style().subControlRect(QStyle.CC_ComboBox, opt, QStyle.SC_ComboBoxEditField, cc)
            avail = max(1, ar.width() - 6)
            fm = QFontMetrics(cc.font())
            if fm.horizontalAdvance(t) > avail:
                cc.setToolTip(t)
            else:
                cc.setToolTip("")

        for combo in self._body_part_combos:

            def _on_text(t: str, cc: QComboBox = combo) -> None:
                _tip_from_elide(cc, t)

            combo.currentTextChanged.connect(_on_text)
            try:
                v = combo.view()
                v.setMouseTracking(True)

                def _on_hov(idx, cc: QComboBox = combo) -> None:
                    self._on_combo_list_hover(cc, idx)

                v.entered.connect(_on_hov)
            except Exception:
                pass
            _tip_from_elide(combo, combo.currentText())
            combo.setMinimumContentsLength(8)

    def _on_combo_list_hover(self, combo: QComboBox, index) -> None:
        t = (combo.model().data(index, Qt.DisplayRole) or "")
        t = str(t) if t is not None else ""
        if t:
            QToolTip.showText(QCursor.pos(), t, combo, QRect(), 5000)
        else:
            QToolTip.hideText()

    def _refill_available_pools(self) -> None:
        """Each Available list only shows bodyparts not already placed in the paired Spine or Tail list."""
        self.bp_available_spine.clear()
        self.bp_available_tail.clear()
        if not self.bodyparts:
            return
        in_spine = {
            (self.spine_list.item(i).text() or "").strip()
            for i in range(self.spine_list.count())
            if self.spine_list.item(i)
        }
        in_tail = {
            (self.tail_list.item(i).text() or "").strip()
            for i in range(self.tail_list.count())
            if self.tail_list.item(i)
        }
        for bp in sorted(self.bodyparts, key=str.lower):
            if bp not in in_spine:
                self.bp_available_spine.addItem(QListWidgetItem(bp))
            if bp not in in_tail:
                self.bp_available_tail.addItem(QListWidgetItem(bp))

    def _on_palette_add_spine(self, t: str) -> None:
        n = (t or "").strip()
        if n and self.spine_list.add_name(n):
            self._refill_available_pools()

    def _on_palette_add_tail(self, t: str) -> None:
        n = (t or "").strip()
        if n and self.tail_list.add_name(n):
            self._refill_available_pools()

    def _rebuild_bodypart_pools(
        self,
        spine_order: list | None = None,
        tail_order: list | None = None,
    ) -> None:
        """Rebuild spine/tail from saved order, then each Available = bodyparts not in that list."""
        self.bp_available_spine.clear()
        self.bp_available_tail.clear()
        self.spine_list.clear()
        self.tail_list.clear()
        if not self.bodyparts:
            return
        bset = set(self.bodyparts)
        s_list: list[str] = []
        for x in spine_order or []:
            t = str(x)
            if t in bset and t not in s_list:
                s_list.append(t)
        t_list: list[str] = []
        for x in tail_order or []:
            t = str(x)
            if t in bset and t not in t_list:
                t_list.append(t)
        for n in s_list:
            self.spine_list.add_name(n)
        for n in t_list:
            self.tail_list.add_name(n)
        self._refill_available_pools()
        self._sync_low_res_point_combos()

    def _assigned_point_labels(self) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()

        def _add(name: str) -> None:
            t = (name or "").strip()
            if t and t not in seen:
                seen.add(t)
                labels.append(t)

        for i in range(self.spine_list.count()):
            _add(self.spine_list.item(i).text())
        for i in range(self.tail_list.count()):
            _add(self.tail_list.item(i).text())
        for combo in (self.fin_r_1, self.fin_r_2, self.fin_l_1, self.fin_l_2, self.head_1, self.head_2):
            _add(combo.currentText())
        return labels

    def _sync_low_res_point_combos(self) -> None:
        labels = self._assigned_point_labels()
        current_dist = self.lr_track_dist_speed.currentText()
        current_ar = self.lr_track_active_rest.currentText()
        for combo, current in (
            (self.lr_track_dist_speed, current_dist),
            (self.lr_track_active_rest, current_ar),
        ):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            for lbl in labels:
                combo.addItem(lbl)
            idx = combo.findText(current or "")
            if idx >= 0:
                combo.setCurrentIndex(idx)
            elif labels:
                combo.setCurrentIndex(1 if combo.count() > 1 else 0)
            combo.blockSignals(False)

    def _config_namespace_dir(self) -> Path:
        """
        Backlog #4: each CSV gets its own folder so `config.json` names do not collide in a shared flat dir.
        """
        if self.current_session is None:
            return Path(sessions_dir()) / "unnamed"
        session_folder = Path(sessions_dir()) / self.current_session.getName()
        session_folder.mkdir(parents=True, exist_ok=True)
        key = self.csv_id or self.csv_path
        if not key:
            return session_folder
        stem = Path(str(key)).stem
        safe = re.sub(r"[^\w\-.]+", "_", stem).strip("_")[:80] or "csv"
        d = session_folder / "by_csv" / safe
        d.mkdir(parents=True, exist_ok=True)
        return d

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

        spine_points = [self.spine_list.item(i).text() for i in range(self.spine_list.count())]
        tail_points = [self.tail_list.item(i).text() for i in range(self.tail_list.count())]

        if len(spine_points) < 2 or len(tail_points) < 2:
            self._user_message(
                "Warning: Please select at least two points for spine and tail (Body Parts tab).",
                tab=1,
            )
            return

        if len(spine_points) != len(set(spine_points)):
            self._user_message(
                "Error: duplicate point name in Spine. Each body part can appear only once.",
                tab=1,
            )
            return
        if len(tail_points) != len(set(tail_points)):
            self._user_message(
                "Error: duplicate point name in Tail. Each body part can appear only once.",
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

        a = self.angle_a.currentText().strip()
        b = self.angle_b.currentText().strip()
        c = self.angle_c.currentText().strip()
        valid_three = bool(a and b and c and len({a, b, c}) == 3)
        dist_pt = self.lr_track_dist_speed.currentText().strip() or (spine_points[0] if spine_points else "")
        ar_pt = self.lr_track_active_rest.currentText().strip() or dist_pt

        config = generate_json.build_config_from_generator(
            points,
            three_point_angle={
                "enabled": valid_three,
                "points": [a, b, c] if valid_three else [],
                "direction": "ccw" if self.angle_ccw.isChecked() else "cw",
                "output_column": "ThreePointAngle",
            },
            low_res_analysis={
                "enabled": True,
                "track_point_distance_speed": dist_pt,
                "active_rest": {
                    "track_point": ar_pt,
                    "min_total_movement_m": float(self.lr_min_total_move.value()),
                    "min_frame_displacement_m": float(self.lr_min_frame_disp.value()),
                    "movement_fraction_of_mean": float(self.lr_move_fraction.value()),
                    "min_rest_frames_to_split_bout": int(self.lr_min_rest_frames.value()),
                    "show_active_rest_plot": self.chk_lr_active_rest_plot.isChecked(),
                },
            },
            shown_outputs_flags={
                "show_angle_and_distance_plot": self.chk_fin_tail.isChecked(),
                "show_spines": self.chk_spines.isChecked(),
                "show_tail_left_fin_angle_dot_plot": self.chk_dot_lf.isChecked(),
                "show_tail_right_fin_angle_dot_plot": self.chk_dot_rf.isChecked(),
                "show_tail_left_fin_moving_dot_plot": self.chk_dot_lf_mov.isChecked(),
                "show_tail_right_fin_moving_dot_plot": self.chk_dot_rf_mov.isChecked(),
            },
        )

        config_name = self._resolved_config_name()
        ok, msg = self._validate_config_name(config_name)
        if not ok:
            self._user_message(f"Warning: {msg}", tab=0)
            return

        save_path = self._next_available_path(self._config_namespace_dir(), config_name)
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
        self.config_name_input.setPlaceholderText("config")
        self.config_name_input.clear()

        if session is not None:
            try:
                session.session_updated.connect(self._refresh_csv_list)
            except Exception:
                pass

        self._refresh_csv_list()
        self._set_tab_index(0)

    def prefill_from_copy(self, csv_path: str, json_path: str | None) -> None:
        """After ``load_session``, select a session CSV and optionally apply an existing JSON as a template."""
        self.csv_id = csv_path
        self.csv_path = csv_path
        self.load_csv()
        if not self.bodyparts:
            return
        if json_path:
            ok, msg = self.apply_existing_config_json(json_path)
            if not ok:
                self._user_message(f"Could not load config template:\n{msg}", tab=0)

    def apply_existing_config_json(self, json_path: str) -> tuple[bool, str]:
        """Populate Body Parts / Custom Calculations / toggles from a saved config file."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            return False, str(e)

        pts = cfg.get("points") or {}

        def _set_combo(combo: QComboBox, val: str) -> None:
            combo.blockSignals(True)
            idx = combo.findText((val or "").strip())
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)

        rf = pts.get("right_fin") or []
        if len(rf) >= 2:
            _set_combo(self.fin_r_1, str(rf[0]))
            _set_combo(self.fin_r_2, str(rf[1]))
        lf = pts.get("left_fin") or []
        if len(lf) >= 2:
            _set_combo(self.fin_l_1, str(lf[0]))
            _set_combo(self.fin_l_2, str(lf[1]))
        head = pts.get("head") or {}
        if isinstance(head, dict):
            _set_combo(self.head_1, str(head.get("pt1", "")))
            _set_combo(self.head_2, str(head.get("pt2", "")))

        self._rebuild_bodypart_pools(pts.get("spine") or [], pts.get("tail") or [])

        so = cfg.get("shown_outputs") or {}
        self.chk_fin_tail.setChecked(bool(so.get("show_angle_and_distance_plot", True)))
        self.chk_spines.setChecked(bool(so.get("show_spines", True)))
        self.chk_dot_lf.setChecked(bool(so.get("show_tail_left_fin_angle_dot_plot", True)))
        self.chk_dot_rf.setChecked(bool(so.get("show_tail_right_fin_angle_dot_plot", True)))
        self.chk_dot_lf_mov.setChecked(bool(so.get("show_tail_left_fin_moving_dot_plot", False)))
        self.chk_dot_rf_mov.setChecked(bool(so.get("show_tail_right_fin_moving_dot_plot", False)))

        tpa = (cfg.get("custom_calculations") or {}).get("three_point_angle") or {}
        pts3 = tpa.get("points") or []
        if len(pts3) >= 3:
            _set_combo(self.angle_a, str(pts3[0]))
            _set_combo(self.angle_b, str(pts3[1]))
            _set_combo(self.angle_c, str(pts3[2]))
        else:
            _set_combo(self.angle_a, "")
            _set_combo(self.angle_b, "")
            _set_combo(self.angle_c, "")
        self.angle_ccw.setChecked(str(tpa.get("direction") or "").lower() == "ccw")
        self._sync_angle_dropdowns(changed=None)

        lr = cfg.get("low_res_analysis") or {}
        ar = lr.get("active_rest") or {}
        self._sync_low_res_point_combos()
        _set_combo(self.lr_track_dist_speed, str(lr.get("track_point_distance_speed") or ""))
        _set_combo(self.lr_track_active_rest, str(ar.get("track_point") or ""))
        self.lr_min_total_move.setValue(float(ar.get("min_total_movement_m", 0.002)))
        self.lr_min_frame_disp.setValue(float(ar.get("min_frame_displacement_m", 0.00008)))
        self.lr_move_fraction.setValue(float(ar.get("movement_fraction_of_mean", 0.5)))
        self.lr_min_rest_frames.setValue(int(ar.get("min_rest_frames_to_split_bout", 12)))
        self.chk_lr_active_rest_plot.setChecked(bool(ar.get("show_active_rest_plot", True)))

        self._user_message(f"Loaded settings from:\n{json_path}", tab=1)
        return True, ""
