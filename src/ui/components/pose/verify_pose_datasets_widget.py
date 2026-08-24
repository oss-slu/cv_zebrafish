"""Compact Pose Studio dataset strip for the Verify panel."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_platform.paths import final_labelled_dir
from core.pose.dataset.dataset_catalog import PoseDatasetEntry, list_pose_datasets
from core.pose.dataset.dataset_merge import combine_video_datasets
from core.pose.dataset.import_external_dataset import import_external_dlc_csv
from core.pose.dataset.lab_config import config_from_human_labels
from session.session import Session

_VIDEO_ID_ROLE = Qt.UserRole
_SOURCE_KEY_ROLE = Qt.UserRole + 1
_ENTRY_ROLE = Qt.UserRole + 2


class VerifyPoseDatasetsWidget(QWidget):
    """Session pose datasets on Verify — toggle sources, order merge priority, send CSV."""

    send_to_verify = pyqtSignal(str)
    json_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VerifyPoseDatasetsWidget")
        self._session: Session | None = None
        self._project_id = "default"
        self._last_csv: str | None = None
        self._active_video_id: str | None = None
        self._entries_by_key: dict[tuple[str, str], PoseDatasetEntry] = {}

        box = QGroupBox("Pose Studio datasets")
        layout = QVBoxLayout(box)

        self._tree = QTreeWidget()
        self._tree.setObjectName("PoseDatasetTree")
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setItemsExpandable(True)
        self._tree.setSelectionMode(QAbstractItemView.NoSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setMinimumHeight(120)
        self._tree.setMaximumHeight(180)
        self._tree.setToolTip(
            "Check datasets under one video. Selecting another video clears the previous video."
        )
        self._tree.itemChanged.connect(self._on_tree_item_changed)
        layout.addWidget(self._tree)

        priority_box = QGroupBox("Merge priority (top overwrites below)")
        priority_layout = QVBoxLayout(priority_box)
        self._priority_hint = QLabel(
            "Drag to reorder. Top source wins on conflicting points."
        )
        self._priority_hint.setObjectName("SettingsHintLabel")
        self._priority_hint.setWordWrap(True)
        priority_layout.addWidget(self._priority_hint)
        self._priority_list = QListWidget()
        self._priority_list.setObjectName("PoseDatasetPriorityList")
        self._priority_list.setDragDropMode(QAbstractItemView.InternalMove)
        self._priority_list.setDefaultDropAction(Qt.MoveAction)
        self._priority_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._priority_list.setMinimumHeight(72)
        self._priority_list.setMaximumHeight(120)
        self._priority_list.setToolTip("Drag rows vertically to set merge overwrite order")
        priority_layout.addWidget(self._priority_list)
        layout.addWidget(priority_box)

        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("Import into"))
        self._import_video_combo = QComboBox()
        self._import_video_combo.setToolTip("Video that receives an imported external CSV")
        import_row.addWidget(self._import_video_combo, stretch=1)
        self._import_btn = QPushButton("Import CSV…")
        self._import_btn.clicked.connect(self._on_import_external)
        import_row.addWidget(self._import_btn)
        layout.addLayout(import_row)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        self._merge_btn = QPushButton("Merge")
        self._merge_btn.clicked.connect(self._on_merge)
        self._config_btn = QPushButton("Generate config")
        self._config_btn.clicked.connect(self._on_generate_config)
        self._send_btn = QPushButton("Use CSV")
        self._send_btn.clicked.connect(self._on_send_csv)
        for b in (self._refresh_btn, self._merge_btn, self._config_btn, self._send_btn):
            btn_row.addWidget(b)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(box)
        self.hide()

    def load_session(self, session: Session | None, project_id: str = "default") -> None:
        self._session = session
        self._project_id = project_id
        self._refresh()

    def _video_meta(self) -> dict[str, str]:
        if self._session is None:
            return {}
        proj = self._session.pose_projects.get(self._project_id, {})
        return {
            vid: (info or {}).get("display_name", vid)
            for vid, info in (proj.get("videos") or {}).items()
        }

    def _import_video_id(self) -> str | None:
        if self._active_video_id:
            return self._active_video_id
        vid = self._import_video_combo.currentData()
        return str(vid) if vid else None

    def _source_display(self, ent: PoseDatasetEntry) -> str:
        label = ent.source_label()
        return f"{label} — {ent.labeled_frames} labeled"

    def _refresh(self) -> None:
        prev_video = self._active_video_id
        prev_keys = self._priority_source_keys()

        self._tree.blockSignals(True)
        self._tree.clear()
        self._priority_list.clear()
        self._entries_by_key.clear()
        self._active_video_id = None
        self._import_video_combo.blockSignals(True)
        self._import_video_combo.clear()

        if self._session is None or not self._session.pose_projects:
            self._tree.blockSignals(False)
            self._import_video_combo.blockSignals(False)
            self.hide()
            return

        meta = self._video_meta()
        entries = list_pose_datasets(
            self._session.getName(),
            self._project_id,
            meta,
        )
        vids = self._session.get_pose_video_ids()
        for vid in vids:
            self._import_video_combo.addItem(meta.get(vid, vid), vid)
        self._import_video_combo.blockSignals(False)

        if not entries:
            self._tree.blockSignals(False)
            self.hide()
            return

        by_video: dict[str, list[PoseDatasetEntry]] = {}
        for ent in entries:
            by_video.setdefault(ent.video_id, []).append(ent)
            self._entries_by_key[(ent.video_id, ent.source_key())] = ent

        for vid in vids:
            video_entries = by_video.get(vid) or []
            if not video_entries:
                continue
            parent = QTreeWidgetItem([meta.get(vid, vid)])
            parent.setFlags(Qt.ItemIsEnabled)
            parent.setData(0, _VIDEO_ID_ROLE, vid)
            parent.setToolTip(0, f"Video: {meta.get(vid, vid)}")
            self._tree.addTopLevelItem(parent)
            for ent in video_entries:
                child = QTreeWidgetItem([self._source_display(ent)])
                child.setFlags(
                    (child.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    & ~Qt.ItemIsSelectable
                )
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, _VIDEO_ID_ROLE, ent.video_id)
                child.setData(0, _SOURCE_KEY_ROLE, ent.source_key())
                child.setData(0, _ENTRY_ROLE, ent)
                child.setToolTip(0, ent.summary())
                parent.addChild(child)
            parent.setExpanded(True)

        self._tree.blockSignals(False)

        # Restore prior selection if still valid and same-video.
        restore_keys = [
            k
            for k in prev_keys
            if prev_video and (prev_video, k) in self._entries_by_key
        ]
        if restore_keys and prev_video:
            self._set_checked_keys(prev_video, restore_keys)
        self.show()

    def _set_checked_keys(self, video_id: str, source_keys: list[str]) -> None:
        want = set(source_keys)
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            if parent is None or parent.data(0, _VIDEO_ID_ROLE) != video_id:
                continue
            for j in range(parent.childCount()):
                child = parent.child(j)
                key = child.data(0, _SOURCE_KEY_ROLE)
                child.setCheckState(0, Qt.Checked if key in want else Qt.Unchecked)
        self._tree.blockSignals(False)
        self._active_video_id = video_id
        self._rebuild_priority_list(source_keys)
        idx = self._import_video_combo.findData(video_id)
        if idx >= 0:
            self._import_video_combo.setCurrentIndex(idx)

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        if item is None or item.parent() is None:
            return
        video_id = item.data(0, _VIDEO_ID_ROLE)
        source_key = item.data(0, _SOURCE_KEY_ROLE)
        if not video_id or not source_key:
            return

        checked = item.checkState(0) == Qt.Checked
        if checked:
            if self._active_video_id and self._active_video_id != video_id:
                self._clear_checks_except_video(str(video_id))
            self._active_video_id = str(video_id)
            if source_key not in self._priority_source_keys():
                self._append_priority_item(str(video_id), str(source_key))
            idx = self._import_video_combo.findData(video_id)
            if idx >= 0:
                self._import_video_combo.setCurrentIndex(idx)
        else:
            self._remove_priority_key(str(source_key))
            if not self._priority_source_keys():
                self._active_video_id = None

    def _clear_checks_except_video(self, keep_video_id: str) -> None:
        self._tree.blockSignals(True)
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            if parent is None:
                continue
            vid = parent.data(0, _VIDEO_ID_ROLE)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if vid != keep_video_id and child.checkState(0) == Qt.Checked:
                    child.setCheckState(0, Qt.Unchecked)
        self._tree.blockSignals(False)
        # Drop priority rows from the previous video.
        keep_keys = set()
        for i in range(self._tree.topLevelItemCount()):
            parent = self._tree.topLevelItem(i)
            if parent is None or parent.data(0, _VIDEO_ID_ROLE) != keep_video_id:
                continue
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    key = child.data(0, _SOURCE_KEY_ROLE)
                    if key:
                        keep_keys.add(str(key))
        self._rebuild_priority_list(
            [k for k in self._priority_source_keys() if k in keep_keys]
            or sorted(keep_keys)
        )

    def _priority_source_keys(self) -> list[str]:
        keys: list[str] = []
        for i in range(self._priority_list.count()):
            item = self._priority_list.item(i)
            if item is None:
                continue
            key = item.data(_SOURCE_KEY_ROLE)
            if key:
                keys.append(str(key))
        return keys

    def _append_priority_item(self, video_id: str, source_key: str) -> None:
        ent = self._entries_by_key.get((video_id, source_key))
        label = ent.source_label() if ent else source_key
        item = QListWidgetItem(label)
        item.setData(_SOURCE_KEY_ROLE, source_key)
        item.setData(_VIDEO_ID_ROLE, video_id)
        item.setFlags(
            (item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
            & ~Qt.ItemIsDropEnabled
        )
        if ent is not None:
            item.setToolTip(ent.summary())
        self._priority_list.addItem(item)

    def _remove_priority_key(self, source_key: str) -> None:
        for i in range(self._priority_list.count() - 1, -1, -1):
            item = self._priority_list.item(i)
            if item is not None and item.data(_SOURCE_KEY_ROLE) == source_key:
                self._priority_list.takeItem(i)

    def _rebuild_priority_list(self, source_keys: list[str]) -> None:
        video_id = self._active_video_id
        self._priority_list.clear()
        if not video_id:
            return
        for key in source_keys:
            if (video_id, key) in self._entries_by_key:
                self._append_priority_item(video_id, key)

    def _selected_sources_high_to_low(self) -> list[str]:
        """Priority list order: index 0 wins (overwrites lower rows)."""
        return self._priority_source_keys()

    def _on_merge(self) -> None:
        if self._session is None:
            return
        vid = self._active_video_id
        high_to_low = self._selected_sources_high_to_low()
        if not vid:
            QMessageBox.warning(self, "Pose datasets", "Select at least one dataset.")
            return
        if not high_to_low:
            QMessageBox.warning(self, "Pose datasets", "Select at least one dataset.")
            return
        # Engine expects low → high (later overwrites earlier).
        sources_low_to_high = list(reversed(high_to_low))
        try:
            csv_path, _ = combine_video_datasets(
                self._session.getName(),
                self._project_id,
                vid,
                sources_low_to_high=sources_low_to_high,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Pose datasets", str(exc))
            return
        self._last_csv = str(csv_path)
        self._session.addCSV(str(csv_path))
        self._session.save()
        self._refresh()

    def _on_import_external(self) -> None:
        if self._session is None:
            return
        vid = self._import_video_id()
        if not vid:
            QMessageBox.warning(self, "Pose datasets", "Select a video.")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import external DLC CSV",
            "",
            "CSV files (*.csv);;All files (*)",
        )
        if not path:
            return
        try:
            dest = import_external_dlc_csv(
                self._session.getName(),
                self._project_id,
                vid,
                Path(path),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Pose datasets", str(exc))
            return
        self._refresh()
        # Auto-select the imported external source for this video.
        self._set_checked_keys(vid, ["external"])
        QMessageBox.information(self, "Pose datasets", f"Imported:\n{dest}")

    def _on_generate_config(self) -> None:
        if self._session is None:
            return
        vid = self._active_video_id or self._import_video_id()
        if not vid:
            QMessageBox.warning(self, "Pose datasets", "Select a video.")
            return
        csv_path = self._last_csv
        if not csv_path:
            final_csv = final_labelled_dir(
                self._session.getName(), self._project_id, vid
            ) / "tracking.csv"
            if final_csv.is_file():
                csv_path = str(final_csv)
        try:
            cfg_path, _ = config_from_human_labels(
                self._session.getName(),
                self._project_id,
                vid,
                csv_path=csv_path,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Pose datasets", str(exc))
            return
        self.json_selected.emit(str(cfg_path))
        QMessageBox.information(
            self,
            "Pose datasets",
            f"Config written:\n{cfg_path}\n\nLoaded into JSON field below.",
        )

    def _on_send_csv(self) -> None:
        if self._last_csv:
            self.send_to_verify.emit(self._last_csv)
            return
        if self._session is None:
            return
        vid = self._active_video_id or self._import_video_id()
        if not vid:
            return
        for candidate in (
            final_labelled_dir(self._session.getName(), self._project_id, vid) / "tracking.csv",
        ):
            if candidate.is_file():
                self.send_to_verify.emit(str(candidate))
                return
        QMessageBox.information(self, "Pose datasets", "Merge or export a CSV first.")
