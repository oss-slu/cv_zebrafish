"""Auto Label scene — run model labeling; view output jumps to Label."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.pose_studio.chrome.scene_shell import PoseSceneShell
from ui.pose_studio.chrome.tab_icons import auto_label_tab_icon
from ui.pose_studio.chrome.task_progress_bar import TaskProgressBar

__all__ = ["AutoLabelScene", "auto_label_tab_icon"]


class AutoLabelScene(QWidget):
    """
    Auto Label scene shell.

    Side: video + model pickers, run controls, heatmap options.
    Main: ``content_host`` (optional embed) + ``progress`` + one-line status.
    """

    run_requested = pyqtSignal()
    view_output_requested = pyqtSignal()
    video_changed = pyqtSignal(str)
    model_changed = pyqtSignal(str)

    _VIDEO_ID_ROLE = Qt.UserRole
    _MODEL_KEY_ROLE = Qt.UserRole
    _HEATMAP_KEY_ROLE = Qt.UserRole

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AutoLabelScene")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.shell = PoseSceneShell(show_context_bar=True, side_width=380)
        QTimer.singleShot(0, self.shell.fit_side_to_content)
        self.shell.set_advanced_visible(False)
        root.addWidget(self.shell)

        self._build_side_panel()
        self._build_main_panel()

    def _build_side_panel(self) -> None:
        inputs_box = QGroupBox("Inputs")
        inputs_box.setToolTip("Choose the video and model for auto-labeling")
        form = QFormLayout(inputs_box)

        self.video_combo = QComboBox()
        self.video_combo.setObjectName("AutoLabelVideoCombo")
        self.video_combo.setToolTip("Select a cropped video to auto-label")
        self.video_combo.currentIndexChanged.connect(self._on_video_combo_changed)
        form.addRow("Video", self.video_combo)

        self.model_combo = QComboBox()
        self.model_combo.setObjectName("AutoLabelModelCombo")
        self.model_combo.setToolTip("Select a trained model checkpoint")
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        form.addRow("Model", self.model_combo)
        self.shell.add_side_widget(inputs_box)

        run_box = QGroupBox("Run")
        run_box.setToolTip("Start auto-label or open results on the Label tab")
        rl = QVBoxLayout(run_box)

        self.run_btn = QPushButton("Run labeling")
        self.run_btn.setObjectName("AutoLabelRunButton")
        self.run_btn.setToolTip(
            "Run auto-label on the selected video and model"
        )
        self.run_btn.clicked.connect(self.run_requested.emit)
        rl.addWidget(self.run_btn)

        self.view_output_btn = QPushButton("View output")
        self.view_output_btn.setObjectName("AutoLabelViewOutputButton")
        self.view_output_btn.setToolTip("Open auto-label results on the Label tab")
        self.view_output_btn.clicked.connect(self.view_output_requested.emit)
        rl.addWidget(self.view_output_btn)
        self.shell.add_side_widget(run_box)

        heatmap_box = QGroupBox("Heatmaps")
        heatmap_box.setToolTip("Save or reuse per-frame heatmap archives")
        hf = QFormLayout(heatmap_box)

        self.save_heatmaps_cb = QCheckBox("Save heatmaps")
        self.save_heatmaps_cb.setObjectName("SaveHeatmapsCheck")
        self.save_heatmaps_cb.setChecked(True)
        self.save_heatmaps_cb.setToolTip(
            "Write per-frame heatmap archives to disk during auto-label"
        )
        hf.addRow("", self.save_heatmaps_cb)

        self.heatmap_combo = QComboBox()
        self.heatmap_combo.setObjectName("HeatmapCombo")
        self.heatmap_combo.setToolTip("Saved heatmap archive for this video")
        hf.addRow("Archive", self.heatmap_combo)
        self.shell.add_side_widget(heatmap_box)

    def _build_main_panel(self) -> None:
        self.content_host = QWidget()
        self.content_host.setObjectName("AutoLabelContentHost")
        self.content_layout = QVBoxLayout(self.content_host)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addStretch(1)
        self.shell.add_main_widget(self.content_host, stretch=1)

        self.progress = TaskProgressBar()
        self.progress.setToolTip("Auto-label job progress and ETA")
        self.progress.set_progress(0, 0, activity="Auto-labeling", unit="frames")
        self.shell.add_main_widget(self.progress, stretch=0)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("AutoLabelSceneStatus")
        self.status_lbl.setToolTip("Last auto-label status message")
        self.status_lbl.setWordWrap(False)
        self.shell.add_main_widget(self.status_lbl, stretch=0)

    def _on_video_combo_changed(self, _index: int) -> None:
        video_id = self.selected_video_id()
        if video_id:
            self.video_changed.emit(video_id)

    def _on_model_combo_changed(self, _index: int) -> None:
        model_key = self.selected_model_key()
        if model_key:
            self.model_changed.emit(model_key)

    # --- Inputs ---

    def set_videos(self, items: list[tuple[str, str]]) -> None:
        """Populate the video combo. Each item is ``(video_id, label)``."""
        self.video_combo.blockSignals(True)
        self.video_combo.clear()
        for video_id, label in items:
            self.video_combo.addItem(label, video_id)
        self.video_combo.blockSignals(False)

    def set_models(self, items: list[tuple[str, str]]) -> None:
        """Populate the model combo. Each item is ``(model_key, label)``."""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for model_key, label in items:
            self.model_combo.addItem(label, model_key)
        self.model_combo.blockSignals(False)

    def selected_video_id(self) -> str | None:
        data = self.video_combo.currentData()
        return str(data) if data else None

    def selected_model_key(self) -> str | None:
        data = self.model_combo.currentData()
        return str(data) if data else None

    def set_selected_video(self, video_id: str) -> None:
        idx = self.video_combo.findData(video_id)
        if idx >= 0:
            self.video_combo.setCurrentIndex(idx)

    def set_selected_model(self, model_key: str) -> None:
        idx = self.model_combo.findData(model_key)
        if idx >= 0:
            self.model_combo.setCurrentIndex(idx)

    # --- Heatmaps ---

    def set_heatmap_archives(self, items: list[tuple[str, str]]) -> None:
        """Populate the heatmap archive combo. Each item is ``(archive_key, label)``."""
        self.heatmap_combo.blockSignals(True)
        self.heatmap_combo.clear()
        for archive_key, label in items:
            self.heatmap_combo.addItem(label, archive_key)
        has_archives = bool(items)
        self.heatmap_combo.setEnabled(has_archives)
        self.heatmap_combo.blockSignals(False)

    def selected_heatmap_archive_key(self) -> str | None:
        data = self.heatmap_combo.currentData()
        return str(data) if data else None

    def set_selected_heatmap_archive(self, archive_key: str) -> None:
        idx = self.heatmap_combo.findData(archive_key)
        if idx >= 0:
            self.heatmap_combo.setCurrentIndex(idx)

    def save_heatmaps(self) -> bool:
        return self.save_heatmaps_cb.isChecked()

    def set_save_heatmaps(self, checked: bool) -> None:
        self.save_heatmaps_cb.setChecked(checked)

    # --- Run controls ---

    def set_run_enabled(self, enabled: bool, *, tooltip: str = "") -> None:
        self.run_btn.setEnabled(enabled)
        if tooltip:
            self.run_btn.setToolTip(tooltip)
        elif enabled:
            self.run_btn.setToolTip(
                "Run auto-label on the selected video and model"
            )

    def set_view_output_enabled(self, enabled: bool) -> None:
        self.view_output_btn.setEnabled(enabled)

    # --- Main panel ---

    def set_content_widget(self, widget: QWidget) -> None:
        """Replace optional main content (e.g. legacy ``PoseAutoLabelWidget``)."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.content_layout.addWidget(widget, stretch=1)

    def clear_content_widget(self) -> None:
        """Remove embedded content and leave an empty stretch host."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.content_layout.addStretch(1)

    def set_status(self, text: str) -> None:
        self.status_lbl.setText(text)
