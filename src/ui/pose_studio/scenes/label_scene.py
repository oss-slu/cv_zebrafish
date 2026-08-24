"""Label scene — human / review labeling with unique-rank advanced controls."""

from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.pose_studio.chrome.scene_shell import PoseSceneShell

_PROTECTED_LABEL_SET_IDS = frozenset({"human", "ai"})


class _LabelSetRow(QWidget):
    """Label-set picker row; exposes hover state for the removable-set close chip."""

    hovered_changed = pyqtSignal(bool)

    def enterEvent(self, event) -> None:
        self.hovered_changed.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered_changed.emit(False)
        super().leaveEvent(event)


class LabelScene(QWidget):
    """
    Label / review scene shell.

    Side: bodypart schema host. Main: label-set picker, timeline chrome, canvas host.
    Advanced: unique-rank reduce controls.
    """

    create_label_set_requested = pyqtSignal()
    label_set_changed = pyqtSignal(str)
    label_set_remove_requested = pyqtSignal(str)
    unique_reduce_requested = pyqtSignal(int)  # keep top-N ranked frames
    prev_requested = pyqtSignal()
    next_requested = pyqtSignal()
    auto_toggled = pyqtSignal(bool)
    undo_requested = pyqtSignal()
    redo_requested = pyqtSignal()
    review_mode_changed = pyqtSignal(bool)
    prev_outlier_requested = pyqtSignal()
    next_outlier_requested = pyqtSignal()
    heatmap_view_changed = pyqtSignal(bool)
    heatmap_archive_changed = pyqtSignal(str)
    photo_opacity_changed = pyqtSignal(int)
    points_opacity_changed = pyqtSignal(int)
    heatmap_opacity_changed = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LabelScene")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.shell = PoseSceneShell(show_context_bar=True, side_width=360)
        self.shell.set_advanced_visible(False)
        QTimer.singleShot(0, self.shell.fit_side_to_content)
        root.addWidget(self.shell)

        self._label_set_row_hovered = False
        self._build_side_panel()
        self._build_main_chrome()

    def _build_side_panel(self) -> None:
        mode_row = QHBoxLayout()
        mode_row.setSpacing(4)
        mode_lbl = QLabel("Mode")
        mode_lbl.setToolTip("Label: diverse frame queue. Review: scrub every frame with outlier QC.")
        mode_row.addWidget(mode_lbl)
        self._mode_group = QButtonGroup(self)
        self._mode_group.setExclusive(True)
        self._label_mode_btn = QPushButton("Label")
        self._label_mode_btn.setObjectName("LabelModeBtn")
        self._label_mode_btn.setCheckable(True)
        self._label_mode_btn.setChecked(True)
        self._label_mode_btn.setToolTip("Label a diverse frame queue (Detect Unique Frames)")
        self._review_mode_btn = QPushButton("Review")
        self._review_mode_btn.setObjectName("LabelReviewModeBtn")
        self._review_mode_btn.setCheckable(True)
        self._review_mode_btn.setToolTip(
            "Review every frame — edit points, jump to bone-stretch outliers"
        )
        for btn in (self._label_mode_btn, self._review_mode_btn):
            self._mode_group.addButton(btn)
            mode_row.addWidget(btn)
        mode_row.addStretch(1)
        mode_wrap = QWidget()
        mode_wrap.setLayout(mode_row)
        self.shell.add_side_widget(mode_wrap)

        self._label_mode_btn.toggled.connect(self._on_label_mode_toggled)
        self._review_mode_btn.toggled.connect(self._on_review_mode_toggled)

        schema_group = QGroupBox("Bodypart")
        schema_group.setToolTip("Bodypart list and labeling schema")
        schema_outer = QVBoxLayout(schema_group)
        schema_outer.setContentsMargins(8, 8, 8, 8)
        schema_outer.setSpacing(4)

        self.side_schema_host = QWidget()
        self.side_schema_host.setObjectName("LabelSideSchemaHost")
        self.side_schema_layout = QVBoxLayout(self.side_schema_host)
        self.side_schema_layout.setContentsMargins(0, 0, 0, 0)
        self.side_schema_layout.setSpacing(4)
        schema_outer.addWidget(self.side_schema_host, stretch=1)

        self.shell.add_side_widget(schema_group, stretch=1)

        self._heatmap_wrap = QWidget()
        self._heatmap_wrap.setObjectName("LabelHeatmapWrap")
        heatmap_layout = QVBoxLayout(self._heatmap_wrap)
        heatmap_layout.setContentsMargins(0, 0, 0, 0)
        heatmap_layout.setSpacing(6)

        self.view_heatmap_cb = QCheckBox("View Heatmap")
        self.view_heatmap_cb.setObjectName("LabelViewHeatmapCb")
        self.view_heatmap_cb.setToolTip(
            "Overlay the model heatmap for the selected bodypart on the current frame"
        )
        self.view_heatmap_cb.toggled.connect(self._on_view_heatmap_toggled)
        heatmap_layout.addWidget(self.view_heatmap_cb)

        archive_row = QHBoxLayout()
        archive_row.setSpacing(6)
        archive_lbl = QLabel("Archive")
        archive_lbl.setMinimumWidth(52)
        archive_row.addWidget(archive_lbl)
        self.heatmap_archive_combo = QComboBox()
        self.heatmap_archive_combo.setObjectName("LabelHeatmapArchiveCombo")
        self.heatmap_archive_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.heatmap_archive_combo.setToolTip(
            "Saved heatmap folder from Auto Label (when multiple runs exist)"
        )
        self.heatmap_archive_combo.currentIndexChanged.connect(
            self._on_heatmap_archive_index_changed
        )
        archive_row.addWidget(self.heatmap_archive_combo, stretch=1)
        heatmap_layout.addLayout(archive_row)

        self._heatmap_advanced_toggle = QToolButton()
        self._heatmap_advanced_toggle.setObjectName("LabelHeatmapAdvancedToggle")
        self._heatmap_advanced_toggle.setText("Advanced")
        self._heatmap_advanced_toggle.setCheckable(True)
        self._heatmap_advanced_toggle.setChecked(False)
        self._heatmap_advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._heatmap_advanced_toggle.setArrowType(Qt.RightArrow)
        self._heatmap_advanced_toggle.setToolTip("Opacity controls for photo, points, and heatmap")
        self._heatmap_advanced_toggle.toggled.connect(self._on_heatmap_advanced_toggled)
        heatmap_layout.addWidget(self._heatmap_advanced_toggle, alignment=Qt.AlignLeft)

        self._heatmap_advanced_body = QWidget()
        self._heatmap_advanced_body.setObjectName("LabelHeatmapAdvancedBody")
        self._heatmap_advanced_body.setVisible(False)
        advanced_layout = QVBoxLayout(self._heatmap_advanced_body)
        advanced_layout.setContentsMargins(8, 0, 0, 0)
        advanced_layout.setSpacing(6)

        self.photo_opacity_slider = self._make_opacity_slider("LabelPhotoOpacitySlider")
        self.points_opacity_slider = self._make_opacity_slider("LabelPointsOpacitySlider")
        self.heatmap_opacity_slider = self._make_opacity_slider("LabelHeatmapOpacitySlider")
        self.photo_opacity_slider.setValue(100)
        self.points_opacity_slider.setValue(100)
        self.heatmap_opacity_slider.setValue(65)
        self._set_opacity_sliders_enabled(False)

        advanced_layout.addWidget(self._opacity_row("Photo", self.photo_opacity_slider))
        advanced_layout.addWidget(self._opacity_row("Labeled points", self.points_opacity_slider))
        advanced_layout.addWidget(self._opacity_row("Heatmap", self.heatmap_opacity_slider))

        self.photo_opacity_slider.valueChanged.connect(self.photo_opacity_changed.emit)
        self.points_opacity_slider.valueChanged.connect(self.points_opacity_changed.emit)
        self.heatmap_opacity_slider.valueChanged.connect(self.heatmap_opacity_changed.emit)

        heatmap_layout.addWidget(self._heatmap_advanced_body)
        self.shell.add_side_widget(self._heatmap_wrap)
        self._heatmap_wrap.setVisible(False)

    @staticmethod
    def _make_opacity_slider(object_name: str) -> QSlider:
        slider = QSlider(Qt.Horizontal)
        slider.setObjectName(object_name)
        slider.setRange(0, 100)
        slider.setToolTip("Opacity (0–100%)")
        return slider

    @staticmethod
    def _opacity_row(label: str, slider: QSlider) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        lbl = QLabel(label)
        lbl.setMinimumWidth(88)
        layout.addWidget(lbl)
        layout.addWidget(slider, stretch=1)
        return row

    def _set_opacity_sliders_enabled(self, enabled: bool) -> None:
        for slider in (
            self.photo_opacity_slider,
            self.points_opacity_slider,
            self.heatmap_opacity_slider,
        ):
            slider.setEnabled(enabled)

    def _on_view_heatmap_toggled(self, checked: bool) -> None:
        self._set_opacity_sliders_enabled(checked)
        self.heatmap_view_changed.emit(checked)

    def _on_heatmap_advanced_toggled(self, checked: bool) -> None:
        self._heatmap_advanced_body.setVisible(checked)
        self._heatmap_advanced_toggle.setArrowType(
            Qt.DownArrow if checked else Qt.RightArrow
        )

    def _on_heatmap_archive_index_changed(self, _index: int) -> None:
        key = self.heatmap_archive_combo.currentData()
        if key is not None:
            self.heatmap_archive_changed.emit(str(key))

    def set_heatmap_archives(self, items: list[tuple[str, str]]) -> None:
        """Populate archive picker; each item is (archive_key, display label)."""
        current = self.heatmap_archive_combo.currentData()
        self.heatmap_archive_combo.blockSignals(True)
        self.heatmap_archive_combo.clear()
        for key, label in items:
            self.heatmap_archive_combo.addItem(label, key)
        if current is not None:
            idx = self.heatmap_archive_combo.findData(current)
            if idx >= 0:
                self.heatmap_archive_combo.setCurrentIndex(idx)
        self.heatmap_archive_combo.blockSignals(False)
        has_archives = bool(items)
        self.heatmap_archive_combo.setVisible(has_archives and len(items) > 1)
        self.set_heatmap_available(has_archives)

    def set_heatmap_available(self, available: bool) -> None:
        """Enable or disable heatmap overlay controls (requires saved AI heatmaps)."""
        self.view_heatmap_cb.setEnabled(available)
        self.heatmap_archive_combo.setEnabled(available)
        if not available:
            self.view_heatmap_cb.blockSignals(True)
            self.view_heatmap_cb.setChecked(False)
            self.view_heatmap_cb.blockSignals(False)
            self._set_opacity_sliders_enabled(False)
            self.heatmap_view_changed.emit(False)
        elif self.view_heatmap_cb.isChecked():
            self._set_opacity_sliders_enabled(True)

    def set_view_heatmap(self, enabled: bool) -> None:
        """Sync the View Heatmap toggle without emitting ``heatmap_view_changed``."""
        enabled = bool(enabled)
        self.view_heatmap_cb.blockSignals(True)
        self.view_heatmap_cb.setChecked(enabled)
        self.view_heatmap_cb.blockSignals(False)
        self._set_opacity_sliders_enabled(enabled and self.view_heatmap_cb.isEnabled())

    def _build_main_chrome(self) -> None:
        chrome = QWidget()
        chrome.setObjectName("LabelMainChrome")
        chrome_layout = QVBoxLayout(chrome)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(6)

        self.label_set_row = _LabelSetRow()
        self.label_set_row.setObjectName("LabelSetRow")
        self.label_set_row.setToolTip("Active label set")
        self.label_set_row.hovered_changed.connect(self._on_label_set_row_hovered)
        label_set_row = QHBoxLayout(self.label_set_row)
        label_set_row.setContentsMargins(0, 0, 0, 0)
        label_set_row.setSpacing(6)

        self.label_set_combo = QComboBox()
        self.label_set_combo.setObjectName("LabelSetCombo")
        self.label_set_combo.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.label_set_combo.setToolTip("Active label set")
        self.label_set_combo.currentIndexChanged.connect(self._on_label_set_index_changed)
        label_set_row.addWidget(self.label_set_combo, stretch=1)

        self.label_set_close_btn = QToolButton()
        self.label_set_close_btn.setObjectName("LabelSetCloseBtn")
        self.label_set_close_btn.setText("\u00d7")
        self.label_set_close_btn.setToolTip("Remove this custom label set")
        self.label_set_close_btn.setCursor(Qt.PointingHandCursor)
        self.label_set_close_btn.setVisible(False)
        self.label_set_close_btn.clicked.connect(self._on_label_set_close_clicked)
        label_set_row.addWidget(self.label_set_close_btn)

        self.create_labels_btn = QPushButton("Create New Labels")
        self.create_labels_btn.setObjectName("LabelCreateSetBtn")
        self.create_labels_btn.setToolTip("Create a new named label set")
        self.create_labels_btn.clicked.connect(self.create_label_set_requested.emit)
        label_set_row.addWidget(self.create_labels_btn)
        chrome_layout.addWidget(self.label_set_row)

        timeline_row = QHBoxLayout()
        timeline_row.setSpacing(4)

        self.prev_outlier_btn = QPushButton("◀ Outlier")
        self.prev_outlier_btn.setObjectName("LabelPrevOutlierBtn")
        self.prev_outlier_btn.setToolTip("Previous outlier frame (bone stretch or jump)")
        self.prev_outlier_btn.clicked.connect(self.prev_outlier_requested.emit)
        self.prev_outlier_btn.setVisible(False)
        timeline_row.addWidget(self.prev_outlier_btn)

        self.prev_btn = QPushButton("Prev frame")
        self.prev_btn.setObjectName("LabelPrevBtn")
        self.prev_btn.setToolTip("Previous frame in the labeling queue (Left arrow)")
        self.prev_btn.clicked.connect(self.prev_requested.emit)
        timeline_row.addWidget(self.prev_btn)

        self.timeline_host = QWidget()
        self.timeline_host.setObjectName("LabelTimelineHost")
        self.timeline_host.setMinimumHeight(36)
        self.timeline_host.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.timeline_host.setToolTip("Frame timeline")
        self.timeline_layout = QVBoxLayout(self.timeline_host)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(0)
        timeline_row.addWidget(self.timeline_host, stretch=1)

        self.next_btn = QPushButton("Next frame")
        self.next_btn.setObjectName("LabelNextBtn")
        self.next_btn.setToolTip("Next frame in the labeling queue (Right arrow or Space)")
        self.next_btn.clicked.connect(self.next_requested.emit)
        timeline_row.addWidget(self.next_btn)

        self.next_outlier_btn = QPushButton("Outlier ▶")
        self.next_outlier_btn.setObjectName("LabelNextOutlierBtn")
        self.next_outlier_btn.setToolTip("Next outlier frame (bone stretch or jump)")
        self.next_outlier_btn.clicked.connect(self.next_outlier_requested.emit)
        self.next_outlier_btn.setVisible(False)
        timeline_row.addWidget(self.next_outlier_btn)

        self.auto_btn = QToolButton()
        self.auto_btn.setObjectName("LabelAutoBtn")
        self.auto_btn.setText("Auto")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setChecked(True)
        self.auto_btn.setToolTip("Advance to next frame after placing a point")
        self.auto_btn.toggled.connect(self.auto_toggled.emit)
        timeline_row.addWidget(self.auto_btn)

        self.undo_btn = QToolButton()
        self.undo_btn.setObjectName("LabelUndoBtn")
        self.undo_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self.undo_btn.setToolTip("Undo")
        self.undo_btn.clicked.connect(self.undo_requested.emit)
        timeline_row.addWidget(self.undo_btn)

        self.redo_btn = QToolButton()
        self.redo_btn.setObjectName("LabelRedoBtn")
        self.redo_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self.redo_btn.setToolTip("Redo")
        self.redo_btn.clicked.connect(self.redo_requested.emit)
        timeline_row.addWidget(self.redo_btn)

        chrome_layout.addLayout(timeline_row)
        self.shell.add_main_widget(chrome, stretch=0)

        self.content_host = QWidget()
        self.content_host.setObjectName("LabelContentHost")
        self.content_layout = QVBoxLayout(self.content_host)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.shell.add_main_widget(self.content_host, stretch=1)

    def _build_advanced_panel(self) -> None:
        unique_group = QGroupBox("Unique frames")
        unique_group.setToolTip("Reduce labeled frames to top unique ranks")
        unique_layout = QVBoxLayout(unique_group)
        unique_layout.setContentsMargins(8, 8, 8, 8)
        unique_layout.setSpacing(6)

        keep_row = QHBoxLayout()
        keep_row.setSpacing(6)

        self.unique_keep_spin = QSpinBox()
        self.unique_keep_spin.setObjectName("LabelUniqueKeepSpin")
        self.unique_keep_spin.setRange(1, 9999)
        self.unique_keep_spin.setValue(300)
        self.unique_keep_spin.setToolTip("Keep this many highest-ranked labeled frames")
        keep_row.addWidget(self.unique_keep_spin)

        self.unique_keep_slider = QSlider(Qt.Horizontal)
        self.unique_keep_slider.setObjectName("LabelUniqueKeepSlider")
        self.unique_keep_slider.setRange(1, 9999)
        self.unique_keep_slider.setValue(300)
        self.unique_keep_slider.setToolTip("Keep this many highest-ranked labeled frames")
        keep_row.addWidget(self.unique_keep_slider, stretch=1)

        self.unique_keep_spin.valueChanged.connect(self._sync_unique_slider_from_spin)
        self.unique_keep_slider.valueChanged.connect(self._sync_unique_spin_from_slider)
        unique_layout.addLayout(keep_row)

        self.unique_reduce_btn = QPushButton("Apply unique reduce")
        self.unique_reduce_btn.setObjectName("LabelUniqueReduceBtn")
        self.unique_reduce_btn.setToolTip(
            "Drop lower-ranked frames; keep the top unique picks"
        )
        self.unique_reduce_btn.clicked.connect(self._on_unique_reduce_clicked)
        unique_layout.addWidget(self.unique_reduce_btn)

        self.gap_fills_ranked_cb = QCheckBox("Gap fills included in ranking")
        self.gap_fills_ranked_cb.setObjectName("LabelGapFillsRankedCb")
        self.gap_fills_ranked_cb.setChecked(True)
        self.gap_fills_ranked_cb.setEnabled(False)
        self.gap_fills_ranked_cb.setToolTip(
            "Gap-fill frames are ranked with diverse picks and stored in the pose scan cache"
        )
        unique_layout.addWidget(self.gap_fills_ranked_cb)

        self.shell.add_advanced_widget(unique_group)

    def _on_label_mode_toggled(self, checked: bool) -> None:
        if checked:
            self._apply_review_chrome(False)
            self.review_mode_changed.emit(False)

    def _on_review_mode_toggled(self, checked: bool) -> None:
        if checked:
            self._apply_review_chrome(True)
            self.review_mode_changed.emit(True)

    def set_review_mode(self, review: bool) -> None:
        """Sync the Label / Review toggle without emitting ``review_mode_changed``."""
        self._label_mode_btn.blockSignals(True)
        self._review_mode_btn.blockSignals(True)
        self._label_mode_btn.setChecked(not review)
        self._review_mode_btn.setChecked(review)
        self._label_mode_btn.blockSignals(False)
        self._review_mode_btn.blockSignals(False)
        self._apply_review_chrome(review)

    def _apply_review_chrome(self, review: bool) -> None:
        self.prev_outlier_btn.setVisible(review)
        self.next_outlier_btn.setVisible(review)
        self._heatmap_wrap.setVisible(review)
        if not review:
            self.set_view_heatmap(False)
            self._heatmap_advanced_toggle.setChecked(False)
            self._heatmap_advanced_body.setVisible(False)
            self._heatmap_advanced_toggle.setArrowType(Qt.RightArrow)
            self.heatmap_view_changed.emit(False)
        if review:
            self.prev_btn.setToolTip("Previous video frame (Left arrow)")
            self.next_btn.setToolTip("Next video frame (Right arrow or Space)")
        else:
            self.prev_btn.setToolTip("Previous frame in the labeling queue (Left arrow)")
            self.next_btn.setToolTip("Next frame in the labeling queue (Right arrow or Space)")

    def _on_label_set_row_hovered(self, hovered: bool) -> None:
        self._label_set_row_hovered = hovered
        self._update_label_set_close_btn()

    def _active_label_set_id(self) -> str | None:
        label_id = self.label_set_combo.currentData()
        return str(label_id) if label_id is not None else None

    def _update_label_set_close_btn(self) -> None:
        label_id = self._active_label_set_id()
        removable = (
            label_id is not None
            and label_id not in _PROTECTED_LABEL_SET_IDS
            and self._label_set_row_hovered
        )
        self.label_set_close_btn.setVisible(removable)

    def _on_label_set_close_clicked(self) -> None:
        label_id = self._active_label_set_id()
        if label_id is None or label_id in _PROTECTED_LABEL_SET_IDS:
            return
        self.label_set_remove_requested.emit(label_id)

    def _on_label_set_index_changed(self, _index: int) -> None:
        self._update_label_set_close_btn()
        label_id = self._active_label_set_id()
        if label_id is not None:
            self.label_set_changed.emit(label_id)

    def _sync_unique_slider_from_spin(self, value: int) -> None:
        if self.unique_keep_slider.value() != value:
            self.unique_keep_slider.blockSignals(True)
            self.unique_keep_slider.setValue(value)
            self.unique_keep_slider.blockSignals(False)

    def _sync_unique_spin_from_slider(self, value: int) -> None:
        if self.unique_keep_spin.value() != value:
            self.unique_keep_spin.blockSignals(True)
            self.unique_keep_spin.setValue(value)
            self.unique_keep_spin.blockSignals(False)

    def _on_unique_reduce_clicked(self) -> None:
        self.unique_reduce_requested.emit(self.unique_keep_spin.value())

    def set_label_sets(self, items: list[tuple[str, str]]) -> None:
        """Populate label-set dropdown; each item is (id, display text e.g. name k/n)."""
        self.label_set_combo.blockSignals(True)
        self.label_set_combo.clear()
        for label_id, display in items:
            self.label_set_combo.addItem(display, label_id)
        self.label_set_combo.blockSignals(False)

    def set_active_label_set(self, label_set_id: str) -> None:
        """Select the active label set without emitting ``label_set_changed``."""
        idx = self.label_set_combo.findData(label_set_id)
        if idx < 0:
            return
        self.label_set_combo.blockSignals(True)
        self.label_set_combo.setCurrentIndex(idx)
        self.label_set_combo.blockSignals(False)
        self._update_label_set_close_btn()

    def mount_bodypart_list(self, widget: QWidget) -> None:
        """Reparent the bodypart schema panel into the scene side host."""
        self._replace_host_child(self.side_schema_layout, widget)

    def mount_timeline_widget(self, widget: QWidget) -> None:
        """Reparent the frame timeline strip into the scene timeline host."""
        self._replace_host_child(self.timeline_layout, widget)

    @staticmethod
    def _replace_host_child(layout: QVBoxLayout, widget: QWidget) -> None:
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
        layout.addWidget(widget, stretch=1)

    def set_content_widget(self, widget: QWidget) -> None:
        """Replace main content (e.g. existing PoseLabelWidget canvas area)."""
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self.content_layout.addWidget(widget, stretch=1)
