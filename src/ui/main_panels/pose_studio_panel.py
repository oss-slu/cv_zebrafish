"""Pose Studio — video upload, arena, and blob setup."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QDialog,
)

from app_platform.paths import pose_video_dir
from app_platform.ui_preferences import UiPreferences, save_ui_preferences
from core.pose.detection.arena import ArenaConfig, load_arena, save_arena
from core.pose.detection.blob import BlobParams, load_blob_params, save_blob_params
from core.pose.detection.histogram import suggest_brightness_range
from core.pose.cache.playback_blob_cache import (
    PlaybackBlobEntry,
    load_playback_overlay_cache,
    playback_blob_cache_key,
    save_playback_overlay_cache,
)
from core.pose.video.video_reader import VideoFrameReader
from core.pose.video.video_registry import (
    LARGE_FILE_WARNING_BYTES,
    read_video_meta,
    resolve_video_source,
)
from core.pose.video.video_transcode import needs_transcode
from session.session import Session
from ui.components.pose.frame_scrubber import FrameScrubber
from ui.components.pose.pose_preview_widget import PosePreviewWidget
from ui.components.widgets.scene_help import create_scene_help_button
from ui.main_panels.pose_dataset_widget import PoseDatasetWidget
from ui.main_panels.pose_label_widget import PoseLabelWidget
from ui.main_panels.pose_train_widget import PoseTrainWidget
from ui.popup_panels.video_upload_dialog import VideoUploadDialog
from ui.workers.blob_scan_worker import BlobScanWorker
from ui.workers.playback_migrate_worker import PlaybackMigrateWorker
from ui.workers.playback_blob_cache_worker import PlaybackBlobCacheWorker
from ui.workers.video_register_worker import VideoRegisterWorker


class PoseStudioPanel(QWidget):
    """Steps 1–3: videos, arena/blob setup, labeling."""

    PREVIEW_MAX_EDGE = 640

    dataset_send_to_verify = pyqtSignal(str)
    dataset_json_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseStudioPanel")
        self._session: Session | None = None
        self._ui_prefs = UiPreferences()
        self._reader: VideoFrameReader | None = None
        self._panel_visible = False
        self._needs_video_open = False
        self._current_video_id: str | None = None
        self._arena = ArenaConfig()
        self._blob_params = BlobParams()
        self._register_worker: VideoRegisterWorker | None = None
        self._blob_worker: BlobScanWorker | None = None
        self._migrate_worker: PlaybackMigrateWorker | None = None
        self._blob_cache_worker: PlaybackBlobCacheWorker | None = None
        self._blob_playback_cache: list[PlaybackBlobEntry] | None = None
        self._blob_cache_key: str | None = None
        self._blob_cache_frame_count = 0
        self._setup_preview: PosePreviewWidget | None = None
        self._ui_ready = False
        self._busy = QLabel("")
        self._busy.setObjectName("SettingsHintLabel")
        self._busy.hide()
        self._busy_bar = QProgressBar()
        self._busy_bar.setObjectName("PoseStudioBusyBar")
        self._busy_bar.setTextVisible(True)
        self._busy_bar.hide()
        self._pending_scrub_index: int | None = None
        self._scrub_preview_timer = QTimer(self)
        self._scrub_preview_timer.setSingleShot(True)
        self._scrub_preview_timer.timeout.connect(self._flush_scrub_preview)
        self._blob_cache_debounce = QTimer(self)
        self._blob_cache_debounce.setSingleShot(True)
        self._blob_cache_debounce.timeout.connect(self._start_blob_cache_build)
        self._setup_tab_index = 1
        self._loading_dots = 0
        self._loading_dots_timer = QTimer(self)
        self._loading_dots_timer.timeout.connect(self._tick_pose_loading_label)

        root = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel("Pose Studio"))
        header.addStretch(1)
        header.addWidget(
            create_scene_help_button(
                self,
                title="Pose Studio",
                paragraph=self._help_text(),
            )
        )
        root.addLayout(header)
        root.addWidget(self._busy)
        root.addWidget(self._busy_bar)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs, stretch=1)

        # --- Videos tab ---
        videos = QWidget()
        vl = QVBoxLayout(videos)
        row = QHBoxLayout()
        self._upload_btn = QPushButton("Upload Video…")
        self._upload_btn.clicked.connect(self._on_upload)
        row.addWidget(self._upload_btn)
        row.addStretch(1)
        vl.addLayout(row)
        self._video_combo = QComboBox()
        self._video_combo.currentIndexChanged.connect(self._on_video_selected)
        vl.addWidget(self._video_combo)
        self._preview = PosePreviewWidget()
        self._preview.set_preview_max_edge(self.PREVIEW_MAX_EDGE)
        self._setup_preview = PosePreviewWidget()
        self._setup_preview.set_preview_max_edge(self.PREVIEW_MAX_EDGE)
        vl.addWidget(self._preview, stretch=1)
        self._tabs.addTab(videos, "Videos")

        # --- Setup tab ---
        setup = QWidget()
        sl = QVBoxLayout(setup)
        self._scrubber = FrameScrubber()
        self._scrubber.frame_changed.connect(self._on_scrubber_frame)
        self._scrubber.frame_preview.connect(self._on_scrubber_preview)
        self._scrubber.playback_stopped.connect(self._on_scrubber_playback_stopped)
        self._scrubber.playback_started.connect(self._on_scrubber_playback_started)
        sl.addWidget(self._scrubber)
        self._cache_hint = QLabel("")
        self._cache_hint.setObjectName("SettingsHintLabel")
        self._cache_hint.hide()
        sl.addWidget(self._cache_hint)

        arena_hint = QLabel(
            "Step 1: position the arena rectangle (drag inside to move, edges/corners to resize), "
            "then confirm. Circle arenas: drag center to move, drag outside or scroll to resize."
        )
        arena_hint.setWordWrap(True)
        arena_hint.setObjectName("SettingsHintLabel")
        sl.addWidget(arena_hint)

        arena_box = QGroupBox("Arena")
        af = QFormLayout(arena_box)
        self._arena_shape = QComboBox()
        self._arena_shape.addItem("Rectangle", "square")
        self._arena_shape.addItem("Circle", "circle")
        af.addRow("Shape", self._arena_shape)
        self._rect_x = QSlider(Qt.Horizontal)
        self._rect_y = QSlider(Qt.Horizontal)
        self._rect_w = QSlider(Qt.Horizontal)
        self._rect_h = QSlider(Qt.Horizontal)
        for slider in (self._rect_x, self._rect_y, self._rect_w, self._rect_h):
            slider.setRange(0, 100)
        self._rect_w.setRange(5, 100)
        self._rect_h.setRange(5, 100)
        self._rect_x_label = QLabel("X (left)")
        self._rect_y_label = QLabel("Y (top)")
        self._rect_w_label = QLabel("Width")
        self._rect_h_label = QLabel("Height")
        af.addRow(self._rect_x_label, self._rect_x)
        af.addRow(self._rect_y_label, self._rect_y)
        af.addRow(self._rect_w_label, self._rect_w)
        af.addRow(self._rect_h_label, self._rect_h)
        self._circle_size = QSlider(Qt.Horizontal)
        self._circle_size.setRange(10, 100)
        self._circle_size_label = QLabel("Diameter")
        af.addRow(self._circle_size_label, self._circle_size)
        self._circle_size.hide()
        self._circle_size_label.hide()
        arena_btn_row = QHBoxLayout()
        self._confirm_arena_btn = QPushButton("Confirm arena")
        self._confirm_arena_btn.clicked.connect(self._on_confirm_arena)
        self._edit_arena_btn = QPushButton("Edit arena…")
        self._edit_arena_btn.clicked.connect(self._on_edit_arena)
        self._edit_arena_btn.hide()
        arena_btn_row.addWidget(self._confirm_arena_btn)
        arena_btn_row.addWidget(self._edit_arena_btn)
        arena_btn_row.addStretch(1)
        af.addRow(arena_btn_row)
        sl.addWidget(arena_box)

        blob_box = QGroupBox("Blob threshold")
        self._blob_box = blob_box
        bf = QFormLayout(blob_box)
        self._bright_min = QSlider(Qt.Horizontal)
        self._bright_min.setRange(0, 254)
        self._bright_min.setValue(self._blob_params.brightness_min)
        self._bright_max = QSlider(Qt.Horizontal)
        self._bright_max.setRange(1, 255)
        self._bright_max.setValue(self._blob_params.brightness_max)
        bf.addRow("Min brightness", self._bright_min)
        bf.addRow("Max brightness", self._bright_max)
        self._blob_padding_px = QSlider(Qt.Horizontal)
        self._blob_padding_px.setRange(0, 40)
        self._blob_padding_px.setValue(self._blob_params.blob_padding_px)
        self._blob_padding_px.setToolTip(
            "Expand the detected fish mask outward before drawing the blob outline."
        )
        self._crop_padding_px = QSlider(Qt.Horizontal)
        self._crop_padding_px.setRange(0, 80)
        self._crop_padding_px.setValue(self._blob_params.crop_padding_px)
        self._crop_padding_px.setToolTip(
            "Extra margin around the fish bounding box when sizing the square labeling crop."
        )
        bf.addRow("Blob padding (px)", self._blob_padding_px)
        bf.addRow("Crop padding (px)", self._crop_padding_px)
        self._auto_thresh_btn = QPushButton("Suggest from histogram")
        self._auto_thresh_btn.clicked.connect(self._on_auto_threshold)
        bf.addRow(self._auto_thresh_btn)
        sl.addWidget(blob_box)

        save_row = QHBoxLayout()
        self._save_setup_btn = QPushButton("Save blob settings")
        self._save_setup_btn.clicked.connect(self._save_video_setup)
        self._scan_btn = QPushButton("Scan video for jumps")
        self._scan_btn.clicked.connect(self._on_blob_scan)
        save_row.addWidget(self._save_setup_btn)
        save_row.addWidget(self._scan_btn)
        save_row.addStretch(1)
        sl.addLayout(save_row)

        self._blob_locked_hint = QLabel("Confirm the arena above to unlock blob thresholding.")
        self._blob_locked_hint.setWordWrap(True)
        self._blob_locked_hint.setObjectName("SettingsHintLabel")
        sl.addWidget(self._blob_locked_hint)

        self._setup_preview.set_arena_editable(True)
        self._setup_preview.arena_changed.connect(self._on_arena_dragged)
        sl.addWidget(self._setup_preview, stretch=1)
        self._tabs.addTab(setup, "Select Crop")

        self._label_widget = PoseLabelWidget()
        self._label_widget.tracking_exported.connect(self._on_tracking_exported)
        self._tabs.addTab(self._label_widget, "Label")

        self._train_widget = PoseTrainWidget()
        self._train_widget.labels_imported.connect(self._on_labels_imported)
        self._tabs.addTab(self._train_widget, "Train")

        self._dataset_widget = PoseDatasetWidget()
        self._dataset_widget.send_to_verify.connect(self.dataset_send_to_verify.emit)
        self._dataset_widget.json_selected.connect(self.dataset_json_selected.emit)
        self._tabs.addTab(self._dataset_widget, "Datasets")

        self._label_tab_index = self._tabs.indexOf(self._label_widget)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._bind_arena_blob_signals()
        self._sync_arena_sliders_from_model()
        self._update_arena_blob_ui_state()
        self._ui_ready = True

        self._loading_overlay = QWidget(self)
        self._loading_overlay.setObjectName("PoseStudioLoadingOverlay")
        self._loading_overlay.setAttribute(Qt.WA_StyledBackground, True)
        overlay_layout = QVBoxLayout(self._loading_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.addStretch(1)
        self._loading_label = QLabel("Pose Studio loading")
        self._loading_label.setObjectName("PoseStudioLoadingLabel")
        self._loading_label.setAlignment(Qt.AlignCenter)
        overlay_layout.addWidget(self._loading_label)
        overlay_layout.addStretch(1)
        self._loading_overlay.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_loading_overlay"):
            self._loading_overlay.setGeometry(self.rect())

    def _tick_pose_loading_label(self) -> None:
        self._loading_dots = (self._loading_dots + 1) % 4
        self._loading_label.setText(
            "Pose Studio loading" + "." * self._loading_dots
        )

    def _show_pose_loading(self) -> None:
        self._loading_dots = 0
        self._tick_pose_loading_label()
        self._loading_overlay.setGeometry(self.rect())
        self._loading_overlay.raise_()
        self._loading_overlay.show()
        self._loading_dots_timer.start(400)

    def _hide_pose_loading(self) -> None:
        self._loading_dots_timer.stop()
        self._loading_overlay.hide()

    def _bind_arena_blob_signals(self) -> None:
        """Wire arena/blob controls after every preview widget exists."""
        self._arena_shape.currentIndexChanged.connect(self._on_arena_shape_changed)
        for slider in (self._rect_x, self._rect_y, self._rect_w, self._rect_h):
            slider.valueChanged.connect(self._on_arena_controls)
        self._circle_size.valueChanged.connect(self._on_arena_controls)
        for slider in (
            self._bright_min,
            self._bright_max,
            self._blob_padding_px,
            self._crop_padding_px,
        ):
            slider.valueChanged.connect(self._on_blob_sliders)

    def _iter_previews(self):
        yield self._preview
        if self._setup_preview is not None:
            yield self._setup_preview

    def _show_circle_arena_controls(self, circle: bool) -> None:
        for w in (
            self._rect_x,
            self._rect_y,
            self._rect_w,
            self._rect_h,
            self._rect_x_label,
            self._rect_y_label,
            self._rect_w_label,
            self._rect_h_label,
        ):
            w.setVisible(not circle)
        self._circle_size.setVisible(circle)
        self._circle_size_label.setVisible(circle)

    def _sync_arena_sliders_from_model(self) -> None:
        self._arena_shape.blockSignals(True)
        self._rect_x.blockSignals(True)
        self._rect_y.blockSignals(True)
        self._rect_w.blockSignals(True)
        self._rect_h.blockSignals(True)
        self._circle_size.blockSignals(True)
        idx = self._arena_shape.findData(self._arena.shape)
        if idx >= 0:
            self._arena_shape.setCurrentIndex(idx)
        circle = self._arena.shape == "circle"
        self._show_circle_arena_controls(circle)
        if circle:
            self._circle_size.setValue(int(self._arena.size * 100))
        else:
            self._rect_x.setValue(int(round(self._arena.rect_x * 100)))
            self._rect_y.setValue(int(round(self._arena.rect_y * 100)))
            self._rect_w.setValue(int(round(self._arena.rect_w * 100)))
            self._rect_h.setValue(int(round(self._arena.rect_h * 100)))
        self._arena_shape.blockSignals(False)
        self._rect_x.blockSignals(False)
        self._rect_y.blockSignals(False)
        self._rect_w.blockSignals(False)
        self._rect_h.blockSignals(False)
        self._circle_size.blockSignals(False)

    def _apply_arena_from_sliders(self) -> None:
        shape = str(self._arena_shape.currentData() or "square")
        self._arena.shape = "circle" if shape == "circle" else "square"
        if self._arena.shape == "circle":
            self._arena.size = self._circle_size.value() / 100.0
        else:
            self._arena.rect_x = self._rect_x.value() / 100.0
            self._arena.rect_y = self._rect_y.value() / 100.0
            self._arena.rect_w = self._rect_w.value() / 100.0
            self._arena.rect_h = self._rect_h.value() / 100.0
            self._arena.uses_rect = True
            self._arena.clamp_rectangle()

    def _on_arena_shape_changed(self, _index: int) -> None:
        self._invalidate_arena_confirmation()
        self._apply_arena_from_sliders()
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()

    def _arena_is_confirmed(self) -> bool:
        return bool(self._arena.confirmed)

    def _invalidate_arena_confirmation(self) -> None:
        if not self._arena.confirmed:
            return
        self._arena.confirmed = False
        self._invalidate_blob_cache()
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()

    def _update_arena_blob_ui_state(self) -> None:
        confirmed = self._arena_is_confirmed()
        self._confirm_arena_btn.setVisible(not confirmed)
        self._edit_arena_btn.setVisible(confirmed)
        for w in (
            self._arena_shape,
            self._rect_x,
            self._rect_y,
            self._rect_w,
            self._rect_h,
            self._circle_size,
            self._confirm_arena_btn,
        ):
            w.setEnabled(not confirmed)
        if self._setup_preview is not None:
            self._setup_preview.set_arena_editable(not confirmed)
        self._blob_box.setEnabled(confirmed)
        self._save_setup_btn.setEnabled(confirmed)
        self._scan_btn.setEnabled(confirmed)
        self._blob_locked_hint.setVisible(not confirmed)
        for w in (
            self._bright_min,
            self._bright_max,
            self._blob_padding_px,
            self._crop_padding_px,
            self._auto_thresh_btn,
        ):
            w.setEnabled(confirmed)

    def _apply_preview_modes(self, *, refresh_frame: bool = False) -> None:
        if not self._ui_ready or self._setup_preview is None:
            return
        confirmed = self._arena_is_confirmed()
        for preview in self._iter_previews():
            preview.set_blob_enabled(confirmed)
        self._preview.set_dim_outside_arena(False)
        self._setup_preview.set_dim_outside_arena(not confirmed)
        if confirmed:
            for preview in self._iter_previews():
                preview.set_blob_params(self._blob_params)
        if refresh_frame:
            self._refresh_current_frame()

    def _sync_arena_to_previews(self) -> None:
        """Update arena overlay on the current frame — no video re-read."""
        if not self._ui_ready or self._setup_preview is None:
            return
        for preview in self._iter_previews():
            preview.set_arena(self._arena)

    def _refresh_current_frame(self) -> None:
        if self._reader is not None and self._reader.is_opened():
            self._show_frame(self._scrubber.frame_index())

    def _on_confirm_arena(self) -> None:
        if not self._current_video_id or self._session is None:
            QMessageBox.warning(self, "Pose Studio", "Select a video first.")
            return
        self._arena.confirmed = True
        vdir = self._video_dir(self._current_video_id)
        save_arena(vdir / "arena.json", self._arena)
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._sync_label_tab()
        self._schedule_blob_cache_build()
        self._label_widget.start_pose_fingerprint_scan_if_needed()
        QMessageBox.information(
            self,
            "Pose Studio",
            "Arena confirmed. Adjust blob brightness, then save blob settings.",
        )

    def _on_edit_arena(self) -> None:
        self._arena.confirmed = False
        self._invalidate_blob_cache()
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._sync_label_tab()

    def _on_tab_changed(self, index: int) -> None:
        on_label = index == self._label_tab_index and self._arena_is_confirmed()
        self._label_widget.set_diverse_scan_allowed(on_label)
        if (
            index == self._setup_tab_index
            and self._reader is not None
            and self._reader.is_opened()
        ):
            self._show_frame(self._scrubber.frame_index())

    @staticmethod
    def _help_text() -> str:
        return (
            "Upload dish videos, set arena and blob, then label keypoints on the "
            "square fish crop (one bodypart across frames). Export DLC CSV when ready. "
            "Use the Train tab after labeling (DLC 3 PyTorch subprocess)."
        )

    def set_ui_preferences(self, prefs: UiPreferences) -> None:
        self._ui_prefs = prefs
        self._train_widget.set_dlc_python(getattr(prefs, "dlc_python_path", "") or "")
        self._label_widget.set_ui_preferences(prefs)

    def on_panel_shown(self) -> None:
        """Open the active video only after Pose Studio becomes visible."""
        self._panel_visible = True
        if not self._needs_video_open or not self._current_video_id or self._session is None:
            return
        self._show_pose_loading()
        QTimer.singleShot(0, self._deferred_prepare_playback)

    def _deferred_prepare_playback(self) -> None:
        if (
            not self._panel_visible
            or not self._needs_video_open
            or not self._current_video_id
            or self._session is None
        ):
            self._hide_pose_loading()
            return
        self._prepare_playback(self._video_dir(self._current_video_id))
        if self._migrate_worker is None or not self._migrate_worker.isRunning():
            self._hide_pose_loading()

    def _stop_panel_workers(self) -> None:
        for worker in (
            self._register_worker,
            self._blob_worker,
            self._migrate_worker,
            self._blob_cache_worker,
        ):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
        self._label_widget.stop_background_work()

    def _reset_panel_for_session(self) -> None:
        """Clear previews, label state, and workers before binding a new session."""
        self._stop_panel_workers()
        self._clear_busy()
        self._release_reader()
        self._current_video_id = None
        self._needs_video_open = False
        self._arena = ArenaConfig()
        self._blob_params = BlobParams()
        self._scrubber.stop_playback()
        self._scrubber.set_flagged_frames(set())
        self._scrubber.set_frame_count(1)
        self._scrubber.set_frame(0)
        for preview in self._iter_previews():
            preview.clear_frame()
            preview.set_arena(self._arena)
            preview.set_blob_params(self._blob_params)
        self._label_widget.reset_for_new_session()
        self._invalidate_blob_cache()
        self._sync_arena_sliders_from_model()
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._video_combo.blockSignals(True)
        self._video_combo.clear()
        self._video_combo.blockSignals(False)
        self._tabs.setCurrentIndex(0)

    def load_session(self, session: Session | None) -> None:
        self._reset_panel_for_session()
        self._session = session
        self._panel_visible = False
        self._refresh_video_list(defer_video=True)
        if self._session is not None:
            self._train_widget.load_session(self._session, self._project_id())
            self._dataset_widget.load_session(self._session, self._project_id())
        else:
            self._train_widget.load_session(None, "default")
            self._dataset_widget.load_session(None, "default")

    def _project_id(self) -> str:
        assert self._session is not None
        return self._session.ensure_default_pose_project()

    def _video_dir(self, video_id: str) -> Path:
        assert self._session is not None
        return pose_video_dir(self._session.getName(), self._project_id(), video_id)

    def _set_busy(self, msg: str, current: int = -1, total: int = -1) -> None:
        self._busy.setText(msg)
        self._busy.show()
        self._busy_bar.show()
        if total > 0 and current >= 0:
            self._busy_bar.setRange(0, total)
            self._busy_bar.setValue(min(current, total))
            pct = int(round(100.0 * min(current, total) / total))
            self._busy_bar.setFormat(f"%p% ({min(current, total)}/{total})")
        else:
            self._busy_bar.setRange(0, 0)
            self._busy_bar.setFormat("")
        self._upload_btn.setEnabled(False)
        self._scan_btn.setEnabled(False)

    def _clear_busy(self) -> None:
        self._busy.hide()
        self._busy_bar.hide()
        self._busy_bar.setRange(0, 100)
        self._busy_bar.setValue(0)
        self._upload_btn.setEnabled(True)
        self._scan_btn.setEnabled(True)

    def _refresh_video_list(self, *, defer_video: bool = False) -> None:
        self._video_combo.blockSignals(True)
        self._video_combo.clear()
        if self._session is None:
            self._video_combo.blockSignals(False)
            return
        ids = self._session.get_pose_video_ids()
        active = self._session.get_active_pose_video_id()
        proj = self._session.pose_projects.get(self._project_id(), {})
        videos = proj.get("videos") or {}
        for vid in ids:
            name = (videos.get(vid) or {}).get("display_name", vid)
            self._video_combo.addItem(name, vid)
        if active:
            idx = self._video_combo.findData(active)
            if idx >= 0:
                self._video_combo.setCurrentIndex(idx)
        self._video_combo.blockSignals(False)
        if self._video_combo.count() > 0:
            self._on_video_selected(
                self._video_combo.currentIndex(),
                defer_video=defer_video or not self._panel_visible,
            )

    def _resolve_policy(self, paths: list[Path]) -> str:
        pref = self._ui_prefs.video_upload_policy
        large = any(p.stat().st_size >= LARGE_FILE_WARNING_BYTES for p in paths if p.is_file())
        if pref == "always_copy" and not large:
            return "copy"
        if pref == "always_reference" and not large:
            return "reference"
        dlg = VideoUploadDialog(
            self,
            file_count=len(paths),
            large_file=large,
            default_policy=pref,
        )
        if dlg.exec_() != QDialog.Accepted:
            return ""
        if dlg.remember_choice:
            key = "always_copy" if dlg.chosen_policy == "copy" else "always_reference"
            self._ui_prefs.video_upload_policy = key
            save_ui_preferences(self._ui_prefs)
        return dlg.chosen_policy

    def _on_upload(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Pose Studio", "Open a session first.")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select video file(s)",
            "",
            "Video (*.mp4 *.avi *.mov *.mkv);;All files (*)",
        )
        if not files:
            dir_path = QFileDialog.getExistingDirectory(self, "Select video folder")
            if dir_path:
                d = Path(dir_path)
                files = [
                    str(p)
                    for p in sorted(d.iterdir())
                    if p.suffix.lower() in {".mp4", ".avi", ".mov", ".mkv"}
                ]
        if not files:
            return
        paths = [Path(f) for f in files]
        policy = self._resolve_policy(paths)
        if not policy:
            return
        pid = self._project_id()
        items = [(p, policy) for p in paths]
        self._set_busy("Uploading videos…", -1, -1)
        self._register_worker = VideoRegisterWorker(
            self._session.getName(),
            pid,
            items,
            set(self._session.get_pose_video_ids()),
        )
        self._register_worker.progress.connect(self._set_busy)
        self._register_worker.video_registered.connect(self._on_video_registered)
        self._register_worker.finished_ok.connect(self._on_register_done)
        self._register_worker.failed.connect(self._on_worker_failed)
        self._register_worker.start()

    def _on_video_registered(self, video_id: str, display_name: str, meta: dict) -> None:
        assert self._session is not None
        self._session.register_pose_video(video_id, display_name, meta)
        self._session.save()

    def _on_register_done(self) -> None:
        self._clear_busy()
        self._refresh_video_list(defer_video=not self._panel_visible)

    def _on_worker_failed(self, msg: str) -> None:
        self._hide_pose_loading()
        self._clear_busy()
        QMessageBox.critical(self, "Pose Studio", msg)

    def _on_video_selected(self, _index: int, *, defer_video: bool = False) -> None:
        vid = self._video_combo.currentData()
        if not vid or self._session is None:
            return
        self._invalidate_blob_cache()
        self._current_video_id = str(vid)
        self._scrubber.stop_playback()
        self._session.set_active_pose_video(self._current_video_id)
        self._session.save()
        vdir = self._video_dir(self._current_video_id)
        self._arena = load_arena(vdir / "arena.json")
        self._blob_params = load_blob_params(vdir / "blob_params.json")
        self._sync_controls_from_model()
        self._apply_video_metadata(vdir)
        if defer_video or not self._panel_visible:
            self._release_reader()
            for preview in self._iter_previews():
                preview.clear_frame()
            self._needs_video_open = True
        else:
            self._prepare_playback(vdir)
        qc_path = vdir / "blob_qc.json"
        if qc_path.is_file():
            data = json.loads(qc_path.read_text(encoding="utf-8"))
            flagged = {
                int(f["frame_index"])
                for f in data.get("frames", [])
                if f.get("flagged")
            }
            self._scrubber.set_flagged_frames(flagged)
        else:
            self._scrubber.set_flagged_frames(set())
        self._sync_label_tab()
        if self._session is not None:
            self._train_widget.load_session(self._session, self._project_id())
            self._dataset_widget.load_session(self._session, self._project_id())

    def _on_labels_imported(self) -> None:
        self._sync_label_tab()
        if self._session is not None:
            self._dataset_widget.load_session(self._session, self._project_id())

    def _on_tracking_exported(self, csv_path: str) -> None:
        if self._session is None:
            return
        self._session.addCSV(csv_path)
        self._session.save()
        self._dataset_widget.load_session(self._session, self._project_id())

    def _sync_label_tab(self) -> None:
        if not self._current_video_id or self._session is None:
            self._label_widget.reset_for_new_session()
            return
        vdir = self._video_dir(self._current_video_id)
        meta_path = vdir / "meta.json"
        frame_count = 0
        if meta_path.is_file():
            frame_count = int(json.loads(meta_path.read_text(encoding="utf-8")).get("frame_count", 0))
        video_path = resolve_video_source(vdir)
        self._label_widget.set_frame_reader(self._read_frame, frame_count)
        self._label_widget.load_video_context(
            session_name=self._session.getName(),
            project_id=self._project_id(),
            video_id=self._current_video_id,
            arena=self._arena,
            blob_params=self._blob_params,
            frame_count=frame_count,
            video_path=video_path,
            video_dir=vdir,
        )
        if self._tabs.currentIndex() == self._label_tab_index and self._arena_is_confirmed():
            self._label_widget.set_diverse_scan_allowed(True)
        else:
            self._label_widget.set_diverse_scan_allowed(False)

    def _sync_controls_from_model(self) -> None:
        if (
            self._reader is not None
            and self._reader.is_opened()
            and self._arena.is_rectangle()
            and not self._arena.uses_rect
        ):
            frame = self._read_frame(self._scrubber.frame_index())
            if frame is not None:
                fh, fw = frame.shape[:2]
                self._arena.ensure_explicit_rect(fw, fh)
        self._bright_min.blockSignals(True)
        self._bright_max.blockSignals(True)
        self._blob_padding_px.blockSignals(True)
        self._crop_padding_px.blockSignals(True)
        self._sync_arena_sliders_from_model()
        self._bright_min.setValue(self._blob_params.brightness_min)
        self._bright_max.setValue(self._blob_params.brightness_max)
        self._blob_padding_px.setValue(self._blob_params.blob_padding_px)
        self._crop_padding_px.setValue(self._blob_params.crop_padding_px)
        self._bright_min.blockSignals(False)
        self._bright_max.blockSignals(False)
        self._blob_padding_px.blockSignals(False)
        self._crop_padding_px.blockSignals(False)
        for preview in self._iter_previews():
            preview.set_arena(self._arena)
        if self._arena_is_confirmed():
            for preview in self._iter_previews():
                preview.set_blob_params(self._blob_params)
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._sync_label_tab()

    def _apply_video_metadata(self, vdir: Path) -> None:
        meta = read_video_meta(vdir)
        n = meta.frame_count if meta and meta.frame_count > 0 else 1
        self._scrubber.set_frame_count(max(1, n))
        if meta and meta.fps > 0:
            self._scrubber.set_playback_fps(meta.fps)

    def _prepare_playback(self, vdir: Path) -> None:
        src = resolve_video_source(vdir)
        if src is None:
            self._needs_video_open = False
            return
        preferred = vdir / "source.mp4"
        if preferred.is_file() or not needs_transcode(src):
            self._open_video_reader(vdir)
            self._needs_video_open = False
            return
        self._hide_pose_loading()
        self._set_busy("Converting video to H.264 MP4…", 0, -1)
        self._migrate_worker = PlaybackMigrateWorker(vdir)
        self._migrate_worker.progress.connect(self._set_busy)
        self._migrate_worker.finished_ok.connect(self._on_playback_migrate_done)
        self._migrate_worker.failed.connect(self._on_worker_failed)
        self._migrate_worker.start()

    def _on_playback_migrate_done(self, _path: str) -> None:
        self._clear_busy()
        if self._current_video_id and self._session is not None:
            self._open_video_reader(self._video_dir(self._current_video_id))
        self._needs_video_open = False
        self._sync_label_tab()
        self._hide_pose_loading()

    def _open_video_reader(self, vdir: Path) -> None:
        self._release_reader()
        src = resolve_video_source(vdir)
        if src is None:
            return
        self._reader = VideoFrameReader(src)
        if not self._reader.is_opened():
            self._release_reader()
            QMessageBox.warning(self, "Pose Studio", f"Could not open video:\n{src}")
            return
        meta = read_video_meta(vdir)
        n = meta.frame_count if meta and meta.frame_count > 0 else 1
        self._scrubber.set_frame_count(max(1, n))
        self._show_frame(0)
        self._sync_arena_sliders_from_model()
        self._apply_preview_modes()
        if self._tabs.currentIndex() == self._label_tab_index:
            self._label_widget.refresh_display()
        if self._arena_is_confirmed():
            self._schedule_blob_cache_build()
            self._label_widget.start_pose_fingerprint_scan_if_needed()

    def _release_reader(self) -> None:
        if self._reader is not None:
            self._reader.release()
            self._reader = None

    def _read_frame(self, index: int):
        if self._reader is None or not self._reader.is_opened():
            return None
        return self._reader.read(index)

    def _on_scrubber_frame(self, index: int) -> None:
        self._show_frame(index)

    def _on_scrubber_preview(self, index: int) -> None:
        self._pending_scrub_index = index
        if not self._scrub_preview_timer.isActive():
            self._flush_scrub_preview()
            self._scrub_preview_timer.start(33)

    def _flush_scrub_preview(self) -> None:
        if self._pending_scrub_index is None:
            return
        index = self._pending_scrub_index
        self._pending_scrub_index = None
        self._show_frame(index, fast=True)

    def _on_scrubber_playback_started(self) -> None:
        self._cache_hint.hide()
        if self._setup_preview is not None:
            self._setup_preview.set_playback_mode(True)

    def _on_scrubber_playback_stopped(self, index: int) -> None:
        if self._setup_preview is not None:
            self._setup_preview.set_playback_mode(False)
        self._show_frame(index, fast=False)

    def _show_frame(self, index: int, *, fast: bool = False) -> None:
        frame = self._read_frame(index)
        if frame is None:
            return
        playing = self._scrubber.is_playing() and not fast
        entry = self._blob_cache_entry(index) if playing and self._arena_is_confirmed() else None
        if fast:
            playback = False
            update_blob = False
            blob = None
            playback_entry = None
        elif playing:
            playback = True
            update_blob = entry is None
            blob = entry.to_blob_result() if entry is not None else None
            playback_entry = entry
        else:
            playback = False
            update_blob = True
            blob = None
            playback_entry = None
        kwargs = {
            "update_blob": update_blob,
            "blob": blob,
            "playback_entry": playback_entry,
            "playback": playback,
        }
        tab = self._tabs.currentIndex()
        if tab == self._setup_tab_index and self._setup_preview is not None:
            self._setup_preview.set_frame_bgr(frame, **kwargs)
        elif tab == 0:
            self._preview.set_frame_bgr(frame, **kwargs)
        else:
            for preview in self._iter_previews():
                preview.set_frame_bgr(frame, **kwargs)

    def _on_arena_dragged(self, arena: ArenaConfig) -> None:
        if self._arena.confirmed:
            self._arena.confirmed = False
            self._invalidate_blob_cache()
            self._update_arena_blob_ui_state()
            self._apply_preview_modes()
        self._arena = arena
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()

    def _on_arena_controls(self, *_args) -> None:
        self._invalidate_arena_confirmation()
        self._apply_arena_from_sliders()
        self._sync_arena_to_previews()

    def _on_blob_sliders(self, *_args) -> None:
        if not self._ui_ready or self._setup_preview is None:
            return
        if not self._arena_is_confirmed():
            return
        self._blob_params.brightness_min = self._bright_min.value()
        self._blob_params.brightness_max = max(
            self._blob_params.brightness_min + 1,
            self._bright_max.value(),
        )
        self._blob_params.blob_padding_px = self._blob_padding_px.value()
        self._blob_params.crop_padding_px = self._crop_padding_px.value()
        for preview in self._iter_previews():
            preview.set_blob_params(self._blob_params)
        self._label_widget.update_tracking_params(self._arena, self._blob_params)
        self._schedule_blob_cache_build()

    def _invalidate_blob_cache(self) -> None:
        self._blob_cache_debounce.stop()
        if self._blob_cache_worker is not None and self._blob_cache_worker.isRunning():
            self._blob_cache_worker.requestInterruption()
        self._blob_cache_worker = None
        self._blob_playback_cache = None
        self._blob_cache_key = None
        self._blob_cache_frame_count = 0
        self._cache_hint.hide()
        if self._setup_preview is not None:
            self._setup_preview.set_playback_mode(False)

    def _schedule_blob_cache_build(self) -> None:
        if not self._arena_is_confirmed():
            return
        self._blob_cache_debounce.start(600)

    def _blob_cache_entry(self, index: int) -> PlaybackBlobEntry | None:
        if self._blob_playback_cache is None:
            return None
        if index < 0 or index >= len(self._blob_playback_cache):
            return None
        return self._blob_playback_cache[index]

    def _start_blob_cache_build(self) -> None:
        if not self._arena_is_confirmed() or not self._current_video_id or self._session is None:
            return
        vdir = self._video_dir(self._current_video_id)
        src = resolve_video_source(vdir)
        if src is None:
            return
        meta = read_video_meta(vdir)
        frame_count = meta.frame_count if meta and meta.frame_count > 0 else 1
        cache_key = playback_blob_cache_key(self._arena, self._blob_params)
        if (
            self._blob_cache_key == cache_key
            and self._blob_playback_cache is not None
            and len(self._blob_playback_cache) >= frame_count
        ):
            return
        loaded = load_playback_overlay_cache(
            vdir,
            frame_count=frame_count,
            video_path=src,
            arena=self._arena,
            blob_params=self._blob_params,
            preview_max_edge=self.PREVIEW_MAX_EDGE,
        )
        if loaded is not None:
            self._blob_cache_key = cache_key
            self._blob_playback_cache = loaded
            self._blob_cache_frame_count = frame_count
            self._cache_hint.hide()
            return
        if self._blob_cache_worker is not None and self._blob_cache_worker.isRunning():
            self._blob_cache_worker.requestInterruption()
        self._blob_cache_key = cache_key
        self._blob_cache_frame_count = frame_count
        self._blob_playback_cache = None
        self._blob_cache_worker = PlaybackBlobCacheWorker(
            src,
            frame_count,
            self._arena,
            self._blob_params,
            preview_max_edge=self.PREVIEW_MAX_EDGE,
        )
        self._blob_cache_worker.progress.connect(self._on_blob_cache_progress)
        self._blob_cache_worker.finished_ok.connect(self._on_blob_cache_finished)
        self._blob_cache_worker.failed.connect(self._on_blob_cache_failed)
        self._cache_hint.setText("Preparing playback overlays…")
        self._cache_hint.show()
        self._blob_cache_worker.start()

    def _on_blob_cache_progress(self, cur: int, tot: int) -> None:
        if not self._scrubber.is_playing():
            self._cache_hint.setText(f"Preparing playback overlays… {cur}/{tot}")

    def _on_blob_cache_finished(self) -> None:
        worker = self._blob_cache_worker
        if worker is not None and worker.entries:
            self._blob_playback_cache = list(worker.entries)
            if self._current_video_id and self._session is not None:
                vdir = self._video_dir(self._current_video_id)
                src = resolve_video_source(vdir)
                meta = read_video_meta(vdir)
                frame_count = meta.frame_count if meta and meta.frame_count > 0 else len(worker.entries)
                if src is not None:
                    try:
                        save_playback_overlay_cache(
                            vdir,
                            self._blob_playback_cache,
                            frame_count=frame_count,
                            video_path=src,
                            arena=self._arena,
                            blob_params=self._blob_params,
                            preview_max_edge=self.PREVIEW_MAX_EDGE,
                        )
                    except OSError:
                        pass
        if not self._scrubber.is_playing():
            self._cache_hint.hide()

    def _on_blob_cache_failed(self, _msg: str) -> None:
        self._blob_playback_cache = None
        self._cache_hint.hide()

    def _on_auto_threshold(self) -> None:
        if not self._arena_is_confirmed():
            return
        self._set_busy("Computing histogram…")
        frame = self._read_frame(self._scrubber.frame_index())
        if frame is None:
            self._clear_busy()
            QMessageBox.warning(self, "Pose Studio", "Open a video frame first.")
            return
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lo, hi = suggest_brightness_range(gray, self._arena)
        self._bright_min.setValue(lo)
        self._bright_max.setValue(hi)
        self._on_blob_sliders()
        self._clear_busy()

    def _save_video_setup(self) -> None:
        if not self._current_video_id or self._session is None:
            return
        if not self._arena_is_confirmed():
            QMessageBox.warning(self, "Pose Studio", "Confirm the arena before saving blob settings.")
            return
        vdir = self._video_dir(self._current_video_id)
        save_blob_params(vdir / "blob_params.json", self._blob_params)
        self._schedule_blob_cache_build()
        QMessageBox.information(self, "Pose Studio", "Blob settings saved.")

    def _on_blob_scan(self) -> None:
        if not self._current_video_id:
            return
        if not self._arena_is_confirmed():
            QMessageBox.warning(self, "Pose Studio", "Confirm the arena before scanning.")
            return
        vdir = self._video_dir(self._current_video_id)
        if not (vdir / "arena.json").is_file():
            QMessageBox.warning(self, "Pose Studio", "Confirm the arena before scanning.")
            return
        self._set_busy("Scanning video for blob jumps…")
        self._blob_worker = BlobScanWorker(vdir)
        self._blob_worker.progress.connect(self._on_blob_scan_progress)
        self._blob_worker.finished_ok.connect(self._on_scan_done)
        self._blob_worker.failed.connect(self._on_worker_failed)
        self._blob_worker.start()

    def _on_blob_scan_progress(self, cur: int, tot: int) -> None:
        self._set_busy(f"Scanning video for blob jumps… {cur}/{tot}", cur, tot)

    def _on_scan_done(self, _path: str) -> None:
        self._clear_busy()
        if self._current_video_id:
            qc_path = self._video_dir(self._current_video_id) / "blob_qc.json"
            if qc_path.is_file():
                data = json.loads(qc_path.read_text(encoding="utf-8"))
                flagged = {
                    int(f["frame_index"])
                    for f in data.get("frames", [])
                    if f.get("flagged")
                }
                self._scrubber.set_flagged_frames(flagged)
        QMessageBox.information(self, "Pose Studio", "Blob scan complete.")

    def closeEvent(self, event) -> None:
        self._release_reader()
        super().closeEvent(event)
