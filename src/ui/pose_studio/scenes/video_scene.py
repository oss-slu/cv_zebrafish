"""Video scene — import, select video, arena, selection (blob), update-all / detect mismatch."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    QFrame,
)

from ui.components.pose.arena_region_list import ArenaRegionList
from ui.pose_studio.chrome.scene_shell import PoseSceneShell
from ui.pose_studio.chrome.task_progress_bar import TaskProgressBar


class VideoScene(QWidget):
    """Crop / arena / blob setup scene (UI shell; orchestrator wires logic)."""

    upload_video_requested = pyqtSignal()
    upload_prelabeled_requested = pyqtSignal()
    upload_analysis_requested = pyqtSignal()
    delete_video_requested = pyqtSignal(str)
    delete_video_and_heatmaps_requested = pyqtSignal(str)
    video_selected = pyqtSignal(str)
    update_all_frames_requested = pyqtSignal()
    detect_mismatch_requested = pyqtSignal()
    suggest_values_requested = pyqtSignal()
    skip_requested = pyqtSignal()
    exclude_mode_toggled = pyqtSignal(bool)
    arena_region_selected = pyqtSignal(str)
    exclusion_added = pyqtSignal()
    exclusion_removed = pyqtSignal(str)
    arena_changed = pyqtSignal()
    selection_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoScene")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.shell = PoseSceneShell(show_context_bar=True, side_width=380)
        self.shell.set_advanced_visible(False)
        root.addWidget(self.shell)
        self._videos: list[dict[str, Any]] = []
        self._build_side()
        self._build_main()
        QTimer.singleShot(0, self.shell.fit_side_to_content)

    # --- Side -----------------------------------------------------------------

    def _build_side(self) -> None:
        imports = QGroupBox("Import")
        imports.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        il = QVBoxLayout(imports)
        self.upload_btn = QPushButton("Upload Videos")
        self.upload_btn.setToolTip("Add video files to this project")
        self.upload_btn.clicked.connect(self.upload_video_requested.emit)
        il.addWidget(self.upload_btn)
        self.upload_prelabeled_btn = QPushButton("Upload Pre-Labeled Data")
        self.upload_prelabeled_btn.setToolTip(
            "Import raw DLC or enriched CSV label data"
        )
        self.upload_prelabeled_btn.clicked.connect(self.upload_prelabeled_requested.emit)
        il.addWidget(self.upload_prelabeled_btn)
        self.upload_analysis_btn = QPushButton("Upload Analysis")
        self.upload_analysis_btn.setToolTip(
            "Import raw DLC or enriched CSV for analysis"
        )
        self.upload_analysis_btn.clicked.connect(self.upload_analysis_requested.emit)
        il.addWidget(self.upload_analysis_btn)
        self.shell.add_side_widget(imports)

        video_box = QGroupBox("Video")
        vl = QVBoxLayout(video_box)
        self.video_combo = QComboBox()
        self.video_combo.setToolTip("Select a project video")
        self.video_combo.currentIndexChanged.connect(self._on_video_combo)
        vl.addWidget(self.video_combo)
        self.remove_btn = QPushButton("Remove…")
        self.remove_btn.setToolTip("Remove video source; optionally delete heatmaps")
        self.remove_btn.clicked.connect(self.prompt_delete_current)
        vl.addWidget(self.remove_btn)
        self._loading_row = QWidget()
        lr = QHBoxLayout(self._loading_row)
        lr.setContentsMargins(0, 0, 0, 0)
        self._loading_lbl = QLabel("Video loading — 0 frames")
        self._loading_bar = QProgressBar()
        self._loading_bar.setRange(0, 0)
        lr.addWidget(self._loading_lbl, stretch=1)
        lr.addWidget(self._loading_bar)
        self._loading_row.hide()
        vl.addWidget(self._loading_row)
        self.shell.add_side_widget(video_box)

        arena_box = QGroupBox("Arena")
        af = QFormLayout(arena_box)
        self.arena_shape = QComboBox()
        self.arena_shape.addItem("Rectangular", "square")
        self.arena_shape.addItem("Circular", "circle")
        self.arena_shape.setToolTip("Arena shape")
        self.arena_shape.currentIndexChanged.connect(self._on_arena_shape)
        af.addRow("Shape", self.arena_shape)
        self.x_pos = self._slider(0, 10_000, 5_000)
        self.y_pos = self._slider(0, 10_000, 5_000)
        self.x_size = self._slider(5, 100, 40)
        self.y_size = self._slider(5, 100, 40)
        self.diameter = self._slider(1_000, 10_000, 4_000)
        af.addRow("X Pos", self.x_pos)
        af.addRow("Y Pos", self.y_pos)
        self._x_size_lbl = QLabel("X Size")
        self._y_size_lbl = QLabel("Y Size")
        af.addRow(self._x_size_lbl, self.x_size)
        af.addRow(self._y_size_lbl, self.y_size)
        self._diameter_lbl = QLabel("Diameter")
        af.addRow(self._diameter_lbl, self.diameter)
        for s in (self.x_pos, self.y_pos, self.x_size, self.y_size, self.diameter):
            s.valueChanged.connect(lambda _=None: self.arena_changed.emit())
        self.exclude_mode_cb = QCheckBox("Exclude Mode")
        self.exclude_mode_cb.setToolTip(
            "Add exclusion regions inside the main arena that blob detection ignores"
        )
        self.exclude_mode_cb.toggled.connect(self._on_exclude_mode_toggled)
        af.addRow(self.exclude_mode_cb)
        self.region_list = ArenaRegionList()
        self.region_list.setMinimumHeight(120)
        self.region_list.region_selected.connect(self.arena_region_selected.emit)
        self.region_list.exclusion_added.connect(self.exclusion_added.emit)
        self.region_list.exclusion_removed.connect(self.exclusion_removed.emit)
        af.addRow(self.region_list)
        self.shell.add_side_widget(arena_box)
        self._sync_arena_shape_visibility()

        sel_box = QGroupBox("Selection")
        sf = QFormLayout(sel_box)
        self.bright_min = self._slider(0, 254, 40)
        self.bright_max = self._slider(1, 255, 255)
        self.blob_padding = self._slider(0, 40, 4)
        self.crop_padding = self._slider(0, 80, 8)
        self.bright_min.setToolTip("Minimum brightness for fish mask")
        self.bright_max.setToolTip("Maximum brightness for fish mask")
        self.blob_padding.setToolTip("Expand detected fish mask outward")
        self.crop_padding.setToolTip("Extra margin on square crop")
        sf.addRow("Min brightness", self.bright_min)
        sf.addRow("Max brightness", self.bright_max)
        sf.addRow("Blob select padding", self.blob_padding)
        sf.addRow("Square crop padding", self.crop_padding)
        self.suggest_btn = QPushButton("Suggest values")
        self.suggest_btn.setToolTip("Suggest brightness from arena histogram")
        self.suggest_btn.clicked.connect(self.suggest_values_requested.emit)
        sf.addRow(self.suggest_btn)
        for s in (self.bright_min, self.bright_max, self.blob_padding, self.crop_padding):
            s.valueChanged.connect(lambda _=None: self.selection_changed.emit())
        self.shell.add_side_widget(sel_box)

        actions = QWidget()
        al = QVBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        self.update_all_btn = QPushButton("Update for all frames")
        self.update_all_btn.setObjectName("VideoUpdateAllButton")
        self.update_all_btn.setToolTip(
            "Apply arena/selection and rebuild blob cache for all frames"
        )
        self.update_all_btn.clicked.connect(self.update_all_frames_requested.emit)
        self.update_all_btn.setProperty("needsAttention", False)
        al.addWidget(self.update_all_btn)
        self.detect_btn = QPushButton("Detect next mismatching frame")
        self.detect_btn.setToolTip("Jump to next frame with unusual blob size or jump")
        self.detect_btn.clicked.connect(self.detect_mismatch_requested.emit)
        al.addWidget(self.detect_btn)
        self.skip_btn = QPushButton("Skip")
        self.skip_btn.setToolTip(
            "Continue without finishing crop setup. A proper crop speeds labeling and training."
        )
        self.skip_btn.clicked.connect(self.skip_requested.emit)
        al.addWidget(self.skip_btn)
        self.shell.add_side_widget(actions)

    def _slider(self, lo: int, hi: int, val: int) -> QSlider:
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        return s

    def _on_arena_shape(self) -> None:
        self._sync_arena_shape_visibility()
        self.arena_changed.emit()

    def _on_exclude_mode_toggled(self, checked: bool) -> None:
        self.region_list.set_list_enabled(checked)
        self.exclude_mode_toggled.emit(bool(checked))

    def set_exclude_mode(self, enabled: bool) -> None:
        self.exclude_mode_cb.blockSignals(True)
        self.exclude_mode_cb.setChecked(bool(enabled))
        self.exclude_mode_cb.blockSignals(False)
        self.region_list.set_list_enabled(bool(enabled))

    def set_arena_regions(
        self,
        exclusions: list,
        *,
        active_id: str,
    ) -> None:
        self.region_list.set_regions(exclusions, active_id=active_id)

    def _sync_arena_shape_visibility(self) -> None:
        """X/Y Pos stay visible for both shapes (origin vs circle center)."""
        circle = self.arena_shape.currentData() == "circle"
        self.diameter.setVisible(circle)
        self._diameter_lbl.setVisible(circle)
        self.x_size.setVisible(not circle)
        self.y_size.setVisible(not circle)
        self._x_size_lbl.setVisible(not circle)
        self._y_size_lbl.setVisible(not circle)
        self.x_pos.setVisible(True)
        self.y_pos.setVisible(True)

    # --- Main -----------------------------------------------------------------

    def _build_main(self) -> None:
        self.video_name_lbl = QLabel("—")
        self.video_name_lbl.setObjectName("PoseSceneTitle")
        self.shell.add_main_widget(self.video_name_lbl, stretch=0)
        self.status_body = QLabel("Upload videos or existing CSV data to begin.")
        self.status_body.setWordWrap(True)
        self.status_body.setObjectName("PoseSceneBody")
        self.shell.add_main_widget(self.status_body, stretch=0)
        self.preview_host = QFrame()
        self.preview_host.setObjectName("VideoPreviewHost")
        self.preview_layout = QVBoxLayout(self.preview_host)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.shell.add_main_widget(self.preview_host, stretch=1)
        self.timeline_host = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_host)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.shell.add_main_widget(self.timeline_host, stretch=0)
        self.progress = TaskProgressBar()
        self.progress.hide()
        self.shell.add_main_widget(self.progress, stretch=0)

    # --- API ------------------------------------------------------------------

    def set_status(self, title: str, body: str) -> None:
        if title:
            self.video_name_lbl.setText(title)
        self.status_body.setText(body)

    def show_import_progress(self, message: str) -> None:
        self.progress.show()
        self.progress.set_busy_message(message)

    def hide_import_progress(self) -> None:
        self.progress.reset()
        self.progress.hide()

    def set_videos(self, videos: list[dict[str, Any]]) -> None:
        """Each item: {id, name, missing?}."""
        self._videos = list(videos)
        self.video_combo.blockSignals(True)
        self.video_combo.clear()
        for v in self._videos:
            name = str(v.get("name") or v.get("id") or "")
            if v.get("missing"):
                name = f"{name} [missing]"
            self.video_combo.addItem(name, v.get("id"))
        self.video_combo.blockSignals(False)
        if self.video_combo.count():
            self._on_video_combo(self.video_combo.currentIndex())

    def current_video_id(self) -> str | None:
        data = self.video_combo.currentData()
        return str(data) if data is not None else None

    def set_video_name(self, name: str) -> None:
        self.video_name_lbl.setText(name or "—")

    def _on_video_combo(self, index: int) -> None:
        if index < 0:
            return
        vid = self.video_combo.itemData(index)
        if vid is not None:
            self.video_selected.emit(str(vid))
            self.set_video_name(self.video_combo.itemText(index))

    def show_video_loading(self, n_frames: int) -> None:
        self._loading_lbl.setText(f"Video loading — {int(n_frames)} frames")
        self._loading_row.show()

    def hide_video_loading(self) -> None:
        self._loading_row.hide()

    def set_update_all_highlighted(self, on: bool) -> None:
        self.update_all_btn.setProperty("needsAttention", bool(on))
        self.update_all_btn.style().unpolish(self.update_all_btn)
        self.update_all_btn.style().polish(self.update_all_btn)

    def prompt_delete_current(self) -> None:
        vid = self.current_video_id()
        if not vid:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Remove video")
        box.setText(
            "Remove this video from the project?\n\n"
            "Labeled data and models are kept. "
            "Choose sub-files to also delete heatmaps."
        )
        delete_btn = box.addButton("Delete Video", QMessageBox.AcceptRole)
        sub_btn = box.addButton("Delete video and sub-files", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked is delete_btn:
            self.delete_video_requested.emit(vid)
        elif clicked is sub_btn:
            self.delete_video_and_heatmaps_requested.emit(vid)
