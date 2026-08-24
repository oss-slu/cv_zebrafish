"""Pose Studio Step 6 — dataset catalog and merge."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.pose.dataset.dataset_catalog import list_pose_datasets
from core.pose.dataset.dataset_merge import combine_video_datasets
from core.pose.dataset.import_external_dataset import import_external_dlc_csv
from core.pose.dataset.lab_config import config_from_human_labels
from core.pose.dataset.retrain_loop import import_source_into_human
from session.session import Session


class PoseDatasetWidget(QWidget):
    """List pose datasets, merge manual+AI, send to Verify."""

    send_to_verify = pyqtSignal(str)
    json_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseDatasetWidget")
        self._session: Session | None = None
        self._project_id = "default"

        root = QVBoxLayout(self)

        self._list = QListWidget()
        self._list.setMinimumHeight(120)
        root.addWidget(self._list, stretch=1)

        combine = QGroupBox("Combine for Verify")
        cl = QVBoxLayout(combine)
        row = QHBoxLayout()
        row.addWidget(QLabel("Video"))
        self._video_combo = QComboBox()
        row.addWidget(self._video_combo, stretch=1)
        cl.addLayout(row)

        flags = QHBoxLayout()
        self._use_human = QCheckBox("Human labels")
        self._use_human.setChecked(True)
        self._use_ai = QCheckBox("AI predictions")
        self._use_ai.setChecked(True)
        self._use_external = QCheckBox("External import")
        self._use_external.setToolTip("Include DLC CSV imported from outside Pose Studio.")
        flags.addWidget(self._use_human)
        flags.addWidget(self._use_ai)
        flags.addWidget(self._use_external)
        flags.addStretch(1)
        cl.addLayout(flags)

        import_row = QHBoxLayout()
        self._import_btn = QPushButton("Import external CSV…")
        self._import_btn.setToolTip(
            "Copy a DLC-shaped tracking CSV into external_labelled/ for the selected video."
        )
        self._import_btn.clicked.connect(self._on_import_external)
        import_row.addWidget(self._import_btn)
        import_row.addStretch(1)
        cl.addLayout(import_row)

        btn_row = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        self._merge_btn = QPushButton("Merge → final_labelled")
        self._merge_btn.clicked.connect(self._on_merge)
        self._promote_btn = QPushButton("AI → human (gaps)")
        self._promote_btn.setToolTip(
            "Import AI predictions into human_labelled for the selected video (manual kept)."
        )
        self._promote_btn.clicked.connect(self._on_promote_ai)
        self._verify_btn = QPushButton("Send to Verify")
        self._verify_btn.clicked.connect(self._on_send_verify)
        btn_row.addWidget(self._refresh_btn)
        btn_row.addWidget(self._merge_btn)
        btn_row.addWidget(self._promote_btn)
        btn_row.addWidget(self._verify_btn)
        self._config_btn = QPushButton("Generate kinematics config")
        self._config_btn.clicked.connect(self._on_generate_config)
        btn_row.addWidget(self._config_btn)
        btn_row.addStretch(1)
        cl.addLayout(btn_row)
        root.addWidget(combine)

        self._status = QLabel("")
        self._status.setObjectName("SettingsHintLabel")
        root.addWidget(self._status)

        self._last_merged_csv: str | None = None

    def load_session(self, session: Session | None, project_id: str) -> None:
        self._session = session
        self._project_id = project_id
        self._refresh()

    def _video_meta(self) -> dict[str, str]:
        if self._session is None:
            return {}
        proj = self._session.pose_projects.get(self._project_id, {})
        videos = proj.get("videos") or {}
        return {
            vid: (info or {}).get("display_name", vid)
            for vid, info in videos.items()
        }

    def _refresh(self) -> None:
        self._list.clear()
        self._video_combo.blockSignals(True)
        self._video_combo.clear()
        if self._session is None:
            self._video_combo.blockSignals(False)
            self._status.setText("Open a session to view datasets.")
            return

        meta = self._video_meta()
        entries = list_pose_datasets(self._session.getName(), self._project_id, meta)
        for ent in entries:
            self._list.addItem(ent.summary())

        vids = self._session.get_pose_video_ids()
        for vid in vids:
            self._video_combo.addItem(meta.get(vid, vid), vid)

        self._video_combo.blockSignals(False)
        if entries:
            self._status.setText(f"{len(entries)} dataset(s) in project.")
        else:
            self._status.setText("No datasets yet — label or train first.")

    def _on_generate_config(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Datasets", "Open a session first.")
            return
        vid = self._video_combo.currentData()
        if not vid:
            QMessageBox.warning(self, "Datasets", "Select a video.")
            return
        csv_path = self._last_merged_csv
        if not csv_path:
            from app_platform.paths import final_labelled_dir, human_labelled_dir

            for root in (
                final_labelled_dir(self._session.getName(), self._project_id, str(vid)),
                human_labelled_dir(self._session.getName(), self._project_id, str(vid)),
            ):
                p = root / "tracking.csv"
                if p.is_file():
                    csv_path = str(p)
                    break
        try:
            cfg_path, _ = config_from_human_labels(
                self._session.getName(),
                self._project_id,
                str(vid),
                csv_path=csv_path,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Datasets", str(exc))
            return
        self._status.setText(f"Config: {cfg_path}")
        self.json_selected.emit(str(cfg_path))
        QMessageBox.information(self, "Datasets", f"Kinematics config written:\n{cfg_path}")

    def _on_merge(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Datasets", "Open a session first.")
            return
        vid = self._video_combo.currentData()
        if not vid:
            QMessageBox.warning(self, "Datasets", "Select a video.")
            return
        if not self._use_human.isChecked() and not self._use_ai.isChecked() and not self._use_external.isChecked():
            QMessageBox.warning(self, "Datasets", "Select at least one source.")
            return
        try:
            csv_path, prov_path = combine_video_datasets(
                self._session.getName(),
                self._project_id,
                str(vid),
                use_human=self._use_human.isChecked(),
                use_ai=self._use_ai.isChecked(),
                use_external=self._use_external.isChecked(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Datasets", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Datasets", str(exc))
            return

        self._last_merged_csv = str(csv_path)
        self._session.addCSV(str(csv_path))
        self._session.save()
        self._status.setText(f"Merged → {csv_path.name} (provenance: {prov_path.name})")
        self._refresh()

    def _on_import_external(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Datasets", "Open a session first.")
            return
        vid = self._video_combo.currentData()
        if not vid:
            QMessageBox.warning(self, "Datasets", "Select a video.")
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
                str(vid),
                Path(path),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Datasets", str(exc))
            return
        self._use_external.setChecked(True)
        self._status.setText(f"Imported external CSV → {dest.name}")
        self._refresh()

    def _on_promote_ai(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Datasets", "Open a session first.")
            return
        vid = self._video_combo.currentData()
        if not vid:
            QMessageBox.warning(self, "Datasets", "Select a video.")
            return
        try:
            result = import_source_into_human(
                self._session.getName(),
                self._project_id,
                str(vid),
                "ai",
                only_missing=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Datasets", str(exc))
            return
        self._session.save()
        self._status.setText(
            f"Promoted {result.points_added} AI point(s) → human labels ({vid})."
        )
        self._refresh()

    def _on_send_verify(self) -> None:
        if self._last_merged_csv:
            self.send_to_verify.emit(self._last_merged_csv)
            return
        if self._session is None:
            return
        vid = self._video_combo.currentData()
        if not vid:
            return
        from app_platform.paths import final_labelled_dir

        csv_path = final_labelled_dir(self._session.getName(), self._project_id, str(vid)) / "tracking.csv"
        if csv_path.is_file():
            self.send_to_verify.emit(str(csv_path))
        else:
            QMessageBox.information(
                self,
                "Datasets",
                "Merge a dataset first, or export from the Label tab.",
            )
