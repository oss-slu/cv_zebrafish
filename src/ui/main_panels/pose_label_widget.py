"""Pose Studio — Step 3 labeling tab."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QShortcut,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app_platform.paths import human_labelled_dir
from app_platform.ui_preferences import UiPreferences
from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop
from core.pose.detection.crop import crop_to_full_frame, extract_square_crop, fish_mask_in_crop, full_frame_to_crop
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.labeling.labels_store import LabelDataset, load_labels, save_labels
from core.pose.labeling.frame_sampler import (
    build_label_frame_queue,
    frames_to_analyze_cap,
    gap_from_frames_to_analyze,
    pad_queue_to_target,
    target_label_frame_count,
)
from core.pose.labeling.scan_progress import PROGRESS_TOTAL
from core.pose.labeling.pose_scan_cache import (
    load_pose_scan_cache,
    scan_settings_hash,
)
from core.pose.dataset.retrain_loop import import_source_into_human
from core.pose.labeling.schema import default_lab_schema
from ui.components.pose.bodypart_label_list import BodypartLabelList
from ui.components.pose.label_canvas import LabelCanvas
from ui.components.pose.label_frame_strip import LabelFrameStrip
from ui.components.pose.labeling_controller import LabelingController
from ui.workers.label_frame_queue_worker import LabelFrameQueueWorker


class PoseLabelWidget(QWidget):
    """One bodypart × many frames on blob-centered square crop."""

    tracking_exported = pyqtSignal(str)
    background_work_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseLabelWidget")
        self._read_frame: Callable[[int], np.ndarray | None] | None = None
        self._frame_count = 0
        self._arena = ArenaConfig()
        self._blob_params = BlobParams()
        self._label_dir: Path | None = None
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
        self._worker_pick_generation = 0
        self._displayed_frame_index: int | None = None

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self._active_lbl = QLabel("Select a bodypart to label")
        self._active_lbl.setObjectName("SettingsHintLabel")
        top.addWidget(self._active_lbl, stretch=1)
        self._undo_btn = QPushButton("Undo")
        self._redo_btn = QPushButton("Redo")
        self._prev_btn = QPushButton("Prev")
        self._next_btn = QPushButton("Next")
        self._auto_next_cb = QCheckBox("Auto next frame")
        self._auto_next_cb.setChecked(True)
        self._auto_next_cb.setToolTip(
            "When on, placing a point advances to the next queue frame. "
            "When off, the frame stays put so you can adjust multiple points."
        )
        self._save_btn = QPushButton("Save labels")
        self._import_ai_btn = QPushButton("Import AI gaps")
        self._import_ai_btn.setToolTip(
            "Fill missing points from ai_labelled into this video's human labels."
        )
        self._export_btn = QPushButton("Export DLC CSV")
        for b in (
            self._undo_btn,
            self._redo_btn,
            self._prev_btn,
            self._next_btn,
            self._auto_next_cb,
            self._save_btn,
            self._import_ai_btn,
            self._export_btn,
        ):
            top.addWidget(b)
        root.addLayout(top)

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
            "Target number of frames to label. Press Pick Analysis Frames to apply."
        )
        self._frames_slider.valueChanged.connect(self._on_frames_preview)
        frames_row.addWidget(self._frames_slider, stretch=1)
        self._pick_frames_btn = QPushButton("Pick Analysis Frames")
        self._pick_frames_btn.setToolTip(
            "Build or rebuild the diverse frame queue for the target count above."
        )
        self._pick_frames_btn.clicked.connect(self._on_pick_analysis_frames)
        frames_row.addWidget(self._pick_frames_btn)
        root.addLayout(frames_row)

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
        root.addLayout(scan_row)

        mid = QSplitter(Qt.Horizontal)
        mid.setObjectName("PoseLabelSplitter")
        mid.setChildrenCollapsible(False)
        self._bodypart_list = BodypartLabelList()
        self._canvas = LabelCanvas()
        mid.addWidget(self._bodypart_list)
        mid.addWidget(self._canvas)
        mid.setStretchFactor(0, 0)
        mid.setStretchFactor(1, 1)
        mid.setSizes([BodypartLabelList.DEFAULT_WIDTH, 720])
        root.addWidget(mid, stretch=1)

        self._strip = LabelFrameStrip()
        root.addWidget(self._strip)

        self._bodypart_list.bodypart_selected.connect(self._controller.set_active_bodypart)
        self._bodypart_list.bodypart_renamed.connect(self._on_bodypart_renamed)
        self._bodypart_list.bodypart_removed.connect(self._on_bodypart_removed)
        self._bodypart_list.add_point_requested.connect(self._controller.enter_add_point_mode)
        self._bodypart_list.clear_all_requested.connect(self._on_clear_all)
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
        self._undo_btn.clicked.connect(self._controller.undo)
        self._redo_btn.clicked.connect(self._controller.redo)
        self._prev_btn.clicked.connect(self._controller.go_prev_frame)
        self._next_btn.clicked.connect(self._controller.go_next_frame)
        self._auto_next_cb.toggled.connect(self._on_auto_next_toggled)
        self._save_btn.clicked.connect(self._save_labels)
        self._import_ai_btn.clicked.connect(self._on_import_ai_gaps)
        self._export_btn.clicked.connect(self._export_csv)

        QShortcut(QKeySequence.Undo, self, activated=self._controller.undo)
        QShortcut(QKeySequence.Redo, self, activated=self._controller.redo)
        QShortcut(QKeySequence("Space"), self, activated=self._controller.go_next_frame)

    def set_ui_preferences(self, prefs: UiPreferences) -> None:
        self._ui_prefs = prefs
        max_f = max(10, int(getattr(prefs, "pose_max_frames_to_analyze", 300)))
        self._frames_spin.setMaximum(max_f)
        self._frames_slider.setMaximum(max_f)
        self._frames_max_lbl.setText(f"/ {max_f}")
        if self._frames_spin.value() > max_f:
            self._frames_spin.setValue(max_f)
        if self._frame_count > 0:
            self._sync_frames_controls(self._target_frames_value())

    def _max_frames_setting(self) -> int:
        return max(10, int(getattr(self._ui_prefs, "pose_max_frames_to_analyze", 300)))

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
        self._thumb_cache.clear()
        self._strip.clear_thumbnail_cache()
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
        self._worker_pick_generation = 0
        self._displayed_frame_index = None
        self._hide_scan_progress()

        ds = LabelDataset()
        ds.schema = default_lab_schema()
        self._controller.load_dataset(ds, [])
        self._canvas.set_crop_frame(None)
        self._canvas.set_fish_outline(None)
        self._canvas.set_display_points({}, None)
        self._canvas.set_display_bones([])
        self._canvas.set_ghost_point(None)
        self._strip.clear_thumbnail_cache()
        self._strip.set_queue([], 0, "", frame_count=1)
        self._active_lbl.setText("Select a bodypart to label")
        self._pick_frames_btn.setEnabled(False)

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
        self._scan_settings_hash = scan_settings_hash(arena, blob_params)
        self._pose_scan_cache = None
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
        self._label_dir = human_labelled_dir(session_name, project_id, video_id)
        self._displayed_frame_index = None
        self._thumb_cache.clear()
        self._diverse_queue_cache.clear()
        ds = load_labels(self._label_dir)
        if not ds.bodyparts():
            ds.schema = default_lab_schema()
        max_f = self._max_frames_setting()
        if ds.frames_to_analyze <= 0 and frame_count > 0:
            ds.frames_to_analyze = target_label_frame_count(frame_count, ds.gap)
        target = frames_to_analyze_cap(frame_count, ds.frames_to_analyze, max_f)
        ds.frames_to_analyze = target
        ds.gap = gap_from_frames_to_analyze(frame_count, target)
        self._sync_frames_controls(target)
        restored = self._restore_saved_queue(ds, target)
        if restored:
            restored = pad_queue_to_target(restored, target, frame_count)
            self._controller.load_dataset(ds, restored)
            cache_key = self._scan_cache_key(target)
            if cache_key is not None:
                self._diverse_queue_cache[cache_key] = list(restored)
        else:
            self._controller.load_dataset(ds, [])
            self._apply_uniform_queue(target)
        self._pick_frames_btn.setEnabled(self._diverse_scan_allowed and frame_count > 0)

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
        self._scan_settings_hash = new_hash
        self._arena = arena
        self._blob_params = blob_params

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
            return False
        if self._pose_scan_cache.fingerprints_loaded:
            return any(fp is not None for fp in self._pose_scan_cache.fingerprints)
        if self._video_dir is None:
            return False
        return (self._video_dir / "pose_scan_cache.npz").is_file()

    def set_diverse_scan_allowed(self, allowed: bool) -> None:
        """When True and the Label tab is visible, diverse picking is available."""
        self._diverse_scan_allowed = allowed
        self._pick_frames_btn.setEnabled(allowed and self._frame_count > 0)
        if allowed:
            self.refresh_display()

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
        target = self._target_frames_value()
        if self._gap_for_target(target) <= 0:
            return
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
        if gap <= 0:
            self._apply_uniform_queue(target)
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

        if for_pick:
            self._worker_pick_generation = self._pick_generation
        self._queue_worker = LabelFrameQueueWorker(
            self._video_dir or self._video_path.parent,
            self._video_path,
            self._frame_count,
            target,
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
            return
        if self._gap_for_target(target) <= 0:
            return
        if not self._scan_cache_has_fingerprints():
            QMessageBox.warning(
                self,
                "Pose Studio",
                "No saved pose fingerprints for this video yet. "
                "Wait for the background pose scan to finish after confirming the arena, "
                "then pick analysis frames again.",
            )
            return
        self._start_diverse_queue_scan(
            target,
            build_from_disk_cache=True,
            save_fingerprints=False,
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
        if self._active_pick_target is None:
            return
        if self._worker_pick_generation != self._pick_generation:
            return
        self._strip.set_live_queue(queue, frame_count=self._frame_count)

    def _emit_background_work_finished(self) -> None:
        if not self.is_background_work_running():
            self.background_work_finished.emit()

    def _on_queue_ready(self, queue: list) -> None:
        if (
            self._active_pick_target is not None
            and self._worker_pick_generation != self._pick_generation
        ):
            return
        self._hide_scan_progress()
        if self._active_pick_target is None:
            if (
                self._video_dir is not None
                and self._video_path is not None
                and self._video_path.is_file()
            ):
                self._pose_scan_cache = load_pose_scan_cache(
                    self._video_dir,
                    frame_count=self._frame_count,
                    video_path=self._video_path,
                    arena=self._arena,
                    blob_params=self._blob_params,
                    load_fingerprints=False,
                )
            self._emit_background_work_finished()
            return
        target = self._active_pick_target
        gap = self._gap_for_target(target)
        cache_key = self._scan_cache_key(target)
        if cache_key is not None:
            self._diverse_queue_cache[cache_key] = list(queue)
        if (
            self._video_dir is not None
            and self._video_path is not None
            and self._video_path.is_file()
        ):
            self._pose_scan_cache = load_pose_scan_cache(
                self._video_dir,
                frame_count=self._frame_count,
                video_path=self._video_path,
                arena=self._arena,
                blob_params=self._blob_params,
                load_fingerprints=False,
            )
        self._apply_frame_queue(target, gap, queue, persist=True)
        self._active_pick_target = None
        self._emit_background_work_finished()

    def _on_queue_failed(self, msg: str) -> None:
        if self._active_pick_target is None:
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
                "Confirm the arena on the Select Crop tab before picking analysis frames.",
            )
            return
        target = self._target_frames_value()
        self._sync_frames_controls(target)
        self._pick_generation += 1
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

    def _on_clear_all(self) -> None:
        if (
            QMessageBox.question(
                self,
                "Clear all points",
                "Remove all bodyparts and labels? You can Undo.",
            )
            != QMessageBox.Yes
        ):
            return
        self._controller.clear_all_bodyparts()

    def _on_point_placed(self, x: float, y: float) -> None:
        fx, fy = self._crop_to_full(x, y)
        self._controller.place_active_point(fx, fy)
        self._save_labels(silent=True)

    def _on_auto_next_toggled(self, checked: bool) -> None:
        self._controller.set_auto_advance_frames(checked)

    def _on_point_delete_requested(self) -> None:
        if not self._controller.delete_active_point():
            return
        self._save_labels(silent=True)

    def _on_point_moved(self, bodypart: str, x: float, y: float) -> None:
        fx, fy = self._crop_to_full(x, y)
        self._controller.move_point(bodypart, fx, fy)
        self._save_labels(silent=True)

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
        frame = self._current_frame_bgr()
        if frame is None:
            return None, None
        blob = detect_blob_square_crop(frame, self._arena, self._blob_params)
        if not blob.found:
            return None, blob
        crop = extract_square_crop(frame, blob)
        return crop, blob

    def _refresh_ui(self) -> None:
        ctrl = self._controller
        names = ctrl.dataset.bodyparts()
        counts = {n: ctrl.dataset.count_for_bodypart(n) for n in names}
        qlen = len(ctrl.frame_queue)
        self._bodypart_list.set_bodyparts(
            names,
            counts,
            qlen,
            selected_name=ctrl.active_bodypart,
        )
        self._bodypart_list.set_bones(ctrl.bone_name_pairs())
        self._bodypart_list.set_add_point_mode(ctrl.add_point_mode)
        self._bodypart_list.set_bone_mode(ctrl.bone_mode)
        if ctrl.active_bodypart:
            self._active_lbl.setText(
                f"Labeling: {ctrl.active_bodypart}  ·  scroll to zoom, middle-drag to pan, double-click to fit"
            )
        elif ctrl.bone_mode:
            self._active_lbl.setText("Bone tool: click two points to link them")
        elif ctrl.add_point_mode:
            self._active_lbl.setText("Click image to add a new point")
        else:
            self._active_lbl.setText("Select a bodypart or Add point")

        crop, blob = self._current_crop()
        fi = ctrl.current_frame_index()
        if crop is None or crop.size == 0:
            self._canvas.set_crop_frame(None)
            self._displayed_frame_index = None
        elif fi != self._displayed_frame_index:
            self._canvas.set_crop_frame(
                crop,
                reset_view=self._displayed_frame_index is None,
            )
            self._displayed_frame_index = fi
        if blob is not None and blob.found:
            self._canvas.set_fish_outline(fish_mask_in_crop(blob))
        else:
            self._canvas.set_fish_outline(None)
        self._canvas.set_add_point_mode(ctrl.add_point_mode)
        points_crop: dict[str, tuple[float, float] | None] = {}
        if blob is not None and blob.found:
            for name in ctrl.dataset.bodyparts():
                xy = ctrl.dataset.get_point(fi, name)
                if xy is not None:
                    points_crop[name] = full_frame_to_crop(xy[0], xy[1], blob)
        self._canvas.set_display_points(points_crop, ctrl.active_bodypart)
        self._canvas.set_display_bones(ctrl.bone_name_pairs())
        self._canvas.set_ghost_point(self._ghost_point_crop(ctrl, blob))
        self._strip.set_queue(
            ctrl.frame_queue,
            ctrl.queue_index,
            f"Frame {fi}  ·  Queue {ctrl.progress_label()}",
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

    def _on_import_ai_gaps(self) -> None:
        if not self._session_name or not self._project_id or not self._video_id:
            QMessageBox.warning(self, "Pose Studio", "Select a video first.")
            return
        try:
            result = import_source_into_human(
                self._session_name,
                self._project_id,
                self._video_id,
                "ai",
                only_missing=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Pose Studio", str(exc))
            return
        if result.points_added == 0:
            QMessageBox.information(
                self,
                "Pose Studio",
                "No new AI points to import (train first, or all gaps already labeled).",
            )
            return
        ds = load_labels(self._label_dir)
        queue = list(self._controller.frame_queue)
        self._controller.load_dataset(ds, queue)
        QMessageBox.information(
            self,
            "Pose Studio",
            f"Imported {result.points_added} AI point(s) on {result.frames_touched} frame(s).",
        )

    def _save_labels(self, silent: bool = False) -> None:
        if self._label_dir is None:
            return
        self._controller.dataset.label_frame_queue = list(self._controller.frame_queue)
        self._controller.dataset.frames_to_analyze = self._target_frames_value()
        self._controller.dataset.gap = self._gap_for_target(self._target_frames_value())
        save_labels(self._label_dir, self._controller.dataset)
        if not silent:
            QMessageBox.information(self, "Pose Studio", "Labels saved.")

    def _export_csv(self) -> None:
        if self._label_dir is None:
            return
        self._save_labels(silent=True)
        out = self._label_dir / "tracking.csv"
        export_dlc_csv(self._controller.dataset, self._frame_count, out)
        self.tracking_exported.emit(str(out))
        QMessageBox.information(
            self,
            "Pose Studio",
            f"Exported:\n{out}\n\nOpen Verify to attach this CSV to the session.",
        )
