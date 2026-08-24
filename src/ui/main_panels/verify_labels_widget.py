"""Pose Studio — Verify Labels: full-frame video + dataset overlay."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Callable

import numpy as np
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core.pose.dataset.dataset_catalog import PoseDatasetEntry, list_datasets_for_video
from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.named_label_sets import (
    apply_edges_to_dataset,
    load_dataset_from_dir,
    save_named_set,
    slugify_dataset_name,
)
from core.pose.labeling.pose_outliers import detect_pose_outlier_frames
from ui.components.pose.bodypart_label_list import BodypartLabelList
from ui.components.pose.frame_scrubber import FrameScrubber
from ui.components.pose.label_canvas import LabelCanvas
from ui.components.pose.labeling_controller import LabelingController

_DATASET_PRIORITY = ("ai", "human", "final", "external", "custom")


def _default_dataset(entries: list[PoseDatasetEntry]) -> PoseDatasetEntry | None:
    for source in _DATASET_PRIORITY:
        for ent in entries:
            if ent.source == source:
                return ent
    return entries[0] if entries else None


def _first_labeled_frame(dataset: LabelDataset) -> int | None:
    """Lowest frame index with at least one non-null point."""
    for fi in sorted(dataset.frames.keys()):
        fl = dataset.frames[fi]
        if any(xy is not None for xy in fl.points.values()):
            return fi
    return None


class VerifyLabelsWidget(QWidget):
    """Review label datasets on plain full-frame video (no crop / arena)."""

    labels_saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VerifyLabelsWidget")
        self._read_frame: Callable[[int], np.ndarray | None] | None = None
        self._frame_count = 0
        self._session_name: str | None = None
        self._project_id = "default"
        self._video_id: str | None = None
        self._entries: list[PoseDatasetEntry] = []
        self._active_entry: PoseDatasetEntry | None = None
        self._custom_slug: str | None = None
        self._dirty = False
        self._controller = LabelingController()
        self._controller.bind_listener(self._refresh_ui)
        self._controller.set_auto_advance_frames(False)
        self._displayed_frame_index: int | None = None
        self._outlier_frames: set[int] = set()
        self._outlier_reasons: dict[int, list[str]] = {}
        self._outlier_bodyparts: dict[int, set[str]] = {}
        self._outlier_bones: dict[int, set[tuple[str, str]]] = {}
        self._outlier_sorted: list[int] = []

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self._status_lbl = QLabel(
            "Select a video — labels overlay the full frame (scroll to zoom, middle-drag to pan)."
        )
        self._status_lbl.setObjectName("SettingsHintLabel")
        self._status_lbl.setWordWrap(True)
        top.addWidget(self._status_lbl, stretch=1)
        self._save_btn = QPushButton("Save")
        self._save_btn.setToolTip("Save to the current custom set (if loaded from one).")
        self._save_as_btn = QPushButton("Save as…")
        self._save_as_btn.clicked.connect(self._on_save_as)
        self._save_btn.clicked.connect(self._on_save)
        self._reload_btn = QPushButton("Reload")
        self._reload_btn.clicked.connect(self._reload_dataset)
        for b in (self._save_btn, self._save_as_btn, self._reload_btn):
            top.addWidget(b)
        root.addLayout(top)

        pick = QHBoxLayout()
        pick.addWidget(QLabel("Dataset"))
        self._dataset_combo = QComboBox()
        self._dataset_combo.setMinimumWidth(220)
        self._dataset_combo.currentIndexChanged.connect(self._on_dataset_changed)
        pick.addWidget(self._dataset_combo, stretch=1)
        root.addLayout(pick)

        tools = QHBoxLayout()
        self._undo_btn = QPushButton("Undo")
        self._redo_btn = QPushButton("Redo")
        self._prev_out_btn = QPushButton("◀ Outlier")
        self._next_out_btn = QPushButton("Outlier ▶")
        self._pause_out_cb = QCheckBox("Pause on outliers")
        for w in (
            self._undo_btn,
            self._redo_btn,
            self._prev_out_btn,
            self._next_out_btn,
            self._pause_out_cb,
        ):
            tools.addWidget(w)
        tools.addStretch(1)
        root.addLayout(tools)

        mid = QSplitter(Qt.Horizontal)
        mid.setChildrenCollapsible(False)
        self._bodypart_list = BodypartLabelList()
        self._bodypart_list.set_clear_all_visible(True)
        self._canvas = LabelCanvas()
        mid.addWidget(self._bodypart_list)
        mid.addWidget(self._canvas)
        mid.setStretchFactor(0, 0)
        mid.setStretchFactor(1, 1)
        mid.setSizes([BodypartLabelList.DEFAULT_WIDTH, 720])
        root.addWidget(mid, stretch=1)

        self._scrubber = FrameScrubber()
        root.addWidget(self._scrubber)

        self._reason_lbl = QLabel("")
        self._reason_lbl.setObjectName("SettingsHintLabel")
        self._reason_lbl.setWordWrap(True)
        root.addWidget(self._reason_lbl)

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
        self._undo_btn.clicked.connect(self._controller.undo)
        self._redo_btn.clicked.connect(self._controller.redo)
        self._prev_out_btn.clicked.connect(lambda: self._jump_outlier(-1))
        self._next_out_btn.clicked.connect(lambda: self._jump_outlier(1))
        self._scrubber.frame_changed.connect(self._on_scrub_frame)
        self._scrubber.frame_preview.connect(self._on_scrub_preview)

        self._set_review_enabled(False)

    def reset_for_new_session(self) -> None:
        self._read_frame = None
        self._frame_count = 0
        self._session_name = None
        self._video_id = None
        self._entries = []
        self._active_entry = None
        self._custom_slug = None
        self._dirty = False
        self._dataset_combo.blockSignals(True)
        self._dataset_combo.clear()
        self._dataset_combo.blockSignals(False)
        self._controller.load_dataset(LabelDataset(), [])
        self._canvas.set_crop_frame(None)
        self._canvas.set_fish_outline(None)
        self._scrubber.stop_playback()
        self._scrubber.set_frame_count(1)
        self._displayed_frame_index = None
        self._set_review_enabled(False)
        self._status_lbl.setText(
            "Select a video — labels overlay the full frame (scroll to zoom, middle-drag to pan)."
        )

    def set_video_context(
        self,
        *,
        read_frame: Callable[[int], np.ndarray | None],
        frame_count: int,
        session_name: str,
        project_id: str,
        video_id: str,
        video_display_name: str,
        force_reload: bool = False,
    ) -> None:
        same_video = (
            self._session_name == session_name
            and self._project_id == project_id
            and self._video_id == video_id
        )
        self._read_frame = read_frame
        self._frame_count = max(1, frame_count)
        self._session_name = session_name
        self._project_id = project_id
        self._video_id = video_id
        if same_video and self._active_entry is not None and not force_reload:
            self._refresh_display()
            return
        self._displayed_frame_index = None
        self._populate_dataset_combo(video_display_name)
        default = _default_dataset(self._entries)
        if default is not None:
            self._load_entry(default)
        else:
            self._status_lbl.setText(
                "No label datasets for this video yet (human, AI, external, or custom)."
            )

    def refresh_display(self) -> None:
        self._refresh_display()

    def _set_review_enabled(self, enabled: bool) -> None:
        for w in (
            self._bodypart_list,
            self._canvas,
            self._scrubber,
            self._undo_btn,
            self._redo_btn,
            self._prev_out_btn,
            self._next_out_btn,
            self._pause_out_cb,
            self._save_btn,
            self._save_as_btn,
            self._reload_btn,
        ):
            w.setEnabled(enabled)
        self._dataset_combo.setEnabled(True)

    def _populate_dataset_combo(self, video_display_name: str) -> None:
        self._dataset_combo.blockSignals(True)
        self._dataset_combo.clear()
        self._entries = []
        if not self._session_name or not self._video_id:
            self._dataset_combo.blockSignals(False)
            return
        self._entries = list_datasets_for_video(
            self._session_name,
            self._project_id,
            self._video_id,
            video_display_name,
        )
        for ent in self._entries:
            label = ent.summary().split(" — ", 1)[-1] if " — " in ent.summary() else ent.summary()
            self._dataset_combo.addItem(label, ent)
        self._dataset_combo.blockSignals(False)

    def _on_dataset_changed(self, index: int) -> None:
        if index < 0:
            return
        if self._dirty:
            ans = QMessageBox.question(
                self,
                "Verify Labels",
                "Discard unsaved edits and load the selected dataset?",
            )
            if ans != QMessageBox.Yes:
                idx = -1
                for i, ent in enumerate(self._entries):
                    if self._active_entry and ent.dir_path == self._active_entry.dir_path:
                        idx = i
                        break
                if idx >= 0:
                    self._dataset_combo.blockSignals(True)
                    self._dataset_combo.setCurrentIndex(idx)
                    self._dataset_combo.blockSignals(False)
                return
        ent = self._dataset_combo.itemData(index)
        if not isinstance(ent, PoseDatasetEntry):
            return
        self._load_entry(ent)

    def _reload_dataset(self) -> None:
        if self._active_entry is None:
            idx = self._dataset_combo.currentIndex()
            if idx >= 0:
                ent = self._dataset_combo.itemData(idx)
                if isinstance(ent, PoseDatasetEntry):
                    self._load_entry(ent)
            return
        if self._dirty:
            ans = QMessageBox.question(
                self,
                "Verify Labels",
                "Discard unsaved edits and reload from disk?",
            )
            if ans != QMessageBox.Yes:
                return
        self._load_entry(self._active_entry)

    def _load_entry(self, ent: PoseDatasetEntry) -> None:
        try:
            ds = load_dataset_from_dir(ent.dir_path)
        except (OSError, ValueError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "Verify Labels", str(exc))
            return
        apply_edges_to_dataset(ds)
        self._active_entry = ent
        self._custom_slug = ent.custom_slug
        self._dirty = False
        for i, candidate in enumerate(self._entries):
            if candidate.dir_path == ent.dir_path:
                self._dataset_combo.blockSignals(True)
                self._dataset_combo.setCurrentIndex(i)
                self._dataset_combo.blockSignals(False)
                break
        fc = max(self._frame_count, max(ds.frames.keys(), default=-1) + 1)
        self._frame_count = max(1, fc)
        queue = list(range(self._frame_count))
        self._controller.load_dataset(deepcopy(ds), queue)
        self._scrubber.stop_playback()
        self._scrubber.set_frame_count(self._frame_count)
        start_frame = _first_labeled_frame(ds)
        if start_frame is None:
            start_frame = 0
        self._scrubber.set_frame(start_frame)
        self._controller.go_to_absolute_frame(start_frame)
        self._recompute_outliers()
        self._displayed_frame_index = None
        self._save_btn.setEnabled(self._custom_slug is not None)
        self._set_review_enabled(True)
        self._update_status()
        self._refresh_display()

    def _update_status(self) -> None:
        if not self._active_entry:
            return
        if self._custom_slug:
            base = f"«{self._active_entry.custom_display or self._custom_slug}»"
        else:
            base = f"{self._active_entry.source} labels"
        if self._dirty:
            base += " · unsaved edits"
        if self._read_frame is None:
            base += " · waiting for video"
        n = len(self._outlier_frames)
        if n:
            base += f" · {n} outlier(s)"
        self._status_lbl.setText(base)

    def _recompute_outliers(self) -> None:
        result = detect_pose_outlier_frames(
            self._controller.dataset,
            self._frame_count,
        )
        self._outlier_frames = result.frames
        self._outlier_reasons = result.reasons
        self._outlier_bodyparts = result.bodyparts
        self._outlier_bones = result.bones
        self._outlier_sorted = sorted(result.frames)
        self._scrubber.set_flagged_frames(result.frames)

    def _jump_outlier(self, direction: int) -> None:
        if not self._outlier_sorted:
            return
        cur = self._scrubber.frame_index()
        if direction > 0:
            nxt = next((f for f in self._outlier_sorted if f > cur), None)
            nxt = nxt if nxt is not None else self._outlier_sorted[0]
        else:
            prev = [f for f in self._outlier_sorted if f < cur]
            nxt = prev[-1] if prev else self._outlier_sorted[-1]
        self._scrubber.set_frame(nxt)

    def _on_scrub_frame(self, frame_index: int) -> None:
        self._controller.go_to_absolute_frame(frame_index)
        self._refresh_display()

    def _on_scrub_preview(self, frame_index: int) -> None:
        if self._scrubber.is_playing():
            self._controller.go_to_absolute_frame(frame_index)
            self._refresh_display()
            if self._pause_out_cb.isChecked() and frame_index in self._outlier_frames:
                self._scrubber.stop_playback()

    def _mark_dirty(self) -> None:
        self._dirty = True
        self._update_status()

    def _on_save(self) -> None:
        if not self._session_name or not self._video_id or not self._custom_slug:
            self._on_save_as()
            return
        meta_name = self._active_entry.custom_display if self._active_entry else self._custom_slug
        path = save_named_set(
            self._session_name,
            self._project_id,
            self._video_id,
            meta_name or self._custom_slug,
            self._controller.dataset,
            frame_count=self._frame_count,
            slug=self._custom_slug,
        )
        self._dirty = False
        self._recompute_outliers()
        self._update_status()
        self.labels_saved.emit(str(path))
        QMessageBox.information(self, "Verify Labels", f"Saved:\n{path}")

    def _on_save_as(self) -> None:
        if not self._session_name or not self._video_id:
            return
        default = ""
        if self._active_entry and self._active_entry.custom_display:
            default = f"{self._active_entry.custom_display} (edited)"
        elif self._active_entry:
            default = f"{self._active_entry.source} reviewed"
        name, ok = QInputDialog.getText(
            self,
            "Save label dataset as",
            "Dataset name:",
            text=default,
        )
        if not ok or not name.strip():
            return
        slug = slugify_dataset_name(name)
        loaded_from = None
        if self._active_entry:
            loaded_from = self._active_entry.source
            if self._active_entry.custom_slug:
                loaded_from = f"custom:{self._active_entry.custom_slug}"
        path = save_named_set(
            self._session_name,
            self._project_id,
            self._video_id,
            name.strip(),
            self._controller.dataset,
            frame_count=self._frame_count,
            loaded_from=loaded_from,
            slug=slug,
        )
        self._dirty = False
        self._custom_slug = slug
        self._save_btn.setEnabled(True)
        display = self._video_id or ""
        self._populate_dataset_combo(display)
        for i, ent in enumerate(self._entries):
            if ent.custom_slug == slug:
                self._dataset_combo.blockSignals(True)
                self._dataset_combo.setCurrentIndex(i)
                self._dataset_combo.blockSignals(False)
                self._active_entry = ent
                break
        self._recompute_outliers()
        self._update_status()
        self.labels_saved.emit(str(path))
        QMessageBox.information(self, "Verify Labels", f"Saved as:\n{path}")

    def _on_point_placed(self, x: float, y: float) -> None:
        self._controller.place_active_point(x, y)
        self._mark_dirty()

    def _on_point_moved(self, bodypart: str, x: float, y: float) -> None:
        self._controller.move_point(bodypart, x, y)
        self._mark_dirty()

    def _on_drag_started(self, _bodypart: str) -> None:
        self._controller.begin_point_move()

    def _on_point_delete_requested(self) -> None:
        if self._controller.delete_active_point():
            self._mark_dirty()

    def _on_add_point_at(self, x: float, y: float) -> None:
        name = self._controller.next_default_point_name()
        self._controller.place_new_point_at(name, x, y)
        self._mark_dirty()

    def _on_bodypart_renamed(self, old_name: str, new_name: str) -> None:
        if self._controller.rename_bodypart(old_name, new_name):
            self._mark_dirty()

    def _on_bodypart_removed(self, name: str) -> None:
        if self._controller.remove_bodypart(name):
            self._mark_dirty()

    def _on_bone_pair(self, a: str, b: str) -> None:
        if self._controller.add_bone(a, b):
            self._bodypart_list.clear_bone_pick()
            self._mark_dirty()

    def _on_bone_removed(self, a: str, b: str) -> None:
        if self._controller.remove_bone(a, b):
            self._mark_dirty()

    def _on_bodypart_reordered(self, name: str, target_index: int) -> None:
        if self._controller.reorder_bodypart(name, target_index):
            self._mark_dirty()

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
        self._mark_dirty()

    def _refresh_ui(self) -> None:
        self._refresh_display()

    def _refresh_display(self) -> None:
        ctrl = self._controller
        if not ctrl.dataset.bodyparts() and self._active_entry is None:
            return
        self._recompute_outliers()
        names = ctrl.dataset.bodyparts()
        counts = {n: ctrl.dataset.count_for_bodypart(n) for n in names}
        self._bodypart_list.set_bodyparts(
            names,
            counts,
            self._frame_count,
            selected_name=ctrl.active_bodypart,
        )
        self._bodypart_list.set_bones(ctrl.bone_name_pairs())
        self._bodypart_list.set_add_point_mode(ctrl.add_point_mode)
        self._bodypart_list.set_bone_mode(ctrl.bone_mode)

        fi = ctrl.current_frame_index()
        if self._scrubber.frame_index() != fi:
            self._scrubber.blockSignals(True)
            self._scrubber.set_frame(fi)
            self._scrubber.blockSignals(False)

        frame = self._read_frame(fi) if self._read_frame else None
        if frame is None or frame.size == 0:
            self._canvas.set_crop_frame(None)
            self._canvas.set_fish_outline(None)
            self._canvas.set_outlier_highlight(set(), set())
            self._displayed_frame_index = None
            self._reason_lbl.setText(
                "Video not ready — select a video and wait for it to load."
            )
        else:
            reset_view = self._displayed_frame_index is None
            self._canvas.set_crop_frame(frame, reset_view=reset_view)
            self._displayed_frame_index = fi
            self._canvas.set_fish_outline(None)
            points: dict[str, tuple[float, float] | None] = {}
            for name in ctrl.dataset.bodyparts():
                xy = ctrl.dataset.get_point(fi, name)
                if xy is not None:
                    points[name] = xy
            self._canvas.set_display_points(points, ctrl.active_bodypart)
            self._canvas.set_display_bones(ctrl.bone_name_pairs())
            self._canvas.set_outlier_highlight(
                self._outlier_bodyparts.get(fi, set()),
                self._outlier_bones.get(fi, set()),
            )
            outlier = self._outlier_reasons.get(fi, [])
            self._reason_lbl.setText(
                "Outlier: " + "; ".join(outlier) if outlier else ""
            )
            if outlier:
                self._reason_lbl.setStyleSheet("color: rgb(255, 152, 50);")
            else:
                self._reason_lbl.setStyleSheet("")
            if not points and not outlier:
                n_labeled = ctrl.dataset.count_frames_with_any_point()
                self._reason_lbl.setText(
                    f"No labels on this frame "
                    f"({n_labeled} / {self._frame_count} frames have points)."
                )

        self._canvas.set_add_point_mode(ctrl.add_point_mode)
        self._canvas.set_ghost_point(None)
        self._update_status()
