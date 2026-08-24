"""Pose Studio — Step 3 labeling tab."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QShortcut,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_platform.ui_preferences import UiPreferences
from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop
from core.pose.detection.crop import crop_to_full_frame, extract_square_crop, fish_mask_in_crop, full_frame_to_crop
from core.pose.labeling.labels_store import LabelDataset, load_labels, save_labels
from core.pose.labeling.crop_remap import (
    frames_with_labels_outside_crops,
    point_inside_square_crop,
)
from core.pose.labeling.frame_sampler import (
    build_label_frame_queue,
    frames_to_analyze_cap,
    gap_from_frames_to_analyze,
    pad_queue_to_target,
    rank_queue_by_uniqueness,
    reduce_queue_by_uniqueness,
    reduce_queue_using_ranks,
    target_label_frame_count,
)
from core.pose.labeling.scan_progress import PROGRESS_TOTAL
from core.pose.labeling.pose_scan_cache import (
    load_pose_scan_cache,
    scan_settings_hash,
)
from core.pose.labeling.pose_outliers import detect_pose_outlier_frames
from core.pose.labeling.schema import canonical_lab_schema
from ui.components.pose.bodypart_label_list import BodypartLabelList
from ui.components.pose.label_canvas import LabelCanvas
from ui.components.pose.label_frame_strip import LabelFrameStrip
from ui.components.pose.labeling_controller import LabelingController
from ui.workers.label_frame_queue_worker import LabelFrameQueueWorker


def _first_labeled_frame(dataset: LabelDataset) -> int | None:
    for fi in sorted(dataset.frames.keys()):
        fl = dataset.frames[fi]
        if any(xy is not None for xy in fl.points.values()):
            return fi
    return None


class PoseLabelWidget(QWidget):
    """One bodypart × many frames on blob-centered square crop."""

    tracking_exported = pyqtSignal(str)
    background_work_finished = pyqtSignal()
    labels_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseLabelWidget")
        self._read_frame: Callable[[int], np.ndarray | None] | None = None
        self._frame_count = 0
        self._arena = ArenaConfig()
        self._blob_params = BlobParams()
        self._label_dir: Path | None = None
        self._active_label_set_id = "human"
        self._active_label_set_display = "Human"
        self._session_name: str | None = None
        self._project_id: str | None = None
        self._video_id: str | None = None
        self._controller = LabelingController()
        self._controller.bind_listener(self._refresh_ui)
        self._queue_worker: LabelFrameQueueWorker | None = None
        self._thumb_cache: dict[int, QPixmap] = {}
        self._video_path: Path | None = None
        self._video_dir: Path | None = None
        self._pose_scan_cache = None
        self._scan_settings_hash: str | None = None
        self._diverse_scan_allowed = False
        self._diverse_queue_cache: dict[tuple, list[int]] = {}
        self._ui_prefs = UiPreferences()
        self._frame_refresh_attempt = 0
        self._pick_generation = 0
        self._active_pick_target: int | None = None
        self._pre_pick_queue_snapshot: dict | None = None
        self._worker_pick_generation = 0
        self._worker_for_pick = False
        self._displayed_frame_index: int | None = None
        self._displayed_settings_hash: str | None = None
        self._crop_cache_key: tuple[int, str | None] | None = None
        self._crop_cache: tuple[np.ndarray | None, BlobResult | None] | None = None
        self._chrome_attached = False
        self._outside_crop_frames: set[int] = set()
        self._outside_crop_point_count = 0
        self._outside_crop_points_by_frame: dict[int, int] = {}
        self._outside_crop_warnings_dirty = False
        self._review_mode = False
        self._outlier_frames: set[int] = set()
        self._outlier_reasons: dict[int, list[str]] = {}
        self._outlier_bodyparts: dict[int, set[str]] = {}
        self._outlier_bones: dict[int, set[tuple[str, str]]] = {}
        self._outlier_sorted: list[int] = []
        self._label_scene = None
        self._heatmap_archives: list = []
        self._heatmap_archive_dir: Path | None = None
        self._heatmap_view_enabled = False

        root = QVBoxLayout(self)

        self._labeling_tools = QWidget()
        self._labeling_tools.setObjectName("PoseLabelingTools")
        labeling_layout = QVBoxLayout(self._labeling_tools)
        labeling_layout.setContentsMargins(0, 0, 0, 0)
        labeling_layout.setSpacing(4)

        frames_row = QHBoxLayout()
        frames_row.addWidget(QLabel("Frames to analyze"))
        self._frames_spin = QSpinBox()
        self._frames_spin.setRange(1, 300)
        self._frames_spin.setValue(300)
        self._frames_spin.setToolTip("How many frames you want in the labeling queue.")
        self._frames_spin.valueChanged.connect(self._on_frames_spin_changed)
        frames_row.addWidget(self._frames_spin)
        self._frames_max_lbl = QLabel("/ 300")
        self._frames_max_lbl.setObjectName("SettingsHintLabel")
        frames_row.addWidget(self._frames_max_lbl)
        self._frames_slider = QSlider(Qt.Horizontal)
        self._frames_slider.setRange(1, 300)
        self._frames_slider.setValue(300)
        self._frames_slider.setToolTip(
            "Target number of frames to label. Press Detect Unique Frames to apply."
        )
        self._frames_slider.valueChanged.connect(self._on_frames_preview)
        frames_row.addWidget(self._frames_slider, stretch=1)
        self._pick_frames_btn = QPushButton("Detect Unique Frames")
        self._pick_frames_btn.setToolTip(
            "Scan the video and build a diverse frame queue for the target count above."
        )
        self._pick_frames_btn.clicked.connect(self._on_pick_analysis_frames)
        frames_row.addWidget(self._pick_frames_btn)
        labeling_layout.addLayout(frames_row)

        scan_row = QVBoxLayout()
        self._scan_status = QLabel("")
        self._scan_status.setObjectName("SettingsHintLabel")
        self._scan_status.hide()
        scan_row.addWidget(self._scan_status)
        self._scan_progress = QProgressBar()
        self._scan_progress.setObjectName("PoseLabelScanProgress")
        self._scan_progress.setRange(0, PROGRESS_TOTAL)
        self._scan_progress.setValue(0)
        self._scan_progress.hide()
        scan_row.addWidget(self._scan_progress)
        labeling_layout.addLayout(scan_row)
        root.addWidget(self._labeling_tools)

        self._canvas = LabelCanvas()
        root.addWidget(self._canvas, stretch=1)

        self._bodypart_list = BodypartLabelList()
        self._strip = LabelFrameStrip()

        self._bodypart_list.bodypart_selected.connect(self._controller.set_active_bodypart)
        self._bodypart_list.bodypart_renamed.connect(self._on_bodypart_renamed)
        self._bodypart_list.bodypart_removed.connect(self._on_bodypart_removed)
        self._bodypart_list.add_point_requested.connect(self._controller.enter_add_point_mode)
        self._bodypart_list.bone_tool_requested.connect(self._controller.enter_bone_mode)
        self._bodypart_list.bone_tool_cancel_requested.connect(
            self._controller.cancel_bone_mode
        )
        self._bodypart_list.bone_pair_requested.connect(self._on_bone_pair)
        self._bodypart_list.bone_removed.connect(self._on_bone_removed)
        self._bodypart_list.bodypart_reordered.connect(self._on_bodypart_reordered)
        self._canvas.point_placed.connect(self._on_point_placed)
        self._canvas.point_moved.connect(self._on_point_moved)
        self._canvas.add_point_at.connect(self._on_add_point_at)
        self._canvas.bodypart_hit.connect(self._controller.set_active_bodypart)
        self._canvas.drag_started.connect(self._on_drag_started)
        self._canvas.point_delete_requested.connect(self._on_point_delete_requested)
        self._strip.frame_selected.connect(self._on_strip_frame)

        QShortcut(QKeySequence.Undo, self, activated=self._controller.undo)
        QShortcut(QKeySequence.Redo, self, activated=self._controller.redo)
        QShortcut(QKeySequence("Space"), self, activated=self._controller.go_next_frame)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self._controller.go_prev_frame)
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self._controller.go_next_frame)

    @property
    def bodypart_list(self) -> BodypartLabelList:
        return self._bodypart_list

    @property
    def frame_strip(self) -> LabelFrameStrip:
        return self._strip

    def attach_label_chrome(self, scene) -> None:
        """
        Mount bodypart list + frame strip into a :class:`LabelScene`.

        Call once after ``LabelScene.set_content_widget(self)`` so the scene
        owns side schema and timeline chrome while this widget keeps the canvas.
        """
        if self._chrome_attached:
            return
        scene.mount_bodypart_list(self._bodypart_list)
        scene.mount_timeline_widget(self._strip)
        self._label_scene = scene
        scene.heatmap_view_changed.connect(self._on_heatmap_view_changed)
        scene.heatmap_archive_changed.connect(self._on_heatmap_archive_changed)
        scene.photo_opacity_changed.connect(self._on_photo_opacity_changed)
        scene.points_opacity_changed.connect(self._on_points_opacity_changed)
        scene.heatmap_opacity_changed.connect(self._on_heatmap_opacity_changed)
        self._chrome_attached = True

    def set_ui_preferences(self, prefs: UiPreferences) -> None:
        self._ui_prefs = prefs
        self._update_frames_controls_max()
        if self._frame_count > 0:
            self._sync_frames_controls(self._target_frames_value())

    def _max_frames_setting(self) -> int:
        return max(10, int(getattr(self._ui_prefs, "pose_max_frames_to_analyze", 300)))

    def _frames_ui_max(self) -> int:
        """Spin/slider cap: preference limit, or video length when shorter."""
        pref = self._max_frames_setting()
        if self._frame_count > 0:
            return min(pref, self._frame_count)
        return pref

    def _update_frames_controls_max(self) -> None:
        max_f = self._frames_ui_max()
        self._frames_spin.setMaximum(max_f)
        self._frames_slider.setMaximum(max_f)
        self._frames_max_lbl.setText(f"/ {max_f}")
        if self._frames_spin.value() > max_f:
            self._frames_spin.setValue(max_f)
        if self._frames_slider.value() > max_f:
            self._frames_slider.setValue(max_f)

    def _target_frames_value(self) -> int:
        return frames_to_analyze_cap(
            self._frame_count,
            self._frames_spin.value(),
            self._max_frames_setting(),
        )

    def _gap_for_target(self, target: int) -> int:
        return gap_from_frames_to_analyze(self._frame_count, target)

    def _sync_frames_controls(self, target: int) -> None:
        target = frames_to_analyze_cap(
            self._frame_count, target, self._max_frames_setting()
        )
        self._frames_spin.blockSignals(True)
        self._frames_slider.blockSignals(True)
        self._frames_spin.setValue(target)
        self._frames_slider.setValue(target)
        self._frames_spin.blockSignals(False)
        self._frames_slider.blockSignals(False)

    def refresh_display(self) -> None:
        """Re-read the current labeling frame (e.g. after the video reader opens)."""
        if self._review_mode:
            self._displayed_frame_index = None
            self._crop_cache_key = None
            self._crop_cache = None
            self._frame_refresh_attempt = 0
            self._refresh_ui()
            self._schedule_frame_refresh()
            return
        self._invalidate_crop_display()
        self._frame_refresh_attempt = 0
        self._refresh_ui()
        self._schedule_frame_refresh()

    def _schedule_frame_refresh(self) -> None:
        if self._frame_refresh_attempt >= 8:
            return
        if self._current_crop()[0] is not None:
            return
        if self._read_frame is None or self._frame_count <= 0:
            return
        self._frame_refresh_attempt += 1
        QTimer.singleShot(40 + self._frame_refresh_attempt * 35, self._retry_frame_refresh)

    def _retry_frame_refresh(self) -> None:
        self._refresh_ui()
        self._schedule_frame_refresh()

    def _sanitize_queue(self, queue: list[int]) -> list[int]:
        if self._frame_count <= 0:
            return []
        return sorted({int(i) for i in queue if 0 <= int(i) < self._frame_count})

    def _restore_saved_queue(self, ds, target: int) -> list[int] | None:
        saved = self._sanitize_queue(ds.label_frame_queue)
        if saved and ds.frames_to_analyze == target:
            return saved
        if self._pose_scan_cache is not None:
            if (
                self._pose_scan_cache.last_queue
                and self._pose_scan_cache.last_frames_to_analyze == target
            ):
                return self._sanitize_queue(self._pose_scan_cache.last_queue)
        return None

    def _persist_label_queue(self) -> None:
        if self._label_dir is None:
            return
        queue = list(self._controller.frame_queue)
        if not queue:
            return
        target = self._target_frames_value()
        gap = self._gap_for_target(target)
        self._controller.dataset.label_frame_queue = queue
        self._controller.dataset.frames_to_analyze = target
        self._controller.dataset.gap = gap
        save_labels(self._label_dir, self._controller.dataset)

    def _apply_frame_queue(
        self,
        target: int,
        gap: int,
        queue: list[int],
        *,
        persist: bool = False,
    ) -> None:
        queue = self._sanitize_queue(queue)
        if not queue:
            self._apply_uniform_queue(target)
            return
        queue = pad_queue_to_target(queue, target, self._frame_count)
        self._controller.dataset.frames_to_analyze = target
        self._controller.dataset.gap = gap
        self._controller.set_gap(gap, queue)
        cache_key = self._scan_cache_key(target)
        if cache_key is not None:
            self._diverse_queue_cache[cache_key] = list(queue)
        if persist:
            self._persist_label_queue()
        self._refresh_ui()
        self._schedule_frame_refresh()

    def set_frame_reader(
        self,
        read_frame: Callable[[int], np.ndarray | None],
        frame_count: int,
    ) -> None:
        self._read_frame = read_frame
        self._frame_count = frame_count
        self._update_frames_controls_max()

    def is_background_work_running(self) -> bool:
        worker = self._queue_worker
        return worker is not None and worker.isRunning()

    def stop_background_work(self) -> None:
        worker = self._queue_worker
        if worker is None or not worker.isRunning():
            return
        worker.requestInterruption()
        for signal, slot in (
            (worker.unified_progress, self._on_unified_progress),
            (worker.queue_preview, self._on_queue_preview),
            (worker.finished_ok, self._on_queue_ready),
            (worker.failed, self._on_queue_failed),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass

    def reset_for_new_session(self) -> None:
        """Clear labels, canvas, queue, and caches when the session or video is unloaded."""
        self.stop_background_work()
        self._queue_worker = None
        self._diverse_scan_allowed = False
        self._read_frame = None
        self._frame_count = 0
        self._label_dir = None
        self._active_label_set_id = "human"
        self._active_label_set_display = "Human"
        self._session_name = None
        self._project_id = None
        self._video_id = None
        self._video_path = None
        self._video_dir = None
        self._pose_scan_cache = None
        self._scan_settings_hash = None
        self._thumb_cache.clear()
        self._diverse_queue_cache.clear()
        self._frame_refresh_attempt = 0
        self._pick_generation = 0
        self._active_pick_target = None
        self._pre_pick_queue_snapshot = None
        self._worker_pick_generation = 0
        self._worker_for_pick = False
        self._displayed_frame_index = None
        self._outside_crop_frames = set()
        self._outside_crop_point_count = 0
        self._outside_crop_points_by_frame = {}
        self._outside_crop_warnings_dirty = False
        self._review_mode = False
        self._outlier_frames = set()
        self._outlier_reasons = {}
        self._outlier_bodyparts = {}
        self._outlier_bones = {}
        self._outlier_sorted = []
        self._labeling_tools.setVisible(True)
        self._strip.set_review_mode(False)
        self._strip.set_outlier_frames(set())
        self._hide_scan_progress()
        self._update_frames_controls_max()

        ds = LabelDataset(schema=canonical_lab_schema())
        self._controller.load_dataset(ds, [])
        self._canvas.set_crop_frame(None)
        self._canvas.set_fish_outline(None)
        self._canvas.set_display_points({}, None)
        self._canvas.set_display_bones([])
        self._canvas.set_ghost_point(None)
        self._strip.clear_thumbnail_cache()
        self._strip.set_queue([], 0, "", frame_count=1)
        self._pick_frames_btn.setEnabled(False)

    @property
    def active_label_set_id(self) -> str:
        return self._active_label_set_id

    @property
    def active_label_set_display(self) -> str:
        return self._active_label_set_display

    def labeled_counts(self) -> dict[str, int]:
        """Labeled frames/points for the active label set."""
        ds = self._controller.dataset
        labeled_frames = ds.count_frames_with_any_point()
        total_frames = max(self._frame_count, 1)
        bps = ds.bodyparts()
        labeled_points = sum(ds.count_for_bodypart(bp) for bp in bps)
        queue_len = len(self._controller.frame_queue) or total_frames
        total_points = len(bps) * queue_len if bps else 0
        return {
            "labeled_frames": labeled_frames,
            "total_frames": total_frames,
            "labeled_points": labeled_points,
            "total_points": total_points,
        }

    def set_label_directory(
        self,
        label_dir: Path,
        *,
        label_set_id: str,
        display_name: str,
    ) -> None:
        """Switch the active label set directory and reload labels."""
        self._label_dir = label_dir
        self._active_label_set_id = label_set_id
        self._active_label_set_display = display_name
        self._displayed_frame_index = None
        self._thumb_cache.clear()
        self._diverse_queue_cache.clear()
        self._reload_label_dataset()
        self._pick_frames_btn.setEnabled(
            self._diverse_scan_allowed and not self._review_mode and self._frame_count > 0
        )

    @property
    def review_mode(self) -> bool:
        return self._review_mode

    def set_review_mode(self, enabled: bool) -> None:
        """Toggle full-video review (no queue / unique detect) with outlier QC."""
        enabled = bool(enabled)
        if enabled == self._review_mode:
            return
        self._review_mode = enabled
        self._labeling_tools.setVisible(not enabled)
        self._strip.set_review_mode(enabled)
        if not enabled:
            self._heatmap_view_enabled = False
            self._canvas.set_heatmap_overlay(None, visible=False)
            if self._label_scene is not None:
                self._label_scene.set_view_heatmap(False)
        self._pick_frames_btn.setEnabled(
            self._diverse_scan_allowed and not enabled and self._frame_count > 0
        )
        if enabled:
            self._outside_crop_warnings_dirty = False
            self._apply_review_queue()
        else:
            self._outlier_frames = set()
            self._outlier_reasons = {}
            self._outlier_bodyparts = {}
            self._outlier_bones = {}
            self._outlier_sorted = []
            self._strip.set_outlier_frames(set())
            self._reload_label_dataset()

    def jump_outlier(self, direction: int) -> None:
        if not self._review_mode or not self._outlier_sorted:
            return
        cur = self._controller.current_frame_index()
        if direction > 0:
            nxt = next((f for f in self._outlier_sorted if f > cur), None)
            nxt = nxt if nxt is not None else self._outlier_sorted[0]
        else:
            prev = [f for f in self._outlier_sorted if f < cur]
            nxt = prev[-1] if prev else self._outlier_sorted[-1]
        self._controller.go_to_absolute_frame(nxt)
        self._frame_refresh_attempt = 0
        self._refresh_ui()
        self._schedule_frame_refresh()

    def _recompute_outliers(self) -> None:
        if not self._review_mode or self._frame_count <= 0:
            self._outlier_frames = set()
            self._outlier_reasons = {}
            self._outlier_bodyparts = {}
            self._outlier_bones = {}
            self._outlier_sorted = []
            self._strip.set_outlier_frames(set())
            return
        result = detect_pose_outlier_frames(
            self._controller.dataset,
            self._frame_count,
        )
        self._outlier_frames = result.frames
        self._outlier_reasons = result.reasons
        self._outlier_bodyparts = result.bodyparts
        self._outlier_bones = result.bones
        self._outlier_sorted = sorted(result.frames)
        self._strip.set_outlier_frames(result.frames)

    def _apply_review_queue(self) -> None:
        if self._frame_count <= 0:
            return
        queue = list(range(self._frame_count))
        ds = self._controller.dataset
        self._controller.load_dataset(ds, queue)
        start = _first_labeled_frame(ds)
        if start is None:
            start = 0
        self._controller.go_to_absolute_frame(start)
        self._recompute_outliers()
        self._refresh_ui()
        self._schedule_frame_refresh()

    def _reload_label_dataset(self) -> None:
        if self._label_dir is None:
            return
        from core.pose.labeling.named_label_sets import load_dataset_from_dir

        try:
            ds = load_dataset_from_dir(self._label_dir)
        except FileNotFoundError:
            ds = load_labels(self._label_dir)
        max_f = self._max_frames_setting()
        frame_count = self._frame_count
        if ds.frames_to_analyze <= 0 and frame_count > 0:
            ds.frames_to_analyze = target_label_frame_count(frame_count, ds.gap)
        target = frames_to_analyze_cap(frame_count, ds.frames_to_analyze, max_f)
        ds.frames_to_analyze = target
        ds.gap = gap_from_frames_to_analyze(frame_count, target)
        self._sync_frames_controls(target)
        restored = self._restore_saved_queue(ds, target)
        if self._review_mode:
            self._controller.load_dataset(ds, [])
            self._apply_review_queue()
            return
        if restored:
            restored = pad_queue_to_target(restored, target, frame_count)
            self._controller.load_dataset(ds, restored)
            cache_key = self._scan_cache_key(target)
            if cache_key is not None:
                self._diverse_queue_cache[cache_key] = list(restored)
            self._refresh_ui()
            self._schedule_frame_refresh()
        else:
            self._controller.load_dataset(ds, [])
            self._apply_uniform_queue(target)

    def load_video_context(
        self,
        *,
        session_name: str,
        project_id: str,
        video_id: str,
        arena: ArenaConfig,
        blob_params: BlobParams,
        frame_count: int,
        video_path: Path | None = None,
        video_dir: Path | None = None,
    ) -> None:
        self._video_id = video_id
        self._session_name = session_name
        self._project_id = project_id
        self._arena = arena
        self._blob_params = blob_params
        self._frame_count = frame_count
        self._video_path = video_path
        self._video_dir = video_dir
        self._update_frames_controls_max()
        self._scan_settings_hash = scan_settings_hash(arena, blob_params)
        self._pose_scan_cache = None
        self._invalidate_crop_display()
        if (
            video_dir is not None
            and video_path is not None
            and video_path.is_file()
            and frame_count > 0
        ):
            self._pose_scan_cache = load_pose_scan_cache(
                video_dir,
                frame_count=frame_count,
                video_path=video_path,
                arena=arena,
                blob_params=blob_params,
                load_fingerprints=False,
            )
        self._pick_frames_btn.setEnabled(self._diverse_scan_allowed and frame_count > 0)
        self._refresh_heatmap_archive()

    def _refresh_heatmap_archive(self) -> None:
        from core.pose.inference.heatmap_store import list_heatmap_archives

        self._heatmap_archives = []
        self._heatmap_archive_dir = None
        if self._session_name and self._project_id and self._video_id:
            self._heatmap_archives = list_heatmap_archives(
                self._session_name,
                self._project_id,
                self._video_id,
            )
            if self._heatmap_archives:
                self._heatmap_archive_dir = self._heatmap_archives[0].path
        if self._label_scene is not None:
            items = [(arch.key, arch.label) for arch in self._heatmap_archives]
            self._label_scene.set_heatmap_archives(items)
        available = self._heatmap_archive_dir is not None
        if not available:
            self._heatmap_view_enabled = False
            self._canvas.set_heatmap_overlay(None, visible=False)

    def _on_heatmap_archive_changed(self, archive_key: str) -> None:
        for arch in self._heatmap_archives:
            if arch.key == archive_key:
                self._heatmap_archive_dir = arch.path
                break
        self._refresh_heatmap_overlay()

    def _on_heatmap_view_changed(self, enabled: bool) -> None:
        self._heatmap_view_enabled = bool(enabled)
        if self._label_scene is not None:
            self._on_photo_opacity_changed(self._label_scene.photo_opacity_slider.value())
            self._on_points_opacity_changed(self._label_scene.points_opacity_slider.value())
            self._on_heatmap_opacity_changed(self._label_scene.heatmap_opacity_slider.value())
        self._refresh_heatmap_overlay()

    def _on_photo_opacity_changed(self, value: int) -> None:
        self._canvas.set_layer_opacities(photo=value / 100.0)

    def _on_points_opacity_changed(self, value: int) -> None:
        self._canvas.set_layer_opacities(points=value / 100.0)

    def _on_heatmap_opacity_changed(self, value: int) -> None:
        self._canvas.set_layer_opacities(heatmap=value / 100.0)

    def _refresh_heatmap_overlay(self) -> None:
        if not self._review_mode or not self._heatmap_view_enabled:
            self._canvas.set_heatmap_overlay(None, visible=False)
            return
        ctrl = self._controller
        bodypart = ctrl.active_bodypart
        if (
            bodypart is None
            or self._heatmap_archive_dir is None
        ):
            self._canvas.set_heatmap_overlay(None, visible=False)
            return
        crop, _blob = self._current_crop()
        if crop is None or crop.size == 0:
            self._canvas.set_heatmap_overlay(None, visible=False)
            return
        from core.pose.inference.heatmap_store import load_heatmaps_for_frame

        fi = ctrl.current_frame_index()
        maps = load_heatmaps_for_frame(
            self._heatmap_archive_dir,
            fi,
            crop_h=crop.shape[0],
            crop_w=crop.shape[1],
        )
        hm = maps.get(bodypart) if maps else None
        self._canvas.set_heatmap_overlay(hm, visible=hm is not None)

    def update_tracking_params(
        self,
        arena: ArenaConfig,
        blob_params: BlobParams,
    ) -> None:
        """Lightweight arena/blob update while adjusting sliders (no dataset reload)."""
        new_hash = scan_settings_hash(arena, blob_params)
        if self._scan_settings_hash and new_hash != self._scan_settings_hash:
            self._pose_scan_cache = None
            self._diverse_queue_cache.clear()
            self._invalidate_crop_display()
        self._scan_settings_hash = new_hash
        self._arena = arena
        self._blob_params = blob_params

    def _invalidate_crop_display(self) -> None:
        """Force crop image + strip thumbs to rebuild after arena/blob change."""
        self._thumb_cache.clear()
        self._strip.clear_thumbnail_cache()
        self._displayed_frame_index = None
        self._displayed_settings_hash = None
        self._crop_cache_key = None
        self._crop_cache = None
        self._outside_crop_warnings_dirty = True

    def _crop_for_labeled_frame(self, frame_index: int) -> BlobResult | None:
        if self._read_frame is None:
            return None
        frame = self._read_frame(int(frame_index))
        if frame is None:
            return None
        return detect_blob_square_crop(frame, self._arena, self._blob_params)

    def _outside_points_on_frame(
        self,
        frame_index: int,
        blob: BlobResult | None,
    ) -> int:
        fl = self._controller.dataset.frames.get(int(frame_index))
        if fl is None:
            return 0
        count = 0
        for xy in fl.points.values():
            if xy is None:
                continue
            if blob is None or not blob.found or not point_inside_square_crop(
                xy[0], xy[1], blob
            ):
                count += 1
        return count

    def _update_outside_warning_for_frame(
        self,
        frame_index: int,
        blob: BlobResult | None,
    ) -> None:
        """Cheap per-frame update — uses the current frame blob only."""
        fi = int(frame_index)
        prev = self._outside_crop_points_by_frame.pop(fi, 0)
        self._outside_crop_point_count = max(0, self._outside_crop_point_count - prev)
        self._outside_crop_frames.discard(fi)

        count = self._outside_points_on_frame(fi, blob)
        if count > 0:
            self._outside_crop_points_by_frame[fi] = count
            self._outside_crop_point_count += count
            self._outside_crop_frames.add(fi)
        self._strip.set_outside_crop_frames(self._outside_crop_frames)

    def _recompute_outside_crop_warnings(self) -> tuple[int, int]:
        labeled = sorted(
            fi
            for fi, fl in self._controller.dataset.frames.items()
            if any(xy is not None for xy in fl.points.values())
        )
        self._outside_crop_frames = set()
        self._outside_crop_point_count = 0
        self._outside_crop_points_by_frame = {}
        if not labeled:
            self._strip.set_outside_crop_frames(set())
            self._outside_crop_warnings_dirty = False
            return 0, 0

        outside_frames: set[int] = set()
        outside_points = 0
        for fi in labeled:
            blob = self._crop_for_labeled_frame(fi)
            count = self._outside_points_on_frame(fi, blob)
            if count > 0:
                outside_frames.add(fi)
                outside_points += count
                self._outside_crop_points_by_frame[fi] = count
        self._outside_crop_frames = outside_frames
        self._outside_crop_point_count = outside_points
        self._strip.set_outside_crop_frames(outside_frames)
        self._outside_crop_warnings_dirty = False
        return outside_points, len(outside_frames)

    def refresh_outside_crop_warnings(
        self,
        *,
        crops_by_frame: dict[int, BlobResult] | None = None,
    ) -> tuple[int, int]:
        """
        Re-scan labeled frames for points outside the current square crop.

        Labels are kept; orange dots on the timeline mark affected frames.
        Returns ``(outside_point_count, outside_frame_count)``.
        """
        self._invalidate_crop_display()
        if crops_by_frame is not None:
            def crop_for_frame(fi: int) -> BlobResult | None:
                return crops_by_frame.get(int(fi))
        else:
            crop_for_frame = self._crop_for_labeled_frame

        labeled = sorted(
            fi
            for fi, fl in self._controller.dataset.frames.items()
            if any(xy is not None for xy in fl.points.values())
        )
        if not labeled:
            self._outside_crop_frames = set()
            self._outside_crop_point_count = 0
            self._outside_crop_points_by_frame = {}
            self._strip.set_outside_crop_frames(set())
            self._outside_crop_warnings_dirty = False
            self.refresh_display()
            return 0, 0

        outside_frames: set[int] = set()
        outside_points = 0
        self._outside_crop_points_by_frame = {}
        for fi in labeled:
            blob = crop_for_frame(fi)
            count = self._outside_points_on_frame(fi, blob)
            if count > 0:
                outside_frames.add(fi)
                outside_points += count
                self._outside_crop_points_by_frame[fi] = count
        self._outside_crop_frames = outside_frames
        self._outside_crop_point_count = outside_points
        self._outside_crop_warnings_dirty = False
        self._strip.set_outside_crop_frames(outside_frames)
        self.refresh_display()
        return outside_points, len(outside_frames)

    def remap_labels_to_current_crops(
        self,
        *,
        crops_by_frame: dict[int, BlobResult] | None = None,
    ) -> tuple[int, int]:
        """Legacy name — warns without deleting labels outside the new crop."""
        return self.refresh_outside_crop_warnings(crops_by_frame=crops_by_frame)

    def _lookup_cached_queue(self, target: int) -> list[int] | None:
        """Return a cached diverse queue if one exists — never builds on the UI thread."""
        if self._pose_scan_cache is None or self._frame_count <= 0:
            return None
        cached = self._pose_scan_cache.queues_by_target.get(target)
        if cached is not None:
            return list(cached)
        gap = self._gap_for_target(target)
        cached = self._pose_scan_cache.queues_by_gap.get(gap)
        if cached is not None:
            return list(cached)
        if (
            self._pose_scan_cache.last_queue
            and self._pose_scan_cache.last_frames_to_analyze == target
        ):
            return list(self._pose_scan_cache.last_queue)
        return None

    def _scan_cache_has_fingerprints(self) -> bool:
        if self._pose_scan_cache is None:
            self._reload_pose_scan_cache(load_fingerprints=False)
        if self._pose_scan_cache is None:
            return False
        if self._pose_scan_cache.fingerprints_loaded:
            return any(fp is not None for fp in self._pose_scan_cache.fingerprints)
        if self._video_dir is None:
            return False
        return (self._video_dir / "pose_scan_cache.npz").is_file()

    def _reload_pose_scan_cache(self, *, load_fingerprints: bool = False) -> None:
        if (
            self._video_dir is None
            or self._video_path is None
            or not self._video_path.is_file()
            or self._frame_count <= 0
        ):
            self._pose_scan_cache = None
            return
        self._pose_scan_cache = load_pose_scan_cache(
            self._video_dir,
            frame_count=self._frame_count,
            video_path=self._video_path,
            arena=self._arena,
            blob_params=self._blob_params,
            load_fingerprints=load_fingerprints,
        )

    def set_diverse_scan_allowed(self, allowed: bool) -> None:
        """When True and the Label tab is visible, diverse picking is available."""
        self._diverse_scan_allowed = allowed and not self._review_mode
        self._pick_frames_btn.setEnabled(
            self._diverse_scan_allowed and not self._review_mode and self._frame_count > 0
        )
        if allowed and not self._review_mode:
            self.refresh_display()
            # Tab just shown — viewport may have been 0×0 during Update-for-all crop swap.
            QTimer.singleShot(0, self._canvas.ensure_view_fitted)
            QTimer.singleShot(50, self._canvas.ensure_view_fitted)
        elif allowed and self._review_mode:
            QTimer.singleShot(0, self._canvas.ensure_view_fitted)
            QTimer.singleShot(50, self._canvas.ensure_view_fitted)

    def _scan_cache_key(self, target: int) -> tuple | None:
        if self._video_path is None:
            return None
        return (str(self._video_path), self._frame_count, target)

    def start_diverse_queue_scan_if_needed(self, *, force: bool = False) -> None:
        target = self._target_frames_value()
        if not self._diverse_scan_allowed:
            return
        if self._video_path is None or not self._video_path.is_file():
            return
        if self._frame_count <= 0:
            return
        gap = self._gap_for_target(target)
        if gap <= 0:
            self._apply_uniform_queue(target)
            return
        if not force:
            saved_queue = self._sanitize_queue(self._controller.dataset.label_frame_queue)
            if (
                saved_queue
                and saved_queue == self._sanitize_queue(self._controller.frame_queue)
                and self._controller.dataset.frames_to_analyze == target
            ):
                self._hide_scan_progress()
                return
            cache_key = self._scan_cache_key(target)
            if cache_key is not None:
                cached = self._diverse_queue_cache.get(cache_key)
                if cached is not None:
                    self._hide_scan_progress()
                    self._apply_frame_queue(target, gap, cached)
                    return
            disk_queue = self._lookup_cached_queue(target)
            if disk_queue is not None:
                self._hide_scan_progress()
                self._apply_frame_queue(target, gap, disk_queue, persist=True)
                return
            build_from_disk_cache = self._scan_cache_has_fingerprints()
        else:
            build_from_disk_cache = False
        self._start_diverse_queue_scan(target, build_from_disk_cache=build_from_disk_cache)

    def _apply_uniform_queue(self, target: int) -> None:
        """Fast stride-based queue; used until a diverse scan finishes or is skipped."""
        if self._frame_count <= 0:
            return
        gap = self._gap_for_target(target)
        self._controller.dataset.frames_to_analyze = target
        self._controller.dataset.gap = gap
        queue = build_label_frame_queue(self._frame_count, gap, target=target)
        self._controller.set_gap(gap, queue)
        self._controller.go_to_queue_index(0)
        self._refresh_ui()

    def start_pose_fingerprint_scan_if_needed(self) -> None:
        """One-time background scan that saves blob-shape fingerprints to disk."""
        if self._video_path is None or not self._video_path.is_file():
            return
        if self._frame_count <= 0:
            return
        if self._scan_cache_has_fingerprints():
            return
        if self._queue_worker is not None and self._queue_worker.isRunning():
            return
        # Fingerprints are independent of the current target count — always scan.
        target = self._target_frames_value()
        self._start_diverse_queue_scan(
            target,
            build_from_disk_cache=False,
            save_fingerprints=True,
            for_pick=False,
        )

    def _start_diverse_queue_scan(
        self,
        target: int,
        *,
        build_from_disk_cache: bool = False,
        save_fingerprints: bool = True,
        for_pick: bool = True,
    ) -> None:
        if self._frame_count <= 0 or self._video_path is None:
            return
        gap = self._gap_for_target(target)
        # Picking every frame needs no diversity pass; fingerprint-only scans still run
        # so Detect Unique Frames works after the user lowers the target.
        if gap <= 0 and for_pick:
            self._apply_uniform_queue(target)
            self._active_pick_target = None
            self._hide_scan_progress()
            return

        if build_from_disk_cache:
            self._scan_status.setText("Building diverse frame queue from cache…")
        else:
            self._scan_status.setText("Scanning video for distinct poses…")
        self._scan_status.show()
        if not build_from_disk_cache:
            self._scan_progress.setValue(0)
        self._scan_progress.show()
        self._pick_frames_btn.setEnabled(False)
        self.stop_background_work()

        self._worker_for_pick = for_pick
        if for_pick:
            self._worker_pick_generation = self._pick_generation
        # Fingerprint-only with target covering the whole video still needs a positive
        # frames_to_analyze for the worker; use frame_count so gap resolves to 0 and the
        # adaptive scanner densifies (coarse stride 1) while saving fingerprints.
        worker_target = target if gap > 0 else max(1, self._frame_count)
        self._queue_worker = LabelFrameQueueWorker(
            self._video_dir or self._video_path.parent,
            self._video_path,
            self._frame_count,
            worker_target,
            self._arena,
            self._blob_params,
            build_from_disk_cache=build_from_disk_cache,
            save_fingerprints=save_fingerprints,
        )
        self._queue_worker.unified_progress.connect(self._on_unified_progress)
        self._queue_worker.queue_preview.connect(self._on_queue_preview)
        self._queue_worker.finished_ok.connect(self._on_queue_ready)
        self._queue_worker.failed.connect(self._on_queue_failed)
        self._queue_worker.start()

    def _rebuild_frame_queue(self, target: int, *, force: bool = False) -> None:
        self._diverse_queue_cache.clear()
        if force:
            self._controller.dataset.label_frame_queue = []
        self._apply_uniform_queue(target)
        if not self._diverse_scan_allowed:
            self._active_pick_target = None
            return
        if self._gap_for_target(target) <= 0:
            self._active_pick_target = None
            return
        has_fp = self._scan_cache_has_fingerprints()
        self._start_diverse_queue_scan(
            target,
            build_from_disk_cache=has_fp,
            save_fingerprints=not has_fp,
            for_pick=True,
        )

    def _hide_scan_progress(self) -> None:
        self._scan_status.hide()
        self._scan_progress.hide()
        self._pick_frames_btn.setEnabled(self._diverse_scan_allowed and self._frame_count > 0)

    def _on_unified_progress(self, value: int, total: int, label: str) -> None:
        self._scan_status.setText(label)
        self._scan_status.show()
        self._scan_progress.show()
        if total > 0 and value >= 0:
            self._scan_progress.setMaximum(total)
            self._scan_progress.setValue(min(value, total))

    def _on_queue_preview(self, queue: list) -> None:
        if not self._worker_for_pick:
            return
        if self._active_pick_target is None:
            return
        if self._worker_pick_generation != self._pick_generation:
            return
        self._strip.set_live_queue(queue, frame_count=self._frame_count)

    def _emit_background_work_finished(self) -> None:
        if not self.is_background_work_running():
            self.background_work_finished.emit()

    def _snapshot_queue_state(self) -> dict:
        return {
            "queue": list(self._controller.frame_queue),
            "gap": self._controller.dataset.gap,
            "frames_to_analyze": self._controller.dataset.frames_to_analyze,
            "label_frame_queue": list(self._controller.dataset.label_frame_queue),
            "queue_index": self._controller.queue_index,
        }

    def _restore_queue_snapshot(self, snap: dict) -> None:
        self._controller.dataset.gap = int(snap["gap"])
        self._controller.dataset.frames_to_analyze = int(snap["frames_to_analyze"])
        self._controller.dataset.label_frame_queue = list(snap["label_frame_queue"])
        self._controller.set_gap(int(snap["gap"]), list(snap["queue"]))
        self._controller.go_to_queue_index(int(snap["queue_index"]))
        self._sync_frames_controls(int(snap["frames_to_analyze"]))
        self._refresh_ui()
        self._schedule_frame_refresh()

    def _labeled_frame_indices_outside_queue(self, queue: list[int]) -> list[int]:
        keep = {int(fi) for fi in queue}
        orphaned: list[int] = []
        for fi, fl in self._controller.dataset.frames.items():
            if int(fi) not in keep and any(xy is not None for xy in fl.points.values()):
                orphaned.append(int(fi))
        return sorted(orphaned)

    def _prune_labels_outside_queue(self, queue: list[int]) -> None:
        keep = {int(fi) for fi in queue}
        for fi in list(self._controller.dataset.frames.keys()):
            if int(fi) not in keep:
                self._controller.dataset.frames.pop(int(fi), None)

    def _confirm_orphan_label_removal(self) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Pose Studio")
        box.setText("Old labeled frames not detected will be removed. Are you sure?")
        continue_btn = box.addButton("Continue", QMessageBox.AcceptRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(cancel_btn)
        box.exec_()
        return box.clickedButton() == continue_btn

    def _finalize_pick_queue(
        self,
        target: int,
        gap: int,
        queue: list[int],
        *,
        orphaned: list[int],
    ) -> None:
        sanitized = pad_queue_to_target(self._sanitize_queue(queue), target, self._frame_count)
        cache_key = self._scan_cache_key(target)
        if cache_key is not None:
            self._diverse_queue_cache[cache_key] = list(sanitized)
        self._reload_pose_scan_cache(load_fingerprints=False)
        if orphaned:
            self._prune_labels_outside_queue(sanitized)
        self._apply_frame_queue(target, gap, sanitized, persist=True)
        self._pre_pick_queue_snapshot = None
        self._active_pick_target = None

    def _cancel_pick_queue(self) -> None:
        snap = self._pre_pick_queue_snapshot
        if snap is not None:
            self._restore_queue_snapshot(snap)
        self._pre_pick_queue_snapshot = None
        self._active_pick_target = None

    def _on_queue_ready(self, queue: list) -> None:
        if self._worker_for_pick:
            if self._worker_pick_generation != self._pick_generation:
                return
            self._hide_scan_progress()
            target = self._active_pick_target
            if target is None:
                self._reload_pose_scan_cache(load_fingerprints=False)
                self._emit_background_work_finished()
                return
            gap = self._gap_for_target(target)
            sanitized = pad_queue_to_target(
                self._sanitize_queue(queue), target, self._frame_count
            )
            orphaned = self._labeled_frame_indices_outside_queue(sanitized)
            if orphaned and not self._confirm_orphan_label_removal():
                self._cancel_pick_queue()
                self._emit_background_work_finished()
                return
            self._finalize_pick_queue(target, gap, sanitized, orphaned=orphaned)
            self._emit_background_work_finished()
            return

        # Fingerprint-only scan finished — always reload cache (do not gate on pick generation).
        self._hide_scan_progress()
        self._reload_pose_scan_cache(load_fingerprints=False)
        pending = self._active_pick_target
        if (
            pending is not None
            and self._diverse_scan_allowed
            and self._gap_for_target(pending) > 0
            and self._scan_cache_has_fingerprints()
        ):
            self._start_diverse_queue_scan(
                pending,
                build_from_disk_cache=True,
                save_fingerprints=False,
                for_pick=True,
            )
            return
        self._emit_background_work_finished()

    def _on_queue_failed(self, msg: str) -> None:
        if not self._worker_for_pick:
            self._hide_scan_progress()
            self._emit_background_work_finished()
            return
        if self._worker_pick_generation != self._pick_generation:
            return
        self._hide_scan_progress()
        target = self._active_pick_target or self._target_frames_value()
        gap = self._gap_for_target(target)
        queue = build_label_frame_queue(self._frame_count, gap, target=target)
        self._apply_frame_queue(target, gap, queue)
        self._active_pick_target = None
        QMessageBox.warning(
            self,
            "Pose Studio",
            f"Pose scan failed; using uniform spacing.\n{msg}",
        )
        self._emit_background_work_finished()

    def _on_frames_preview(self, value: int) -> None:
        """Slider drag — update spinbox only."""
        if self._frames_spin.value() != value:
            self._frames_spin.blockSignals(True)
            self._frames_spin.setValue(value)
            self._frames_spin.blockSignals(False)

    def _on_frames_spin_changed(self, value: int) -> None:
        """Spinbox edit — keep slider in sync without rebuilding the queue."""
        capped = min(value, self._frames_slider.maximum())
        if self._frames_slider.value() != capped:
            self._frames_slider.blockSignals(True)
            self._frames_slider.setValue(capped)
            self._frames_slider.blockSignals(False)

    def _on_pick_analysis_frames(self) -> None:
        if self._frame_count <= 0:
            QMessageBox.warning(self, "Pose Studio", "Open a video before picking frames.")
            return
        if not self._diverse_scan_allowed:
            QMessageBox.warning(
                self,
                "Pose Studio",
                "Confirm the arena on the Select Crop tab before detecting unique frames.",
            )
            return
        target = self._target_frames_value()
        self._sync_frames_controls(target)
        self._pick_generation += 1
        self._pre_pick_queue_snapshot = self._snapshot_queue_state()
        self._active_pick_target = target
        self._rebuild_frame_queue(target, force=True)

    def _on_bodypart_renamed(self, old_name: str, new_name: str) -> None:
        if not self._controller.rename_bodypart(old_name, new_name):
            QMessageBox.warning(
                self,
                "Pose Studio",
                f"Could not rename '{old_name}' to '{new_name}' (duplicate or invalid name).",
            )
            return
        self._save_labels(silent=True)

    def _on_bodypart_removed(self, name: str) -> None:
        if not self._controller.remove_bodypart(name):
            QMessageBox.warning(self, "Pose Studio", f"Could not remove '{name}'.")
            return
        self._save_labels(silent=True)

    def _on_bone_pair(self, a: str, b: str) -> None:
        if not self._controller.add_bone(a, b):
            self._bodypart_list.clear_bone_pick()
            return
        self._save_labels(silent=True)

    def _on_bone_removed(self, a: str, b: str) -> None:
        if not self._controller.remove_bone(a, b):
            return
        self._save_labels(silent=True)

    def _on_bodypart_reordered(self, name: str, target_index: int) -> None:
        if not self._controller.reorder_bodypart(name, target_index):
            return
        self._save_labels(silent=True)

    def _on_point_placed(self, x: float, y: float) -> None:
        fx, fy = self._crop_to_full(x, y)
        self._controller.place_active_point(fx, fy)
        self._save_labels(silent=True)
        if self._review_mode:
            self._recompute_outliers()

    def _on_auto_next_toggled(self, checked: bool) -> None:
        self._controller.set_auto_advance_frames(checked)

    def _on_point_delete_requested(self) -> None:
        if not self._controller.delete_active_point():
            return
        self._save_labels(silent=True)
        if self._review_mode:
            self._recompute_outliers()

    def _on_point_moved(self, bodypart: str, x: float, y: float) -> None:
        fx, fy = self._crop_to_full(x, y)
        self._controller.move_point(bodypart, fx, fy)
        self._save_labels(silent=True)
        if self._review_mode:
            self._recompute_outliers()

    def _on_drag_started(self, _bodypart: str) -> None:
        self._controller.begin_point_move()

    def _on_add_point_at(self, x: float, y: float) -> None:
        name = self._controller.next_default_point_name()
        fx, fy = self._crop_to_full(x, y)
        self._controller.place_new_point_at(name, fx, fy)

    def _on_strip_frame(self, frame_index: int) -> None:
        try:
            qi = self._controller.frame_queue.index(frame_index)
            self._controller.go_to_queue_index(qi)
        except ValueError:
            pass
        self._frame_refresh_attempt = 0
        self._schedule_frame_refresh()

    def _crop_to_full(self, x: float, y: float) -> tuple[float, float]:
        frame = self._current_frame_bgr()
        if frame is None:
            return x, y
        blob = detect_blob_square_crop(frame, self._arena, self._blob_params)
        return crop_to_full_frame(x, y, blob)

    def _current_frame_bgr(self) -> np.ndarray | None:
        if self._read_frame is None:
            return None
        return self._read_frame(self._controller.current_frame_index())

    def _current_crop(self) -> tuple[np.ndarray | None, BlobResult | None]:
        fi = self._controller.current_frame_index()
        cache_key = (fi, self._scan_settings_hash)
        if cache_key == self._crop_cache_key and self._crop_cache is not None:
            return self._crop_cache
        frame = self._current_frame_bgr()
        if frame is None:
            self._crop_cache_key = cache_key
            self._crop_cache = (None, None)
            return self._crop_cache
        blob = detect_blob_square_crop(frame, self._arena, self._blob_params)
        if not blob.found:
            self._crop_cache_key = cache_key
            self._crop_cache = (None, blob)
            return self._crop_cache
        crop = extract_square_crop(frame, blob)
        self._crop_cache_key = cache_key
        self._crop_cache = (crop, blob)
        return self._crop_cache

    def _refresh_ui(self) -> None:
        if self._outside_crop_warnings_dirty and not self._review_mode:
            self._recompute_outside_crop_warnings()

        ctrl = self._controller
        names = ctrl.dataset.bodyparts()
        counts = {n: ctrl.dataset.count_for_bodypart(n) for n in names}
        qlen = self._frame_count if self._review_mode else len(ctrl.frame_queue)
        self._bodypart_list.set_bodyparts(
            names,
            counts,
            qlen,
            selected_name=ctrl.active_bodypart,
        )
        self._bodypart_list.set_bones(ctrl.bone_name_pairs())
        self._bodypart_list.set_add_point_mode(ctrl.add_point_mode)
        self._bodypart_list.set_bone_mode(ctrl.bone_mode)

        crop, blob = self._current_crop()
        fi = ctrl.current_frame_index()
        settings_hash = self._scan_settings_hash
        crop_changed = (
            fi != self._displayed_frame_index
            or settings_hash != getattr(self, "_displayed_settings_hash", None)
        )
        if crop is None or crop.size == 0:
            self._canvas.set_crop_frame(None)
            self._displayed_frame_index = None
            self._displayed_settings_hash = settings_hash
        elif crop_changed:
            self._canvas.set_crop_frame(
                crop,
                reset_view=self._displayed_frame_index is None,
            )
            self._displayed_frame_index = fi
            self._displayed_settings_hash = settings_hash
        if blob is not None and blob.found and crop_changed:
            self._canvas.set_fish_outline(fish_mask_in_crop(blob))
        elif blob is None or not blob.found:
            if crop_changed:
                self._canvas.set_fish_outline(None)
        self._canvas.set_add_point_mode(ctrl.add_point_mode)
        points_crop: dict[str, tuple[float, float] | None] = {}
        if blob is not None and blob.found:
            for name in ctrl.dataset.bodyparts():
                xy = ctrl.dataset.get_point(fi, name)
                if xy is not None:
                    points_crop[name] = full_frame_to_crop(xy[0], xy[1], blob)
        self._canvas.set_display_points(points_crop, ctrl.active_bodypart)
        self._refresh_heatmap_overlay()
        outside_names: set[str] = set()
        if blob is not None and blob.found:
            for name in ctrl.dataset.bodyparts():
                xy_full = ctrl.dataset.get_point(fi, name)
                if xy_full is not None and not point_inside_square_crop(
                    xy_full[0], xy_full[1], blob
                ):
                    outside_names.add(name)
        elif fi in self._outside_crop_frames:
            for name in ctrl.dataset.bodyparts():
                if ctrl.dataset.get_point(fi, name) is not None:
                    outside_names.add(name)
        if self._review_mode:
            self._canvas.set_outlier_highlight(
                self._outlier_bodyparts.get(fi, set()),
                self._outlier_bones.get(fi, set()),
            )
        else:
            self._canvas.set_outlier_highlight(outside_names, [])
        self._canvas.set_display_bones(ctrl.bone_name_pairs())
        self._canvas.set_ghost_point(self._ghost_point_crop(ctrl, blob))
        self._update_outside_warning_for_frame(fi, blob)
        self._strip.set_queue(
            ctrl.frame_queue,
            ctrl.queue_index,
            self._strip_progress_text(fi),
            frame_count=self._frame_count,
            thumbnail_for=self._frame_thumbnail,
        )
        if crop is None and self._read_frame is not None and self._frame_count > 0:
            self._schedule_frame_refresh()

    def _ghost_point_crop(
        self,
        ctrl: LabelingController,
        blob: BlobResult | None,
    ) -> tuple[float, float] | None:
        if not ctrl.active_bodypart or blob is None or not blob.found or ctrl.queue_index <= 0:
            return None
        for i in range(ctrl.queue_index - 1, -1, -1):
            prev_frame = ctrl.frame_queue[i]
            prev_xy = ctrl.dataset.get_point(prev_frame, ctrl.active_bodypart)
            if prev_xy is not None:
                return full_frame_to_crop(prev_xy[0], prev_xy[1], blob)
        return None

    def _strip_progress_text(self, frame_index: int) -> str:
        ctrl = self._controller
        if self._review_mode:
            total = max(self._frame_count, 1)
            text = f"Frame {frame_index} / {total - 1}"
            n_out = len(self._outlier_frames)
            if n_out:
                text += f"  ·  {n_out} outlier(s)"
            reasons = self._outlier_reasons.get(frame_index, [])
            if reasons:
                text += "  ·  " + "; ".join(reasons)
            return text
        text = f"Frame {frame_index}  ·  Queue {ctrl.progress_label()}"
        if self._outside_crop_point_count > 0:
            text += f"  ·  {self._outside_crop_point_count} outside crop"
        return text

    def _frame_thumbnail(self, frame_index: int) -> QPixmap | None:
        cached = self._thumb_cache.get(frame_index)
        if cached is not None:
            return cached
        if self._read_frame is None:
            return None
        frame = self._read_frame(frame_index)
        if frame is None or frame.size == 0:
            return None
        blob = detect_blob_square_crop(frame, self._arena, self._blob_params)
        if not blob.found:
            return None
        crop = extract_square_crop(frame, blob)
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        pix = QPixmap.fromImage(qimg)
        self._thumb_cache[frame_index] = pix
        return pix

    def apply_unique_reduce(self, keep_n: int) -> int:
        """
        Shrink the labeling queue to the ``keep_n`` most unique frames.

        Drops labels on frames removed from the queue. Returns how many frames remain.
        """
        if self._frame_count <= 0 or self._label_dir is None:
            return 0
        queue = self._sanitize_queue(list(self._controller.frame_queue))
        if not queue:
            return 0
        keep = max(1, min(int(keep_n), len(queue)))
        if keep >= len(queue):
            return len(queue)

        fingerprints: list = [None] * self._frame_count
        cache = None
        if (
            self._video_dir is not None
            and self._video_path is not None
            and self._video_path.is_file()
        ):
            cache = load_pose_scan_cache(
                self._video_dir,
                frame_count=self._frame_count,
                video_path=self._video_path,
                arena=self._arena,
                blob_params=self._blob_params,
                load_fingerprints=True,
            )
            if cache is not None and cache.fingerprints_loaded:
                fingerprints = list(cache.fingerprints)

        ranks = dict(getattr(cache, "queue_ranks", None) or {}) if cache else {}
        if ranks:
            new_queue = reduce_queue_using_ranks(
                queue, ranks, keep, fingerprints=fingerprints
            )
        else:
            new_queue = reduce_queue_by_uniqueness(fingerprints, queue, keep)
        if not new_queue:
            return len(queue)

        keep_set = set(new_queue)
        dropped = [fi for fi in queue if fi not in keep_set]
        ds = self._controller.dataset
        for fi in dropped:
            ds.frames.pop(int(fi), None)

        target = len(new_queue)
        gap = self._gap_for_target(target) if target else 1
        self._apply_frame_queue(target, gap, new_queue, persist=True)
        self._save_labels(silent=True)

        from core.pose.labeling.pose_scan_cache import save_pose_scan_cache

        kept_ranks = {int(fi): int(ranks[fi]) for fi in new_queue if fi in ranks}
        if not kept_ranks and any(fp is not None for fp in fingerprints):
            kept_ranks = rank_queue_by_uniqueness(fingerprints, new_queue)
        if (
            cache is not None
            and self._video_dir is not None
            and self._video_path is not None
        ):
            save_pose_scan_cache(
                self._video_dir,
                frame_count=self._frame_count,
                video_path=self._video_path,
                arena=self._arena,
                blob_params=self._blob_params,
                fingerprints=fingerprints,
                coarse_stride=getattr(cache, "coarse_stride", 1) or 1,
                queue=new_queue,
                frames_to_analyze=target,
                fingerprints_unchanged=True,
                queue_ranks=kept_ranks or None,
            )
        return len(new_queue)

    def _save_labels(self, silent: bool = False) -> None:
        if self._label_dir is None:
            return
        self._controller.dataset.label_frame_queue = list(self._controller.frame_queue)
        self._controller.dataset.frames_to_analyze = self._target_frames_value()
        self._controller.dataset.gap = self._gap_for_target(self._target_frames_value())
        save_labels(self._label_dir, self._controller.dataset)
        self.labels_changed.emit()
        if not silent:
            QMessageBox.information(self, "Pose Studio", "Labels saved.")
