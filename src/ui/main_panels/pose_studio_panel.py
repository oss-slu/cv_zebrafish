"""Pose Studio — video upload, arena, and blob setup."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
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

from app_platform.paths import (
    ai_labelled_dir,
    pose_video_dir,
    human_labelled_dir,
    custom_labelled_dir,
)
from app_platform.ui_preferences import UiPreferences, save_ui_preferences
from core.pose.detection.arena import (
    MAIN_ARENA_ID,
    ARENA_SIZE_SLIDER_MIN_FRAC,
    ArenaConfig,
    arena_pos_from_slider,
    arena_pos_slider_range,
    arena_pos_to_slider,
    circle_center_bounds,
    circle_size_from_slider,
    circle_size_slider_range,
    circle_size_to_slider,
    clamp_circle_center,
    load_arena,
    make_default_exclusion,
    rect_pos_slider_ranges,
    save_arena,
)
from core.pose.detection.blob import BlobParams, load_blob_params, save_blob_params
from core.pose.detection.blob_qc import (
    load_blob_qc,
    next_mismatch_frame,
)
from core.pose.detection.histogram import suggest_blob_selection_values
from core.pose.cache.playback_blob_cache import (
    PlaybackBlobEntry,
    load_playback_overlay_cache,
    playback_blob_cache_key,
)
from core.pose.video.video_reader import VideoFrameReader
from core.pose.video.video_registry import (
    LARGE_FILE_WARNING_BYTES,
    clear_video_runtime_caches,
    probe_video,
    read_video_meta,
    remove_video_source_files,
    resolve_video_source,
)
from core.pose.inference.heatmap_store import delete_heatmap_archive, list_heatmap_archives
from core.pose.labeling.labels_store import LabelDataset, load_labels
from core.pose.labeling.named_label_sets import (
    delete_custom_set,
    list_custom_sets,
    load_dataset_from_dir,
    save_named_set,
    slugify_dataset_name,
)
from core.pose.labeling.schema import canonical_lab_schema
from core.pose.video.video_transcode import needs_transcode
from session.session import Session
from ui.components.pose.frame_scrubber import FrameScrubber
from ui.components.pose.pose_preview_widget import PosePreviewWidget
from ui.components.widgets.scene_help import create_scene_help_button
from ui.main_panels.pose_label_widget import PoseLabelWidget
from ui.main_panels.pose_auto_label_widget import PoseAutoLabelWidget
from ui.main_panels.pose_train_widget import PoseTrainWidget
from ui.pose_studio.chrome import brief_busy_scope
from ui.pose_studio.scenes import (
    AutoLabelScene,
    LabelScene,
    ModelScene,
    VideoScene,
)
from ui.popup_panels.video_upload_dialog import VideoUploadDialog
from ui.components.widgets.loading_overlay import LoadingOverlay
from ui.workers.blob_scan_worker import BlobScanWorker
from ui.workers.mismatch_detect_worker import MismatchDetectWorker
from ui.workers.playback_migrate_worker import PlaybackMigrateWorker
from ui.workers.playback_blob_cache_worker import PlaybackBlobCacheWorker
from ui.workers.video_open_worker import VideoOpenWorker
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
        self._mismatch_worker: MismatchDetectWorker | None = None
        self._mismatch_detect_gen = 0
        self._migrate_worker: PlaybackMigrateWorker | None = None
        self._blob_cache_worker: PlaybackBlobCacheWorker | None = None
        self._video_open_worker: VideoOpenWorker | None = None
        self._video_open_gen = 0
        self._video_switch_gen = 0
        self._pending_video_open_dir: Path | None = None
        self._blob_playback_cache: list[PlaybackBlobEntry] | None = None
        self._blob_cache_key: str | None = None
        self._blob_cache_frame_count = 0
        self._blob_cache_build_pending = False
        self._video_progress_message = "Loading playback overlays…"
        self._pending_label_crop_remap = False
        self._settings_dirty = False
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
        self._pending_scrub_settle_index: int | None = None
        self._scrub_preview_timer = QTimer(self)
        self._scrub_preview_timer.setSingleShot(True)
        self._scrub_preview_timer.timeout.connect(self._flush_scrub_preview)
        # Apply settled overlays after the pointer is fully up (not mid-drag release race).
        self._scrub_settle_timer = QTimer(self)
        self._scrub_settle_timer.setSingleShot(True)
        self._scrub_settle_timer.timeout.connect(self._flush_scrub_settle)
        self._blob_cache_debounce = QTimer(self)
        self._blob_cache_debounce.setSingleShot(True)
        self._blob_cache_debounce.timeout.connect(self._start_blob_cache_build)
        self._setup_tab_index = 1  # overwritten when Video tab is added
        self._reader_open_pending = False
        self._active_label_set_id = "human"
        self._active_arena_region_id = MAIN_ARENA_ID
        self._crop_setup_skipped = False

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
        self._tabs.setObjectName("PoseStudioTabWidget")
        root.addWidget(self._tabs, stretch=1)

        # --- Overhaul scenes: Video → Label → Model → Auto Label ---
        self._video_scene = VideoScene()
        self._video_scene.upload_video_requested.connect(self._on_upload)
        self._video_scene.upload_prelabeled_requested.connect(self._on_upload_prelabeled)
        self._video_scene.upload_analysis_requested.connect(self._on_upload_analysis)
        self._video_scene.update_all_frames_requested.connect(self._on_update_all_frames)
        self._video_scene.detect_mismatch_requested.connect(self._on_detect_next_mismatch)
        self._video_scene.suggest_values_requested.connect(self._on_auto_threshold)
        self._video_scene.skip_requested.connect(self._on_video_skip)
        self._video_scene.delete_video_requested.connect(self._on_delete_video)
        self._video_scene.delete_video_and_heatmaps_requested.connect(
            self._on_delete_video_and_heatmaps
        )
        self._video_scene.arena_changed.connect(self._on_arena_controls)
        self._video_scene.selection_changed.connect(self._on_blob_sliders)
        self._video_scene.exclude_mode_toggled.connect(self._on_exclude_mode_toggled)
        self._video_scene.arena_region_selected.connect(self._on_arena_region_selected)
        self._video_scene.exclusion_added.connect(self._on_exclusion_added)
        self._video_scene.exclusion_removed.connect(self._on_exclusion_removed)

        # Alias legacy control names onto VideoScene widgets
        self._upload_btn = self._video_scene.upload_btn
        self._video_combo = self._video_scene.video_combo
        self._video_combo.currentIndexChanged.connect(self._on_video_selected)
        self._arena_shape = self._video_scene.arena_shape
        self._rect_x = self._video_scene.x_pos
        self._rect_y = self._video_scene.y_pos
        self._rect_w = self._video_scene.x_size
        self._rect_h = self._video_scene.y_size
        self._circle_size = self._video_scene.diameter
        self._rect_w_label = self._video_scene._x_size_lbl
        self._rect_h_label = self._video_scene._y_size_lbl
        self._circle_size_label = self._video_scene._diameter_lbl
        self._bright_min = self._video_scene.bright_min
        self._bright_max = self._video_scene.bright_max
        self._blob_padding_px = self._video_scene.blob_padding
        self._crop_padding_px = self._video_scene.crop_padding
        self._auto_thresh_btn = self._video_scene.suggest_btn
        self._save_setup_btn = self._video_scene.update_all_btn
        self._scan_btn = self._video_scene.detect_btn
        self._confirm_arena_btn = QPushButton("Confirm arena")
        self._confirm_arena_btn.hide()
        self._edit_arena_btn = QPushButton("Edit arena…")
        self._edit_arena_btn.hide()
        self._blob_locked_hint = QLabel("")
        self._blob_locked_hint.hide()
        self._blob_box = self._video_scene.shell.side_host

        self._preview = PosePreviewWidget()
        self._preview.set_preview_max_edge(self.PREVIEW_MAX_EDGE)
        self._setup_preview = PosePreviewWidget()
        self._setup_preview.set_preview_max_edge(self.PREVIEW_MAX_EDGE)
        self._setup_preview.set_arena_editable(True)
        self._setup_preview.arena_changed.connect(self._on_arena_dragged)
        self._video_scene.preview_layout.addWidget(self._setup_preview, stretch=1)

        self._scrubber = FrameScrubber()
        self._scrubber.frame_changed.connect(self._on_scrubber_frame)
        self._scrubber.frame_preview.connect(self._on_scrubber_preview)
        self._scrubber.playback_stopped.connect(self._on_scrubber_playback_stopped)
        self._scrubber.playback_started.connect(self._on_scrubber_playback_started)
        self._video_scene.timeline_layout.addWidget(self._scrubber)
        self._cache_hint = QLabel("")
        self._cache_hint.setObjectName("SettingsHintLabel")
        self._cache_hint.hide()
        self._video_scene.timeline_layout.addWidget(self._cache_hint)

        self._tabs.addTab(self._video_scene, "Video")
        self._setup_tab_index = self._tabs.indexOf(self._video_scene)

        self._label_scene = LabelScene()
        self._label_widget = PoseLabelWidget()
        self._label_widget.tracking_exported.connect(self._on_tracking_exported)
        self._label_widget.background_work_finished.connect(self._sync_pose_loading_overlay)
        self._label_widget.labels_changed.connect(self._refresh_label_set_combo)
        self._label_widget.labels_changed.connect(self._sync_context_bar)
        self._label_scene.set_content_widget(self._label_widget)
        self._label_widget.attach_label_chrome(self._label_scene)
        self._tabs.addTab(self._label_scene, "Label")

        self._model_scene = ModelScene()
        self._train_widget = PoseTrainWidget(self)
        self._train_widget.labels_imported.connect(self._on_labels_imported)
        if hasattr(self._train_widget, "model_selection_changed"):
            self._train_widget.model_selection_changed.connect(self._sync_context_bar)
            self._train_widget.model_selection_changed.connect(self._sync_auto_label_tab)
        self._train_widget.attach_to_model_scene(self._model_scene)
        self._tabs.addTab(self._model_scene, "Model")

        self._auto_label_scene = AutoLabelScene()
        self._auto_label_widget = PoseAutoLabelWidget()
        self._auto_label_widget.labels_exported.connect(self._on_auto_label_exported)
        self._auto_label_scene.set_content_widget(self._auto_label_widget)
        self._auto_label_scene.view_output_requested.connect(self._on_view_auto_label_output)
        self._auto_label_scene.run_requested.connect(self._on_auto_label_run_proxy)
        self._auto_label_scene.video_changed.connect(self._on_auto_scene_video_changed)
        self._auto_label_scene.model_changed.connect(self._on_auto_scene_model_changed)
        self._tabs.addTab(self._auto_label_scene, "Auto Label")

        self._label_scene.prev_requested.connect(self._label_widget._controller.go_prev_frame)
        self._label_scene.next_requested.connect(self._label_widget._controller.go_next_frame)
        self._label_scene.undo_requested.connect(self._label_widget._controller.undo)
        self._label_scene.redo_requested.connect(self._label_widget._controller.redo)
        self._label_scene.auto_toggled.connect(self._label_widget._controller.set_auto_advance_frames)
        self._label_scene.create_label_set_requested.connect(self._on_create_label_set)
        self._label_scene.label_set_changed.connect(self._on_label_set_changed)
        self._label_scene.label_set_remove_requested.connect(self._on_remove_label_set)
        self._label_scene.review_mode_changed.connect(self._on_label_review_mode_changed)
        self._label_scene.prev_outlier_requested.connect(
            lambda: self._label_widget.jump_outlier(-1)
        )
        self._label_scene.next_outlier_requested.connect(
            lambda: self._label_widget.jump_outlier(1)
        )

        # Model scene owns side + main chrome; train widget is the controller.

        self._label_tab_index = self._tabs.indexOf(self._label_scene)
        self._verify_labels_tab_index = -1
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._bind_arena_blob_signals()
        self._sync_arena_sliders_from_model()
        self._sync_arena_region_ui()
        self._update_arena_blob_ui_state()
        self._ui_ready = True

        self._loading_overlay = LoadingOverlay(self, title="Loading Pose Studio")
        self._loading_overlay.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_loading_overlay"):
            self._loading_overlay.resize_to_parent()

    def _is_pose_background_loading(self) -> bool:
        """True when the full-panel loading overlay should block the UI.

        Blob-cache rebuild is excluded — Video tab shows an in-panel progress bar
        and only the timeline stays locked until that job finishes.
        """
        if self._needs_video_open:
            return True
        if self._reader_open_pending:
            return True
        if self._video_open_worker is not None and self._video_open_worker.isRunning():
            return True
        if self._migrate_worker is not None and self._migrate_worker.isRunning():
            return True
        if self._label_widget.is_background_work_running():
            return True
        return False

    def _blob_cache_busy(self) -> bool:
        return bool(
            self._blob_cache_build_pending
            or (
                self._blob_cache_worker is not None
                and self._blob_cache_worker.isRunning()
            )
        )

    def _show_pose_loading(self, message: str = "Loading Pose Studio") -> None:
        self._loading_overlay.set_message(message)
        self._loading_overlay.set_indeterminate(True)
        self._loading_overlay.show_loading()
        self._tabs.setEnabled(False)

    def _hide_pose_loading(self) -> None:
        self._loading_overlay.hide_loading()
        self._tabs.setEnabled(True)

    def _sync_pose_loading_overlay(self) -> None:
        if not self._panel_visible:
            self._hide_pose_loading()
            self._sync_playback_lock()
            return
        if self._is_pose_background_loading():
            if not self._loading_overlay.isVisible():
                self._show_pose_loading()
        else:
            self._hide_pose_loading()
        # Re-evaluate scrub/play whenever background work state changes.
        self._sync_playback_lock()

    def _bind_arena_blob_signals(self) -> None:
        """Wire arena shape changes after every preview widget exists.

        Slider moves are handled via VideoScene.arena_changed / selection_changed
        to avoid double-firing.
        """
        self._arena_shape.currentIndexChanged.connect(self._on_arena_shape_changed)

    def _iter_previews(self):
        yield self._preview
        if self._setup_preview is not None:
            yield self._setup_preview

    def _show_circle_arena_controls(self, circle: bool) -> None:
        """Delegate visibility to VideoScene (X/Y Pos always shown)."""
        del circle
        if hasattr(self, "_video_scene"):
            self._video_scene._sync_arena_shape_visibility()

    def _arena_frame_size(self) -> tuple[int, int]:
        """Full-resolution video dimensions for arena slider math (never preview scale)."""
        if self._reader is not None and self._reader.is_opened():
            frame = self._read_frame(self._scrubber.frame_index())
            if frame is not None:
                h, w = frame.shape[:2]
                if w > 0 and h > 0:
                    return w, h
        if self._setup_preview is not None and self._setup_preview._frame_bgr_source is not None:
            h, w = self._setup_preview._frame_bgr_source.shape[:2]
            if w > 0 and h > 0:
                return w, h
        if self._current_video_id and self._session is not None:
            meta = read_video_meta(self._video_dir(self._current_video_id))
            if meta is not None and meta.width > 0 and meta.height > 0:
                return meta.width, meta.height
        return 0, 0

    def _clamp_arena_config(self, cfg: ArenaConfig, fw: int, fh: int) -> None:
        if fw <= 0 or fh <= 0:
            return
        if cfg.shape == "circle":
            cfg.size = min(1.0, max(ARENA_SIZE_SLIDER_MIN_FRAC, float(cfg.size)))
            cfg.center_x, cfg.center_y = clamp_circle_center(
                cfg.center_x,
                cfg.center_y,
                cfg.size,
                fw,
                fh,
            )
            cfg.uses_rect = False
        else:
            cfg.clamp_rectangle()

    def _clamp_arena_geometry(self) -> None:
        fw, fh = self._arena_frame_size()
        if fw <= 0 or fh <= 0:
            return
        self._clamp_arena_config(self._arena, fw, fh)
        for exclusion in self._arena.exclusions:
            inner = exclusion.to_arena_config()
            self._clamp_arena_config(inner, fw, fh)
            exclusion.apply_from_arena_config(inner)

    def _sync_arena_slider_ranges(self, *, size: float | None = None) -> None:
        fw, fh = self._arena_frame_size()
        circle = str(self._arena_shape.currentData() or "square") == "circle"
        if not circle:
            (x_lo, x_hi), (y_lo, y_hi) = rect_pos_slider_ranges(fw, fh)
            self._rect_x.setRange(x_lo, x_hi)
            self._rect_y.setRange(y_lo, y_hi)
            return
        if size is None:
            size = circle_size_from_slider(self._circle_size.value(), fw, fh)
        min_x, max_x, min_y, max_y = circle_center_bounds(size, fw, fh)
        x_lo, x_hi = arena_pos_slider_range(min_x, max_x, fw)
        y_lo, y_hi = arena_pos_slider_range(min_y, max_y, fh)
        self._rect_x.setRange(x_lo, x_hi)
        self._rect_y.setRange(y_lo, y_hi)
        d_lo, d_hi = circle_size_slider_range(fw, fh)
        self._circle_size.setRange(d_lo, d_hi)

    def _sync_arena_sliders_from_model(self) -> None:
        self._clamp_arena_geometry()
        cfg = self._editing_region_cfg()
        fw, fh = self._arena_frame_size()
        self._arena_shape.blockSignals(True)
        self._rect_x.blockSignals(True)
        self._rect_y.blockSignals(True)
        self._rect_w.blockSignals(True)
        self._rect_h.blockSignals(True)
        self._circle_size.blockSignals(True)
        idx = self._arena_shape.findData(cfg.shape)
        if idx >= 0:
            self._arena_shape.setCurrentIndex(idx)
        circle = cfg.shape == "circle"
        self._show_circle_arena_controls(circle)
        if circle:
            self._sync_arena_slider_ranges(size=cfg.size)
            self._circle_size.setValue(circle_size_to_slider(cfg.size, fw, fh))
            self._rect_x.setValue(arena_pos_to_slider(cfg.center_x, fw))
            self._rect_y.setValue(arena_pos_to_slider(cfg.center_y, fh))
        else:
            self._sync_arena_slider_ranges()
            self._rect_x.setValue(arena_pos_to_slider(cfg.rect_x, fw))
            self._rect_y.setValue(arena_pos_to_slider(cfg.rect_y, fh))
            self._rect_w.setValue(int(round(cfg.rect_w * 100)))
            self._rect_h.setValue(int(round(cfg.rect_h * 100)))
        self._arena_shape.blockSignals(False)
        self._rect_x.blockSignals(False)
        self._rect_y.blockSignals(False)
        self._rect_w.blockSignals(False)
        self._rect_h.blockSignals(False)
        self._circle_size.blockSignals(False)

    def _apply_arena_from_sliders(self) -> None:
        shape = str(self._arena_shape.currentData() or "square")
        fw, fh = self._arena_frame_size()
        values = ArenaConfig()
        values.shape = "circle" if shape == "circle" else "square"
        if values.shape == "circle":
            values.size = circle_size_from_slider(self._circle_size.value(), fw, fh)
            values.center_x = arena_pos_from_slider(self._rect_x.value(), fw)
            values.center_y = arena_pos_from_slider(self._rect_y.value(), fh)
            values.uses_rect = False
            values.center_x, values.center_y = clamp_circle_center(
                values.center_x,
                values.center_y,
                values.size,
                fw,
                fh,
            )
        else:
            values.rect_x = arena_pos_from_slider(self._rect_x.value(), fw)
            values.rect_y = arena_pos_from_slider(self._rect_y.value(), fh)
            values.rect_w = self._rect_w.value() / 100.0
            values.rect_h = self._rect_h.value() / 100.0
            values.uses_rect = True
            values.clamp_rectangle()
        if self._active_arena_region_id == MAIN_ARENA_ID:
            self._arena.shape = values.shape
            if values.shape == "circle":
                self._arena.size = values.size
                self._arena.center_x = values.center_x
                self._arena.center_y = values.center_y
                self._arena.uses_rect = False
            else:
                self._arena.rect_x = values.rect_x
                self._arena.rect_y = values.rect_y
                self._arena.rect_w = values.rect_w
                self._arena.rect_h = values.rect_h
                self._arena.uses_rect = True
                self._arena.clamp_rectangle()
        else:
            for ex in self._arena.exclusions:
                if ex.id == self._active_arena_region_id:
                    ex.apply_from_arena_config(values)
                    break

    def _on_arena_shape_changed(self, _index: int) -> None:
        self._invalidate_arena_confirmation()
        self._apply_arena_from_sliders()
        self._sync_arena_sliders_from_model()
        self._sync_arena_region_ui()
        self._sync_arena_to_previews()
        if self._setup_preview is not None:
            self._setup_preview.set_blob_enabled(True)
            self._setup_preview.set_blob_params(self._blob_params)
        self._refresh_current_frame()
        self._sync_playback_lock()

    def _arena_is_confirmed(self) -> bool:
        return bool(self._arena.confirmed)

    def _label_workflow_ready(self) -> bool:
        return self._arena_is_confirmed() or self._crop_setup_skipped

    def _editing_region_cfg(self) -> ArenaConfig:
        if self._active_arena_region_id == MAIN_ARENA_ID:
            return self._arena
        for ex in self._arena.exclusions:
            if ex.id == self._active_arena_region_id:
                return ex.to_arena_config()
        return self._arena

    def _sync_arena_region_ui(self) -> None:
        if not hasattr(self, "_video_scene"):
            return
        self._video_scene.set_exclude_mode(self._arena.exclude_mode)
        self._video_scene.set_arena_regions(
            self._arena.exclusions,
            active_id=self._active_arena_region_id,
        )
        for preview in self._iter_previews():
            preview.set_active_arena_region(self._active_arena_region_id)

    def _on_exclude_mode_toggled(self, enabled: bool) -> None:
        self._mark_setup_settings_dirty()
        self._arena.exclude_mode = bool(enabled)
        if not enabled:
            self._active_arena_region_id = MAIN_ARENA_ID
        self._sync_arena_region_ui()
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()
        self._refresh_current_frame()

    def _on_arena_region_selected(self, region_id: str) -> None:
        self._active_arena_region_id = region_id or MAIN_ARENA_ID
        self._sync_arena_region_ui()
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()

    def _on_exclusion_added(self) -> None:
        self._mark_setup_settings_dirty()
        exclusion = make_default_exclusion(self._arena.exclusions)
        self._arena.exclusions.append(exclusion)
        self._arena.exclude_mode = True
        self._active_arena_region_id = exclusion.id
        self._sync_arena_region_ui()
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()
        self._refresh_current_frame()

    def _on_exclusion_removed(self, region_id: str) -> None:
        self._mark_setup_settings_dirty()
        self._arena.exclusions = [
            ex for ex in self._arena.exclusions if ex.id != region_id
        ]
        if self._active_arena_region_id == region_id:
            self._active_arena_region_id = MAIN_ARENA_ID
        if not self._arena.exclusions:
            self._arena.exclude_mode = False
        self._sync_arena_region_ui()
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()
        self._refresh_current_frame()

    def _mark_setup_settings_dirty(self) -> None:
        """User edited Arena/Selection; scrubbing uses bare-during-drag until Update."""
        was_confirmed = self._arena.confirmed
        self._settings_dirty = True
        if was_confirmed:
            self._arena.confirmed = False
            self._invalidate_blob_cache()
            self._update_arena_blob_ui_state()
            self._apply_preview_modes()
        self._sync_playback_lock()

    def _invalidate_arena_confirmation(self) -> None:
        self._mark_setup_settings_dirty()

    def _clear_setup_settings_dirty(self) -> None:
        self._settings_dirty = False

    def _update_arena_blob_ui_state(self) -> None:
        # Overhaul: arena + selection stay editable; Update-for-all commits cache.
        confirmed = self._arena_is_confirmed()
        self._confirm_arena_btn.hide()
        self._edit_arena_btn.hide()
        self._blob_locked_hint.hide()
        for w in (
            self._arena_shape,
            self._rect_x,
            self._rect_y,
            self._rect_w,
            self._rect_h,
            self._circle_size,
            self._bright_min,
            self._bright_max,
            self._blob_padding_px,
            self._crop_padding_px,
            self._auto_thresh_btn,
            self._save_setup_btn,
            self._scan_btn,
        ):
            w.setEnabled(True)
        if self._setup_preview is not None:
            self._setup_preview.set_arena_editable(True)
        if hasattr(self, "_video_scene"):
            self._video_scene.set_update_all_highlighted(not confirmed)
        if hasattr(self, "_scrubber"):
            self._sync_playback_lock()

    def _apply_preview_modes(self, *, refresh_frame: bool = False) -> None:
        if not self._ui_ready or self._setup_preview is None:
            return
        confirmed = self._arena_is_confirmed()
        # Setup preview always shows live blob/crop for the current frame.
        self._setup_preview.set_blob_enabled(True)
        self._setup_preview.set_blob_params(self._blob_params)
        self._setup_preview.set_dim_outside_arena(not confirmed)
        self._preview.set_blob_enabled(confirmed)
        self._preview.set_dim_outside_arena(False)
        if confirmed:
            self._preview.set_blob_params(self._blob_params)
        if refresh_frame:
            self._refresh_current_frame()

    def _sync_arena_to_previews(self) -> None:
        """Update arena overlay on the current frame — no video re-read."""
        if not self._ui_ready or self._setup_preview is None:
            return
        for preview in self._iter_previews():
            preview.set_arena(self._arena)
            preview.set_active_arena_region(self._active_arena_region_id)

    def _refresh_current_frame(self) -> None:
        if self._reader is not None and self._reader.is_opened():
            self._show_frame(self._scrubber.frame_index())

    def _on_confirm_arena(self) -> None:
        if not self._current_video_id or self._session is None:
            QMessageBox.warning(self, "Pose Studio", "Select a video first.")
            return
        self._arena.confirmed = True
        self._clear_setup_settings_dirty()
        vdir = self._video_dir(self._current_video_id)
        save_arena(vdir / "arena.json", self._arena)
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._sync_label_tab()
        self._sync_verify_labels_tab()
        self._schedule_blob_cache_build()
        self._label_widget.start_pose_fingerprint_scan_if_needed()
        QMessageBox.information(
            self,
            "Pose Studio",
            "Arena confirmed. Adjust blob brightness, then save blob settings.",
        )

    def _on_edit_arena(self) -> None:
        self._mark_setup_settings_dirty()
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._sync_label_tab()
        self._sync_verify_labels_tab()

    def _on_tab_changed(self, index: int) -> None:
        on_label = index == self._label_tab_index and self._label_workflow_ready()
        self._label_widget.set_diverse_scan_allowed(on_label)
        if (
            index == self._setup_tab_index
            and self._reader is not None
            and self._reader.is_opened()
        ):
            self._show_frame(self._scrubber.frame_index())
        self._sync_context_bar_active_key(index)
        # Tab pages often layout at width 0 while hidden; re-fit side stretch on every tab.
        page = self._tabs.widget(index)
        shell = getattr(page, "shell", None)
        if shell is not None and hasattr(shell, "fit_side_to_content"):
            shell._sizes_applied = False
            QTimer.singleShot(0, lambda s=shell: s.fit_side_to_content())
            QTimer.singleShot(50, lambda s=shell: s.fit_side_to_content())

    @staticmethod
    def _help_text() -> str:
        return (
            "Upload dish videos, set arena and blob, then label keypoints on the "
            "square fish crop (one bodypart across frames). Export DLC CSV when ready. "
            "Use the Model tab after labeling (DLC 3 PyTorch subprocess), then Auto Label "
            "to propagate from your human seed frame with blob-masked heatmap search. "
            "Review and edit results on the Label tab."
        )

    def set_ui_preferences(self, prefs: UiPreferences) -> None:
        self._ui_prefs = prefs
        self._train_widget.set_dlc_python(getattr(prefs, "dlc_python_path", "") or "")
        self._auto_label_widget.set_dlc_python(getattr(prefs, "dlc_python_path", "") or "")
        self._label_widget.set_ui_preferences(prefs)

    def on_panel_shown(self) -> None:
        """Open the active video only after Pose Studio becomes visible."""
        self._panel_visible = True
        if not self._current_video_id or self._session is None:
            return
        self._show_pose_loading()
        if self._needs_video_open:
            QTimer.singleShot(0, self._deferred_prepare_playback)
            return
        self._sync_pose_loading_overlay()

    def _deferred_prepare_playback(self) -> None:
        if (
            not self._panel_visible
            or not self._needs_video_open
            or not self._current_video_id
            or self._session is None
        ):
            self._sync_pose_loading_overlay()
            return
        self._prepare_playback(self._video_dir(self._current_video_id))
        self._sync_pose_loading_overlay()

    def _stop_panel_workers(self) -> None:
        self._mismatch_detect_gen += 1
        for worker in (
            self._register_worker,
            self._blob_worker,
            self._mismatch_worker,
            self._migrate_worker,
            self._blob_cache_worker,
            self._video_open_worker,
        ):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
        self._label_widget.stop_background_work()
        self._hide_blob_cache_progress()
        if hasattr(self, "_scan_btn"):
            self._scan_btn.setEnabled(True)

    def _reset_panel_for_session(self) -> None:
        """Clear previews, label state, and workers before binding a new session."""
        self._stop_panel_workers()
        self._clear_busy()
        self._hide_pose_loading()
        self._release_reader()
        self._current_video_id = None
        self._active_label_set_id = "human"
        self._active_arena_region_id = MAIN_ARENA_ID
        self._crop_setup_skipped = False
        self._needs_video_open = False
        self._arena = ArenaConfig()
        self._blob_params = BlobParams()
        self._clear_setup_settings_dirty()
        self._scrubber.stop_playback()
        self._scrubber.set_flagged_frames(set())
        self._scrubber.set_frame_count(1)
        self._scrubber.set_frame(0)
        for preview in self._iter_previews():
            preview.clear_frame()
            preview.set_arena(self._arena)
            preview.set_blob_params(self._blob_params)
        self._label_widget.reset_for_new_session()
        self._label_scene.set_label_sets([])
        self._auto_label_widget.load_session(None, "default")
        self._invalidate_blob_cache()
        self._blob_cache_build_pending = False
        self._sync_arena_sliders_from_model()
        self._sync_arena_region_ui()
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
            self._auto_label_widget.load_session(self._session, self._project_id())
        else:
            self._train_widget.load_session(None, "default")
            self._auto_label_widget.load_session(None, "default")

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
        if self._session is None:
            self._video_combo.blockSignals(True)
            self._video_combo.clear()
            self._video_combo.blockSignals(False)
            if hasattr(self, "_video_scene"):
                self._video_scene.set_videos([])
            if hasattr(self, "_auto_label_scene"):
                self._auto_label_scene.set_videos([])
            self._sync_context_bar()
            return
        ids = self._session.get_pose_video_ids()
        active = self._session.get_active_pose_video_id()
        proj = self._session.pose_projects.get(self._project_id(), {})
        videos = proj.get("videos") or {}
        items: list[dict] = []
        auto_items: list[tuple[str, str]] = []
        dirty_missing = False
        for vid in ids:
            entry = videos.get(vid) or {}
            name = entry.get("display_name", vid)
            vdir = self._video_dir(vid)
            missing = bool(entry.get("missing")) or resolve_video_source(vdir) is None
            if missing and not entry.get("missing"):
                self._session.mark_pose_video_missing(vid)
                entry = videos.get(vid) or entry
                missing = True
                dirty_missing = True
            items.append({"id": vid, "name": name, "missing": missing})
            auto_items.append((vid, f"{name} [missing]" if missing else str(name)))
        if dirty_missing:
            self._session.save()
        self._video_combo.blockSignals(True)
        if hasattr(self, "_video_scene"):
            self._video_scene.set_videos(items)
        else:
            self._video_combo.clear()
            for it in items:
                label = f"{it['name']} [missing]" if it.get("missing") else it["name"]
                self._video_combo.addItem(label, it["id"])
        if active:
            idx = self._video_combo.findData(active)
            if idx < 0 and self._video_combo.count():
                idx = 0
            if idx >= 0:
                self._video_combo.setCurrentIndex(idx)
        self._video_combo.blockSignals(False)
        if hasattr(self, "_auto_label_scene"):
            self._auto_label_scene.set_videos(auto_items)
            if active:
                self._auto_label_scene.set_selected_video(str(active))
        n = len(items)
        if hasattr(self, "_video_scene"):
            self._video_scene.status_body.setText(
                f"{n} video(s) in this session." if n else "Upload videos or CSV data to begin."
            )
        self._sync_context_bar()
        self._sync_playback_lock()
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
        preferred: dict[str, str] = {}
        for path in paths:
            try:
                meta = probe_video(path)
            except Exception:
                continue
            relink = self._session.find_pose_video_relink_id(
                display_name=path.name,
                frame_count=meta.frame_count,
                width=meta.width,
                height=meta.height,
            )
            if relink:
                preferred[str(path.resolve())] = relink
        self._set_busy("Uploading videos…", -1, -1)
        if hasattr(self, "_video_scene"):
            self._video_scene.show_import_progress("Uploading videos…")
            self._video_scene.show_video_loading(0)
        self._register_worker = VideoRegisterWorker(
            self._session.getName(),
            pid,
            items,
            set(self._session.get_pose_video_ids()),
            preferred_ids=preferred,
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
        if hasattr(self, "_video_scene"):
            self._video_scene.hide_import_progress()
            self._video_scene.hide_video_loading()
        self._refresh_video_list()
        self._sync_context_bar()

    def _on_worker_failed(self, msg: str) -> None:
        self._sync_pose_loading_overlay()
        self._clear_busy()
        QMessageBox.critical(self, "Pose Studio", msg)

    def _on_video_selected(self, _index: int, *, defer_video: bool = False) -> None:
        vid = self._video_combo.currentData()
        if not vid or self._session is None:
            return
        new_id = str(vid)
        if (
            new_id == self._current_video_id
            and self._reader is not None
            and self._reader.is_opened()
            and not self._needs_video_open
        ):
            return
        self._video_switch_gen += 1
        switch_gen = self._video_switch_gen
        self._mismatch_detect_gen += 1
        if self._mismatch_worker is not None and self._mismatch_worker.isRunning():
            self._mismatch_worker.requestInterruption()
        self._pending_label_crop_remap = False
        self._hide_blob_cache_progress()
        if hasattr(self, "_scan_btn"):
            self._scan_btn.setEnabled(True)
        self._invalidate_blob_cache()
        self._current_video_id = new_id
        self._active_label_set_id = "human"
        self._active_arena_region_id = MAIN_ARENA_ID
        self._crop_setup_skipped = False
        self._scrubber.stop_playback()
        self._session.set_active_pose_video(self._current_video_id)
        # Persist session off the hot path so switching videos stays snappy.
        QTimer.singleShot(0, self._persist_session_if_current)
        vdir = self._video_dir(self._current_video_id)
        self._arena = load_arena(vdir / "arena.json")
        self._blob_params = load_blob_params(vdir / "blob_params.json")
        self._clear_setup_settings_dirty()
        self._sync_controls_from_model(sync_downstream=False)
        self._apply_video_metadata(vdir)
        if defer_video or not self._panel_visible:
            self._release_reader()
            for preview in self._iter_previews():
                preview.clear_frame()
            self._needs_video_open = True
        else:
            self._show_pose_loading()
            self._prepare_playback(vdir)
            self._sync_pose_loading_overlay()
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
        self._sync_playback_lock()
        self._sync_context_bar()
        # Auto Label + Model dataset refresh are deferred so the first frame paints sooner.
        QTimer.singleShot(
            0, lambda g=switch_gen: self._deferred_after_video_switch(g)
        )

    def _persist_session_if_current(self) -> None:
        if self._session is not None:
            self._session.save()

    def _deferred_after_video_switch(self, switch_gen: int) -> None:
        if switch_gen != self._video_switch_gen:
            return
        self._sync_auto_label_tab()
        if self._session is not None:
            self._train_widget.refresh_project_context(self._session, self._project_id())

    def _on_labels_imported(self) -> None:
        self._sync_label_tab()
        self._refresh_label_set_combo()
        self._sync_verify_labels_tab()
        self._sync_auto_label_tab()
        if self._session is not None:
            self._train_widget.refresh_project_context(self._session, self._project_id())

    def _on_auto_label_exported(self) -> None:
        self._sync_verify_labels_tab(force_reload=True)
        self._sync_label_tab()
        self._refresh_label_set_combo()
        self._sync_context_bar()
        if self._label_widget.review_mode():
            self._label_widget._refresh_heatmap_overlay()

    def _on_tracking_exported(self, csv_path: str) -> None:
        if self._session is None:
            return
        self._session.addCSV(csv_path)
        self._session.save()

    def _sync_label_tab(self) -> None:
        if not self._current_video_id or self._session is None:
            self._label_widget.reset_for_new_session()
            self._label_scene.set_label_sets([])
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
        label_dir = self._label_set_dir(self._active_label_set_id)
        display = self._label_set_display_name(self._active_label_set_id)
        self._label_widget.set_label_directory(
            label_dir,
            label_set_id=self._active_label_set_id,
            display_name=display,
        )
        self._refresh_label_set_combo()
        if self._tabs.currentIndex() == self._label_tab_index and self._label_workflow_ready():
            self._label_widget.set_diverse_scan_allowed(True)
        else:
            self._label_widget.set_diverse_scan_allowed(False)
        self._sync_context_bar()

    def _sync_verify_labels_tab(self, *, force_reload: bool = False) -> None:
        """Verify Labels tab removed — review happens on Label."""
        return

    def _sync_auto_label_tab(self) -> None:
        if self._session is None:
            self._auto_label_widget.load_session(None, "default")
            if hasattr(self, "_auto_label_scene"):
                self._auto_label_scene.set_videos([])
                self._auto_label_scene.set_models([])
                self._auto_label_scene.set_heatmap_archives([])
            return
        self._auto_label_widget.load_session(self._session, self._project_id())
        self._auto_label_widget.set_video_id(self._current_video_id)
        if hasattr(self, "_auto_label_scene"):
            if not self._current_video_id:
                self._auto_label_scene.set_models([])
                self._auto_label_scene.set_heatmap_archives([])
                self._auto_label_scene.set_run_enabled(False, tooltip="Select a video first")
                self._auto_label_scene.set_view_output_enabled(False)
            else:
                self._auto_label_scene.set_selected_video(self._current_video_id)
                # Mirror checkpoint labels into scene model combo
                models: list[tuple[str, str]] = []
                combo = getattr(self._auto_label_widget, "_checkpoint_combo", None)
                if combo is not None:
                    for i in range(combo.count()):
                        key = combo.itemData(i)
                        if key is None:
                            continue
                        models.append((str(key), combo.itemText(i)))
                self._auto_label_scene.set_models(models)
                if combo is not None:
                    key = combo.currentData()
                    if key:
                        self._auto_label_scene.set_selected_model(str(key))
                archives = list_heatmap_archives(
                    self._session.getName(), self._project_id(), self._current_video_id
                )
                self._auto_label_scene.set_heatmap_archives(
                    [(a.key, a.label) for a in archives]
                )
                reason = ""
                try:
                    reason = self._auto_label_widget._disable_reason()
                except Exception:
                    reason = ""
                self._auto_label_scene.set_run_enabled(
                    not bool(reason), tooltip=reason or "Run auto-label"
                )
                self._auto_label_scene.set_view_output_enabled(True)
        self._sync_context_bar()

    def _sync_controls_from_model(self, *, sync_downstream: bool = True) -> None:
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
        self._sync_arena_region_ui()
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
            preview.set_active_arena_region(self._active_arena_region_id)
        if self._arena_is_confirmed():
            for preview in self._iter_previews():
                preview.set_blob_params(self._blob_params)
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        if sync_downstream:
            self._sync_label_tab()
            self._sync_verify_labels_tab()
            self._sync_auto_label_tab()

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
            self._sync_pose_loading_overlay()
            return
        preferred = vdir / "source.mp4"
        if preferred.is_file() or not needs_transcode(src):
            self._start_video_open(vdir)
            return
        self._set_busy("Converting video to H.264 MP4…", 0, -1)
        self._migrate_worker = PlaybackMigrateWorker(vdir)
        self._migrate_worker.progress.connect(self._set_busy)
        self._migrate_worker.finished_ok.connect(self._on_playback_migrate_done)
        self._migrate_worker.failed.connect(self._on_worker_failed)
        self._migrate_worker.start()
        self._sync_pose_loading_overlay()

    def _start_video_open(self, vdir: Path) -> None:
        self._video_open_gen += 1
        open_gen = self._video_open_gen
        self._pending_video_open_dir = Path(vdir)
        if self._video_open_worker is not None and self._video_open_worker.isRunning():
            # Let the in-flight probe finish; we open only the latest pending dir.
            self._show_pose_loading("Opening video…")
            self._sync_pose_loading_overlay()
            return
        self._show_pose_loading("Opening video…")
        self._video_open_worker = VideoOpenWorker(vdir, self)
        self._video_open_worker.finished_ok.connect(
            lambda path, g=open_gen: self._on_video_open_done(path, g)
        )
        self._video_open_worker.failed.connect(
            lambda msg, g=open_gen: self._on_video_open_failed(msg, g)
        )
        self._video_open_worker.start()
        self._sync_pose_loading_overlay()

    def _on_video_open_done(self, vdir_str: str, open_gen: int | None = None) -> None:
        self._video_open_worker = None
        pending = self._pending_video_open_dir
        if pending is not None and Path(vdir_str).resolve() != pending.resolve():
            # User switched videos while this probe ran — start the latest one.
            self._start_video_open(pending)
            return
        if open_gen is not None and open_gen != self._video_open_gen:
            return
        vdir = Path(vdir_str)
        self._show_pose_loading("Loading playback")
        self._reader_open_pending = True
        self._sync_pose_loading_overlay()
        QTimer.singleShot(0, lambda: self._finish_video_open_deferred(vdir))

    def _on_video_open_failed(self, msg: str, open_gen: int | None = None) -> None:
        self._video_open_worker = None
        if open_gen is not None and open_gen != self._video_open_gen:
            pending = self._pending_video_open_dir
            if pending is not None:
                self._start_video_open(pending)
            return
        self._needs_video_open = False
        self._reader_open_pending = False
        self._sync_pose_loading_overlay()
        QMessageBox.warning(self, "Pose Studio", msg)

    def _finish_video_open_deferred(self, vdir: Path) -> None:
        try:
            self._finish_video_open(vdir)
        finally:
            self._reader_open_pending = False
            self._needs_video_open = False
            self._sync_pose_loading_overlay()

    def _finish_video_open(self, vdir: Path) -> None:
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
        QTimer.singleShot(0, lambda: self._show_frame(0))
        self._sync_arena_sliders_from_model()
        self._sync_arena_region_ui()
        self._apply_preview_modes()
        if self._tabs.currentIndex() == self._label_tab_index:
            self._label_widget.refresh_display()
        if self._arena_is_confirmed():
            self._schedule_blob_cache_build()
            self._label_widget.start_pose_fingerprint_scan_if_needed()

    def _on_playback_migrate_done(self, _path: str) -> None:
        self._clear_busy()
        if self._current_video_id and self._session is not None:
            self._start_video_open(self._video_dir(self._current_video_id))
        self._needs_video_open = False
        self._sync_label_tab()
        self._sync_verify_labels_tab()
        self._sync_pose_loading_overlay()

    def _open_video_reader(self, vdir: Path) -> None:
        """Synchronous open — prefer ``_start_video_open`` for UI responsiveness."""
        self._finish_video_open(vdir)
        self._sync_pose_loading_overlay()

    def _release_reader(self) -> None:
        if self._reader is not None:
            self._reader.release()
            self._reader = None

    def _read_frame(self, index: int):
        if self._reader is None or not self._reader.is_opened():
            return None
        return self._reader.read(index)

    def _on_scrubber_frame(self, index: int) -> None:
        # Ignore drag-preview that may still be queued after pointer-up.
        self._scrub_preview_timer.stop()
        self._pending_scrub_index = None
        # Defer the settled paint until after the release event queue finishes so a
        # late drag preview cannot wipe live overlays when releasing mid-motion.
        self._pending_scrub_settle_index = int(index)
        self._scrub_settle_timer.start(50)

    def _on_scrubber_preview(self, index: int) -> None:
        # Drag: bare while settings are dirty; otherwise immediate (cache or live).
        if not self._scrubber.is_slider_down():
            return
        self._scrub_settle_timer.stop()
        self._pending_scrub_settle_index = None
        self._pending_scrub_index = index
        if not self._scrub_preview_timer.isActive():
            self._flush_scrub_preview()
            self._scrub_preview_timer.start(33)

    def _flush_scrub_preview(self) -> None:
        if self._pending_scrub_index is None:
            return
        # A release may have landed while this timer was pending — do not paint bare.
        if not self._scrubber.is_slider_down():
            self._pending_scrub_index = None
            return
        index = self._pending_scrub_index
        self._pending_scrub_index = None
        self._show_frame(index, fast=True, from_scrub=True)

    def _flush_scrub_settle(self) -> None:
        if self._pending_scrub_settle_index is None:
            return
        if self._scrubber.is_slider_down():
            # Still dragging (new press); wait for the next release.
            return
        index = self._pending_scrub_settle_index
        self._pending_scrub_settle_index = None
        self._show_frame(index, from_scrub=True)

    def _on_scrubber_playback_started(self) -> None:
        self._cache_hint.hide()
        if self._setup_preview is not None:
            self._setup_preview.set_playback_mode(True)

    def _on_scrubber_playback_stopped(self, index: int) -> None:
        if self._setup_preview is not None:
            self._setup_preview.set_playback_mode(False)
        self._show_frame(index, fast=False, from_scrub=True)

    def _show_frame(
        self,
        index: int,
        *,
        fast: bool = False,
        from_scrub: bool = False,
    ) -> None:
        frame = self._read_frame(index)
        if frame is None:
            return
        dirty = bool(self._settings_dirty)
        confirmed = self._arena_is_confirmed() and not dirty
        playing = self._scrubber.is_playing() and not fast

        if from_scrub and dirty and fast:
            # Drag after Arena/Selection change: bare video (no arena/crop overlay).
            kwargs = {
                "update_blob": False,
                "blob": None,
                "playback_entry": None,
                "playback": False,
                "bare": True,
            }
        elif from_scrub and dirty:
            # Release after settings change: live visuals for current settings.
            kwargs = {
                "update_blob": True,
                "blob": None,
                "playback_entry": None,
                "playback": False,
                "bare": False,
            }
        elif confirmed:
            entry = self._blob_cache_entry(index)
            if entry is not None and (playing or from_scrub):
                kwargs = {
                    "update_blob": False,
                    "blob": entry.to_blob_result(),
                    "playback_entry": entry,
                    "playback": True,
                    "bare": False,
                }
            elif entry is not None:
                # Cached overlays for the resting frame — skip full-res detect.
                kwargs = {
                    "update_blob": False,
                    "blob": entry.to_blob_result(),
                    "playback_entry": entry,
                    "playback": False,
                    "bare": False,
                }
            elif playing:
                kwargs = {
                    "update_blob": True,
                    "blob": None,
                    "playback_entry": None,
                    "playback": True,
                    "bare": False,
                }
            else:
                # Initial load / current-frame refresh — always show live overlays.
                kwargs = {
                    "update_blob": True,
                    "blob": None,
                    "playback_entry": None,
                    "playback": False,
                    "bare": False,
                }
        else:
            # Not Updated yet (and not dirty), or live edit of current frame.
            kwargs = {
                "update_blob": True,
                "blob": None,
                "playback_entry": None,
                "playback": False,
                "bare": False,
            }

        tab = self._tabs.currentIndex()
        if tab == self._setup_tab_index and self._setup_preview is not None:
            self._setup_preview.set_frame_bgr(frame, **kwargs)
        else:
            for preview in self._iter_previews():
                preview.set_frame_bgr(frame, **kwargs)

    def _on_arena_dragged(self, arena: ArenaConfig) -> None:
        self._mark_setup_settings_dirty()
        self._arena = arena
        self._sync_arena_sliders_from_model()
        self._sync_arena_region_ui()
        self._sync_arena_to_previews()
        self._refresh_current_frame()
        self._sync_playback_lock()

    def _on_arena_controls(self, *_args) -> None:
        self._mark_setup_settings_dirty()
        if str(self._arena_shape.currentData() or "square") == "circle":
            self._sync_arena_slider_ranges()
        self._apply_arena_from_sliders()
        self._sync_arena_to_previews()
        if self._setup_preview is not None:
            self._setup_preview.set_blob_enabled(True)
            self._setup_preview.set_blob_params(self._blob_params)
        self._refresh_current_frame()
        self._sync_playback_lock()

    def _apply_blob_from_sliders(self) -> None:
        self._blob_params.brightness_min = self._bright_min.value()
        self._blob_params.brightness_max = max(
            self._blob_params.brightness_min + 1,
            self._bright_max.value(),
        )
        self._blob_params.blob_padding_px = self._blob_padding_px.value()
        self._blob_params.crop_padding_px = self._crop_padding_px.value()

    def _on_blob_sliders(self, *_args) -> None:
        if not self._ui_ready or self._setup_preview is None:
            return
        # Editing selection after a commit requires Update-for-all again.
        self._mark_setup_settings_dirty()
        self._apply_blob_from_sliders()
        self._setup_preview.set_blob_enabled(True)
        self._setup_preview.set_blob_params(self._blob_params)
        self._label_widget.update_tracking_params(self._arena, self._blob_params)
        # Live current-frame only — never rebuild the full-frame cache here.
        self._refresh_current_frame()
        self._sync_playback_lock()

    def _invalidate_blob_cache(self) -> None:
        self._blob_cache_debounce.stop()
        self._blob_cache_build_pending = False
        if self._blob_cache_worker is not None and self._blob_cache_worker.isRunning():
            self._blob_cache_worker.requestInterruption()
        self._blob_cache_worker = None
        self._blob_playback_cache = None
        self._blob_cache_key = None
        self._blob_cache_frame_count = 0
        self._cache_hint.hide()
        self._hide_blob_cache_progress()
        if self._setup_preview is not None:
            self._setup_preview.set_playback_mode(False)

    def _show_blob_cache_progress(self, message: str = "Loading playback overlays…") -> None:
        if not hasattr(self, "_video_scene"):
            return
        self._video_progress_message = message
        self._video_scene.progress.show()
        self._video_scene.progress.set_busy_message(message)
        self._cache_hint.setText(message)
        self._cache_hint.show()

    def _update_blob_cache_progress(self, phase: str, cur: int, tot: int) -> None:
        if not hasattr(self, "_video_scene"):
            return
        self._video_scene.progress.show()
        if phase == "save":
            self._video_scene.progress.set_busy_message("Saving playback cache…")
            msg = "Saving playback cache…"
        else:
            self._video_scene.progress.set_progress(
                cur,
                tot,
                activity="Loading playback overlays",
                unit="frames",
            )
            msg = self._video_progress_message or "Loading playback overlays…"
            if tot > 0:
                msg = f"Loading playback overlays - {cur}/{tot} frames"
        self._cache_hint.setText(msg)
        self._cache_hint.show()

    def _hide_blob_cache_progress(self) -> None:
        if hasattr(self, "_video_scene"):
            self._video_scene.hide_import_progress()
        self._cache_hint.hide()

    def _schedule_blob_cache_build(self) -> None:
        if not self._arena_is_confirmed():
            return
        self._blob_cache_build_pending = True
        self._show_blob_cache_progress("Loading playback overlays…")
        self._sync_playback_lock()
        self._blob_cache_debounce.start(600)

    def _blob_cache_entry(self, index: int) -> PlaybackBlobEntry | None:
        if self._blob_playback_cache is None:
            return None
        if index < 0 or index >= len(self._blob_playback_cache):
            return None
        return self._blob_playback_cache[index]

    def _start_blob_cache_build(self) -> None:
        try:
            if not self._arena_is_confirmed() or not self._current_video_id or self._session is None:
                self._hide_blob_cache_progress()
                return
            vdir = self._video_dir(self._current_video_id)
            src = resolve_video_source(vdir)
            if src is None:
                self._hide_blob_cache_progress()
                return
            meta = read_video_meta(vdir)
            frame_count = meta.frame_count if meta and meta.frame_count > 0 else 1
            cache_key = playback_blob_cache_key(self._arena, self._blob_params)
            if (
                self._blob_cache_key == cache_key
                and self._blob_playback_cache is not None
                and len(self._blob_playback_cache) >= frame_count
            ):
                self._hide_blob_cache_progress()
                self._maybe_remap_labels_to_crops()
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
                self._hide_blob_cache_progress()
                self._maybe_remap_labels_to_crops()
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
                save_dir=vdir,
            )
            self._blob_cache_worker.progress.connect(self._on_blob_cache_progress)
            self._blob_cache_worker.finished_ok.connect(self._on_blob_cache_finished)
            self._blob_cache_worker.failed.connect(self._on_blob_cache_failed)
            self._show_blob_cache_progress("Loading playback overlays…")
            self._blob_cache_worker.start()
        finally:
            self._blob_cache_build_pending = False
            self._sync_playback_lock()

    def _on_blob_cache_progress(self, phase: str, cur: int, tot: int) -> None:
        if not self._scrubber.is_playing():
            self._update_blob_cache_progress(phase, cur, tot)

    def _on_blob_cache_finished(self) -> None:
        worker = self._blob_cache_worker
        if worker is not None and worker.entries:
            self._blob_playback_cache = list(worker.entries)
        self._hide_blob_cache_progress()
        self._sync_playback_lock()
        self._maybe_remap_labels_to_crops()

    def _on_blob_cache_failed(self, _msg: str) -> None:
        self._blob_playback_cache = None
        self._hide_blob_cache_progress()
        self._sync_playback_lock()
        self._maybe_remap_labels_to_crops()

    def _maybe_remap_labels_to_crops(self) -> None:
        """After Update-for-all, flag labels outside the new crops (keep all points)."""
        if not self._pending_label_crop_remap:
            return
        self._pending_label_crop_remap = False
        outside_pts, outside_frames = self._label_widget.refresh_outside_crop_warnings()
        if outside_pts:
            QMessageBox.information(
                self,
                "Pose Studio",
                (
                    f"{outside_pts} label point(s) on {outside_frames} frame(s) fall outside "
                    "the new square crop. Labels were kept. Orange dots under the timeline "
                    "bars mark affected frames."
                ),
            )

    def _on_auto_threshold(self) -> None:
        self._set_busy("Suggesting selection values…")
        frame = self._read_frame(self._scrubber.frame_index())
        if frame is None:
            self._clear_busy()
            QMessageBox.warning(self, "Pose Studio", "Open a video frame first.")
            return
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        lo, hi = suggest_blob_selection_values(gray, self._arena)
        self._bright_min.blockSignals(True)
        self._bright_max.blockSignals(True)
        self._bright_min.setValue(lo)
        self._bright_max.setValue(hi)
        self._bright_min.blockSignals(False)
        self._bright_max.blockSignals(False)
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

    def _on_detect_next_mismatch(self) -> None:
        """Jump scrubber to the next volume/size/center-jump outlier (wraps)."""
        if not self._current_video_id:
            return
        if not self._arena_is_confirmed():
            QMessageBox.warning(
                self,
                "Pose Studio",
                "Run Update for all frames first so blob stats are available.",
            )
            return
        if self._mismatch_worker is not None and self._mismatch_worker.isRunning():
            return

        entries = list(self._blob_playback_cache) if self._blob_playback_cache else None
        qc_frames = None
        if entries is None:
            qc_path = self._video_dir(self._current_video_id) / "blob_qc.json"
            if qc_path.is_file():
                qc_frames, _ = load_blob_qc(qc_path)
            else:
                QMessageBox.warning(
                    self,
                    "Pose Studio",
                    "Run Update for all frames first (or a blob scan) so mismatch stats exist.",
                )
                return

        self._mismatch_detect_gen += 1
        gen = self._mismatch_detect_gen
        self._scan_btn.setEnabled(False)
        self._show_blob_cache_progress("Detecting mismatching frames…")
        self._mismatch_worker = MismatchDetectWorker(
            entries=entries,
            qc_frames=qc_frames,
        )
        self._mismatch_worker.progress.connect(self._on_mismatch_detect_progress)
        self._mismatch_worker.finished_ok.connect(
            lambda frames, g=gen: self._on_mismatch_detect_done(frames, g)
        )
        self._mismatch_worker.failed.connect(
            lambda msg, g=gen: self._on_mismatch_detect_failed(msg, g)
        )
        self._mismatch_worker.start()

    def _on_mismatch_detect_progress(self, cur: int, tot: int) -> None:
        self._update_blob_cache_progress("scan", cur, tot)

    def _on_mismatch_detect_done(self, mismatches: list, gen: int) -> None:
        if gen != self._mismatch_detect_gen:
            return
        self._hide_blob_cache_progress()
        self._scan_btn.setEnabled(True)
        frames = [int(f) for f in mismatches]
        if not frames:
            QMessageBox.information(self, "Pose Studio", "No mismatching frames found.")
            return
        self._scrubber.set_flagged_frames(set(frames))
        cursor = self._scrubber.frame_index()
        nxt = next_mismatch_frame(frames, cursor)
        if nxt is not None:
            self._scrubber.set_frame(nxt)

    def _on_mismatch_detect_failed(self, msg: str, gen: int) -> None:
        if gen != self._mismatch_detect_gen:
            return
        self._hide_blob_cache_progress()
        self._scan_btn.setEnabled(True)
        QMessageBox.warning(self, "Pose Studio", f"Mismatch detection failed.\n{msg}")

    def _on_blob_scan(self) -> None:
        """Optional full-video QC scan (legacy); prefer Update-for-all + detect next."""
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

    def _on_update_all_frames(self) -> None:
        """Commit arena + blob settings and rebuild playback cache (Update for all frames)."""
        if not self._current_video_id or self._session is None:
            QMessageBox.warning(self, "Pose Studio", "Select a video first.")
            return
        self._sync_arena_sliders_from_model()
        self._apply_arena_from_sliders()
        self._apply_blob_from_sliders()
        self._clamp_arena_geometry()
        self._arena.confirmed = True
        self._clear_setup_settings_dirty()
        vdir = self._video_dir(self._current_video_id)
        save_arena(vdir / "arena.json", self._arena)
        save_blob_params(vdir / "blob_params.json", self._blob_params)
        self._sync_arena_sliders_from_model()
        self._sync_arena_to_previews()
        self._update_arena_blob_ui_state()
        self._apply_preview_modes()
        self._pending_label_crop_remap = True
        self._sync_label_tab()
        # Flag outside-crop labels only — never prune (full-frame coords preserved on disk).
        self._maybe_remap_labels_to_crops()
        self._schedule_blob_cache_build()
        self._label_widget.start_pose_fingerprint_scan_if_needed()
        if hasattr(self, "_video_scene"):
            self._video_scene.set_update_all_highlighted(False)
        self._sync_playback_lock()
        self._sync_context_bar()
        self._refresh_current_frame()

    def _on_video_skip(self) -> None:
        reply = QMessageBox.warning(
            self,
            "Skip crop setup",
            "Skipping crop setup can make labeling and training slower and less accurate.\n\nContinue anyway?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._crop_setup_skipped = True
        idx = self._tabs.indexOf(self._label_scene)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)
        self._label_widget.set_diverse_scan_allowed(True)
        self._sync_playback_lock()

    def _on_delete_video(self, video_id: str) -> None:
        self._delete_video_impl(video_id, delete_heatmaps=False)

    def _on_delete_video_and_heatmaps(self, video_id: str) -> None:
        self._delete_video_impl(video_id, delete_heatmaps=True)

    def _delete_video_impl(self, video_id: str, *, delete_heatmaps: bool) -> None:
        if self._session is None or not video_id:
            return
        vdir = self._video_dir(video_id)
        try:
            remove_video_source_files(vdir)
            if delete_heatmaps:
                with brief_busy_scope(self, "Deleting heatmaps…"):
                    for arch in list_heatmap_archives(
                        self._session.getName(), self._project_id(), video_id
                    ):
                        try:
                            delete_heatmap_archive(arch.path)
                        except FileNotFoundError:
                            pass
                    clear_video_runtime_caches(vdir)
            self._session.mark_pose_video_missing(video_id)
            self._session.save()
        except Exception as exc:
            QMessageBox.warning(self, "Pose Studio", f"Could not remove video:\n{exc}")
            return
        if self._current_video_id == video_id:
            self._release_reader()
            self._current_video_id = None
        self._refresh_video_list()
        self._sync_auto_label_tab()
        self._sync_context_bar()

    def _sync_playback_lock(self) -> None:
        """Scrub whenever a video is open; Play only after Update-for-all + cache."""
        video_opening = (
            self._needs_video_open
            or self._reader_open_pending
            or (
                self._video_open_worker is not None
                and self._video_open_worker.isRunning()
            )
        )
        video_ready = (
            self._reader is not None
            and self._reader.is_opened()
            and not video_opening
        )
        scrub_ok = bool(video_ready)
        play_ok = bool(
            video_ready
            and self._arena_is_confirmed()
            and not self._blob_cache_busy()
        )
        self._scrubber.set_scrub_enabled(scrub_ok)
        self._scrubber.set_play_enabled(play_ok)
        if hasattr(self, "_video_scene"):
            self._video_scene.set_update_all_highlighted(not self._arena_is_confirmed())

    def _output_chip_text(self) -> tuple[str, str]:
        """Return (short_label, full_text) for the Auto Label / AI output chip."""
        if not self._current_video_id or self._session is None:
            return "—", ""
        out_dir = ai_labelled_dir(
            self._session.getName(), self._project_id(), self._current_video_id
        )
        tracking = out_dir / "tracking.csv"
        if not tracking.is_file():
            archives = list_heatmap_archives(
                self._session.getName(), self._project_id(), self._current_video_id
            )
            if archives:
                n = len(archives)
                short = f"Heatmaps ×{n}"
                return short, f"AI heatmaps: {n} archive(s) under ai_labelled/"
            return "—", ""
        try:
            ds = load_dataset_from_dir(out_dir)
            labeled = ds.count_frames_with_any_point()
        except (OSError, ValueError, FileNotFoundError):
            labeled = 0
        total = max(self._label_set_frame_count(), 1)
        short = f"AI — {labeled}/{total}"
        full = f"Auto label output — {labeled}/{total} frames"
        return short, full

    def _sync_context_bar_active_key(self, tab_index: int | None = None) -> None:
        if tab_index is None:
            tab_index = self._tabs.currentIndex()
        key_map = {
            self._tabs.indexOf(self._video_scene): "video",
            self._tabs.indexOf(self._label_scene): "labels",
            self._tabs.indexOf(self._model_scene): "model",
            self._tabs.indexOf(self._auto_label_scene): "output",
        }
        active = key_map.get(tab_index)
        for scene in (
            getattr(self, "_video_scene", None),
            getattr(self, "_label_scene", None),
            getattr(self, "_model_scene", None),
            getattr(self, "_auto_label_scene", None),
        ):
            if scene is None:
                continue
            scene.shell.context_bar.set_active_key(active)

    def _sync_context_bar(self) -> None:
        video_name = "—"
        if self._current_video_id and self._session is not None:
            entry = self._session.get_pose_video_entry(self._current_video_id) or {}
            video_name = entry.get("display_name") or self._current_video_id
            if entry.get("missing") or (
                resolve_video_source(self._video_dir(self._current_video_id)) is None
            ):
                video_name = f"{video_name} [missing]"
        label_name = "—"
        try:
            display = self._label_widget.active_label_set_display
            counts = self._label_widget.labeled_counts()
            labeled = counts.get("labeled_frames", 0)
            total = counts.get("total_frames", 0)
            label_name = f"{display} — {labeled}/{total} frames"
        except Exception:
            pass
        model_name = "—"
        dataset_name = "—"
        try:
            label_fn = getattr(self._train_widget, "selected_model_label", None)
            if callable(label_fn):
                model_name = label_fn() or "—"
        except Exception:
            pass
        try:
            ds_fn = getattr(self._train_widget, "selected_dataset_summary", None)
            if callable(ds_fn):
                dataset_name = ds_fn() or "—"
        except Exception:
            pass
        output_label, output_full = self._output_chip_text()
        for scene in (
            getattr(self, "_video_scene", None),
            getattr(self, "_label_scene", None),
            getattr(self, "_model_scene", None),
            getattr(self, "_auto_label_scene", None),
        ):
            if scene is None:
                continue
            bar = scene.shell.context_bar
            bar.set_chip("video", label=video_name, full_text=video_name)
            bar.set_chip("labels", label=label_name, full_text=label_name)
            bar.set_chip("model", label=model_name, full_text=model_name)
            bar.set_chip("output", label=output_label, full_text=output_full)
            bar.set_chip("dataset", label=dataset_name, full_text=dataset_name)
        self._sync_context_bar_active_key()

    def _label_set_dir(self, label_set_id: str) -> Path:
        assert self._session is not None and self._current_video_id
        session_name = self._session.getName()
        project_id = self._project_id()
        video_id = self._current_video_id
        if label_set_id == "human":
            return human_labelled_dir(session_name, project_id, video_id)
        if label_set_id == "ai":
            return ai_labelled_dir(session_name, project_id, video_id)
        return custom_labelled_dir(session_name, project_id, video_id, label_set_id)

    def _label_set_display_name(self, label_set_id: str) -> str:
        if label_set_id == "human":
            return "Human"
        if label_set_id == "ai":
            return "AI"
        if not self._session or not self._current_video_id:
            return label_set_id
        for slug, display, _path in list_custom_sets(
            self._session.getName(),
            self._project_id(),
            self._current_video_id,
        ):
            if slug == label_set_id:
                return display
        return label_set_id

    def _ai_label_set_available(self) -> bool:
        if not self._current_video_id or self._session is None:
            return False
        ai_dir = ai_labelled_dir(
            self._session.getName(), self._project_id(), self._current_video_id
        )
        return (ai_dir / "tracking.csv").is_file() or (ai_dir / "labels.json").is_file()

    def _label_set_frame_count(self) -> int:
        if not self._current_video_id or self._session is None:
            return 0
        meta_path = self._video_dir(self._current_video_id) / "meta.json"
        if not meta_path.is_file():
            return 0
        try:
            return int(json.loads(meta_path.read_text(encoding="utf-8")).get("frame_count", 0))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return 0

    def _label_set_combo_text(
        self,
        display_name: str,
        label_dir: Path,
        *,
        frame_count: int,
    ) -> str:
        total = max(frame_count, 1)
        try:
            if (label_dir / "tracking.csv").is_file() or (label_dir / "labels.json").is_file():
                ds = load_dataset_from_dir(label_dir)
            else:
                ds = load_labels(label_dir)
            labeled = ds.count_frames_with_any_point()
        except (OSError, ValueError, FileNotFoundError):
            labeled = 0
        return f"{display_name} — {labeled}/{total} frames"

    def _refresh_label_set_combo(self) -> None:
        if not self._current_video_id or self._session is None:
            self._label_scene.set_label_sets([])
            return
        frame_count = self._label_set_frame_count()
        session_name = self._session.getName()
        project_id = self._project_id()
        video_id = self._current_video_id
        items: list[tuple[str, str]] = []
        human_dir = human_labelled_dir(session_name, project_id, video_id)
        items.append(
            (
                "human",
                self._label_set_combo_text("Human", human_dir, frame_count=frame_count),
            )
        )
        if self._ai_label_set_available():
            ai_dir = ai_labelled_dir(session_name, project_id, video_id)
            items.append(
                (
                    "ai",
                    self._label_set_combo_text("AI", ai_dir, frame_count=frame_count),
                )
            )
        for slug, display, path in list_custom_sets(session_name, project_id, video_id):
            items.append(
                (
                    slug,
                    self._label_set_combo_text(display, path, frame_count=frame_count),
                )
            )
        self._label_scene.set_label_sets(items)
        self._label_scene.set_active_label_set(self._active_label_set_id)

    def _on_label_set_changed(self, label_set_id: str) -> None:
        if not self._current_video_id or self._session is None:
            return
        if label_set_id == self._active_label_set_id:
            return
        self._label_widget._save_labels(silent=True)
        self._active_label_set_id = label_set_id
        label_dir = self._label_set_dir(label_set_id)
        display = self._label_set_display_name(label_set_id)
        self._label_widget.set_label_directory(
            label_dir,
            label_set_id=label_set_id,
            display_name=display,
        )
        self._refresh_label_set_combo()
        self._sync_context_bar()

    def _on_remove_label_set(self, label_set_id: str) -> None:
        if not self._current_video_id or self._session is None:
            return
        if label_set_id in ("human", "ai"):
            return
        display = self._label_set_display_name(label_set_id)
        reply = QMessageBox.question(
            self,
            "Remove label set",
            f"Delete custom label set “{display}”? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if self._active_label_set_id == label_set_id:
            self._label_widget._save_labels(silent=True)
        try:
            delete_custom_set(
                self._session.getName(),
                self._project_id(),
                self._current_video_id,
                label_set_id,
            )
        except (OSError, ValueError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Pose Studio", f"Could not remove label set:\n{exc}")
            return
        if self._active_label_set_id == label_set_id:
            self._active_label_set_id = "human"
            human_dir = human_labelled_dir(
                self._session.getName(), self._project_id(), self._current_video_id
            )
            self._label_widget.set_label_directory(
                human_dir,
                label_set_id="human",
                display_name="Human",
            )
        self._refresh_label_set_combo()
        self._sync_context_bar()

    def _on_create_label_set(self) -> None:
        if not self._current_video_id or self._session is None:
            QMessageBox.warning(self, "Pose Studio", "Select a video first.")
            return
        name, ok = QInputDialog.getText(
            self,
            "Create New Labels",
            "Label set name:",
        )
        if not ok:
            return
        display_name = name.strip()
        if not display_name:
            QMessageBox.warning(self, "Pose Studio", "Enter a name for the new label set.")
            return
        slug = slugify_dataset_name(display_name)
        existing = {
            s for s, _d, _p in list_custom_sets(
                self._session.getName(),
                self._project_id(),
                self._current_video_id,
            )
        }
        if slug in existing:
            QMessageBox.warning(
                self,
                "Pose Studio",
                f"A label set named “{display_name}” already exists.",
            )
            return
        self._label_widget._save_labels(silent=True)
        frame_count = self._label_set_frame_count()
        ds = LabelDataset(schema=canonical_lab_schema())
        try:
            dest = save_named_set(
                self._session.getName(),
                self._project_id(),
                self._current_video_id,
                display_name,
                ds,
                frame_count=frame_count,
                slug=slug,
            )
        except OSError as exc:
            QMessageBox.warning(self, "Pose Studio", f"Could not create label set:\n{exc}")
            return
        self._active_label_set_id = slug
        self._label_widget.set_label_directory(
            dest,
            label_set_id=slug,
            display_name=display_name,
        )
        self._refresh_label_set_combo()
        self._sync_context_bar()

    def _on_unique_reduce(self, keep_n: int) -> None:
        remaining = self._label_widget.apply_unique_reduce(int(keep_n))
        self._refresh_label_set_combo()
        self._sync_context_bar()
        QMessageBox.information(
            self,
            "Unique frames",
            f"Kept {remaining} most unique labeled frame(s).",
        )


    def _on_auto_scene_video_changed(self, video_id: str) -> None:
        if not video_id:
            return
        idx = self._video_combo.findData(video_id)
        if idx >= 0 and idx != self._video_combo.currentIndex():
            self._video_combo.setCurrentIndex(idx)

    def _on_auto_scene_model_changed(self, model_key: str) -> None:
        combo = getattr(self._auto_label_widget, "_checkpoint_combo", None)
        if combo is None or not model_key:
            return
        idx = combo.findData(model_key)
        if idx >= 0 and idx != combo.currentIndex():
            combo.setCurrentIndex(idx)
            self._auto_label_widget._sync_enabled()

    def _on_upload_prelabeled(self) -> None:
        self._import_csv_dialog(kind="prelabeled")

    def _on_upload_analysis(self) -> None:
        self._import_csv_dialog(kind="analysis")

    def _import_csv_dialog(self, *, kind: str) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Pose Studio", "Open a session first.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV (raw DLC or enriched)",
            "",
            "CSV (*.csv);;All files (*)",
        )
        if not path:
            return
        if not self._current_video_id:
            QMessageBox.warning(
                self,
                "Pose Studio",
                "Select or upload a video first so the CSV can be attached.",
            )
            return
        try:
            from core.pose.dataset.import_external_dataset import import_external_dlc_csv

            dest = import_external_dlc_csv(
                self._session.getName(),
                self._project_id(),
                self._current_video_id,
                Path(path),
            )
            self._video_scene.set_status("Imported", f"{kind}: saved to {dest}")
            if kind == "analysis":
                self.dataset_json_selected.emit(str(dest))
            QMessageBox.information(self, "Pose Studio", f"Imported:\n{dest}")
        except Exception as exc:
            QMessageBox.warning(self, "Pose Studio", f"Import failed:\n{exc}")

    def _on_label_review_mode_changed(self, review: bool) -> None:
        self._label_widget.set_review_mode(review)

    def _on_view_auto_label_output(self) -> None:
        """Open Label tab on the AI label set in review mode."""
        video_id = None
        if hasattr(self, "_auto_label_scene"):
            video_id = self._auto_label_scene.selected_video_id()
        if video_id and video_id != self._current_video_id:
            idx = self._video_combo.findData(video_id)
            if idx >= 0:
                self._video_combo.setCurrentIndex(idx)
        if self._session is None or not self._current_video_id:
            QMessageBox.information(
                self,
                "Auto Label",
                "Select a video with AI output first.",
            )
            return
        if not self._ai_label_set_available():
            QMessageBox.information(
                self,
                "Auto Label",
                "No AI labels on disk for this video — run Auto Label first.",
            )
            return
        if self._active_label_set_id != "ai":
            self._label_widget._save_labels(silent=True)
        self._active_label_set_id = "ai"
        self._label_widget.set_label_directory(
            self._label_set_dir("ai"),
            label_set_id="ai",
            display_name="AI",
        )
        self._label_widget.set_review_mode(True)
        self._label_scene.set_review_mode(True)
        self._refresh_label_set_combo()
        self._sync_context_bar()
        idx = self._tabs.indexOf(self._label_scene)
        if idx >= 0:
            self._tabs.setCurrentIndex(idx)

    def _on_auto_label_run_proxy(self) -> None:
        run = getattr(self._auto_label_widget, "_run_btn", None)
        if run is not None:
            run.click()
            return
        QMessageBox.information(
            self,
            "Auto Label",
            "Use the Auto Label controls in the main panel to run labeling.",
        )

