"""Compact Pose Studio dataset strip for the Verify panel."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import pyqtSignal
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

from app_platform.paths import final_labelled_dir
from core.pose.dataset.dataset_catalog import list_pose_datasets
from core.pose.dataset.dataset_merge import combine_video_datasets
from core.pose.dataset.import_external_dataset import import_external_dlc_csv
from core.pose.dataset.lab_config import config_from_human_labels
from session.session import Session


class VerifyPoseDatasetsWidget(QWidget):
    """Session pose datasets on Verify — merge, config, send to validation."""

    send_to_verify = pyqtSignal(str)
    json_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("VerifyPoseDatasetsWidget")
        self._session: Session | None = None
        self._project_id = "default"
        self._last_csv: str | None = None

        box = QGroupBox("Pose Studio datasets")
        layout = QVBoxLayout(box)
        hint = QLabel(
            "Tracking sets from Pose Studio. Merge human + AI, generate a kinematics "
            "config from the label schema, then send CSV to validation below."
        )
        hint.setWordWrap(True)
        hint.setObjectName("SettingsHintLabel")
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.setMaximumHeight(100)
        layout.addWidget(self._list)

        row = QHBoxLayout()
        row.addWidget(QLabel("Video"))
        self._video_combo = QComboBox()
        row.addWidget(self._video_combo, stretch=1)
        layout.addLayout(row)

        flags = QHBoxLayout()
        self._use_human = QCheckBox("Human")
        self._use_human.setChecked(True)
        self._use_ai = QCheckBox("AI")
        self._use_ai.setChecked(True)
        self._use_external = QCheckBox("External")
        flags.addWidget(self._use_human)
        flags.addWidget(self._use_ai)
        flags.addWidget(self._use_external)
        flags.addStretch(1)
        layout.addLayout(flags)

        import_row = QHBoxLayout()
        self._import_btn = QPushButton("Import CSV…")
        self._import_btn.clicked.connect(self._on_import_external)
        import_row.addWidget(self._import_btn)
        import_row.addStretch(1)
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

    def _current_video_id(self) -> str | None:
        vid = self._video_combo.currentData()
        return str(vid) if vid else None

    def _refresh(self) -> None:
        self._list.clear()
        self._video_combo.blockSignals(True)
        self._video_combo.clear()
        if self._session is None or not self._session.pose_projects:
            self._video_combo.blockSignals(False)
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
            self._video_combo.addItem(meta.get(vid, vid), vid)
        self._video_combo.blockSignals(False)
        if not entries:
            self.hide()
            return
        for ent in entries:
            self._list.addItem(ent.summary())
        self.show()

    def _on_merge(self) -> None:
        if self._session is None:
            return
        vid = self._current_video_id()
        if not vid:
            return
        try:
            csv_path, _ = combine_video_datasets(
                self._session.getName(),
                self._project_id,
                vid,
                use_human=self._use_human.isChecked(),
                use_ai=self._use_ai.isChecked(),
                use_external=self._use_external.isChecked(),
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
        vid = self._current_video_id()
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
        self._use_external.setChecked(True)
        self._refresh()
        QMessageBox.information(self, "Pose datasets", f"Imported:\n{dest}")

    def _on_generate_config(self) -> None:
        if self._session is None:
            return
        vid = self._current_video_id()
        if not vid:
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
        vid = self._current_video_id()
        if not vid:
            return
        for candidate in (
            final_labelled_dir(self._session.getName(), self._project_id, vid) / "tracking.csv",
        ):
            if candidate.is_file():
                self.send_to_verify.emit(str(candidate))
                return
        QMessageBox.information(self, "Pose datasets", "Merge or export a CSV first.")
