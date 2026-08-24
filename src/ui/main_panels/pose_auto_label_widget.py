"""Pose Studio — constrained auto-label (blob heatmap + temporal propagation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app_platform.paths import human_labelled_dir, pose_models_dir, pose_video_dir
from core.pose.inference.auto_label_propagate import (
    first_complete_seed_frame,
    nearest_complete_seed_frame,
    seed_frame_is_complete,
)
from core.pose.inference.heatmap_store import (
    HeatmapArchive,
    archive_is_complete,
    archive_missing_frames,
    delete_heatmap_archive,
    list_heatmap_archives,
)
from core.pose.labeling.labels_store import load_labels
from core.pose.training.analyze_progress import total_analyze_frames
from core.pose.training.dlc_bundle import (
    DLC_WORK_DIRNAME,
    find_train_job_path,
)
from core.pose.training.model_registry import (
    AnalyzeCheckpoint,
    ModelRun,
    list_analyze_checkpoints,
    list_model_runs,
    pick_default_checkpoint,
)
from core.pose.video.video_registry import read_video_meta
from session.session import Session
from ui.popup_panels.pose_train_dialog import PoseJobDialog
from ui.components.widgets.artifact_file_list import ArtifactEntry, ArtifactFileList
from ui.workers.gpu_probe_worker import GpuProbeWorker
from ui.workers.pose_subprocess_worker import PoseSubprocessWorker


class PoseAutoLabelWidget(QWidget):
    """Propagate labels from a human seed frame with constrained heatmap decode."""

    labels_exported = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseAutoLabelWidget")
        self._session: Session | None = None
        self._project_id = "default"
        self._video_id: str | None = None
        self._dlc_python: str = ""
        self._job_path: Path | None = None
        self._model_runs: list[ModelRun] = []
        self._subprocess_worker: PoseSubprocessWorker | None = None
        self._gpu_probe_worker: GpuProbeWorker | None = None
        self._heatmap_archives: list[HeatmapArchive] = []
        self._cuda_available = False

        root = QVBoxLayout(self)

        self._status_lbl = QLabel("Open a session and select a video.")
        self._status_lbl.setObjectName("SettingsHintLabel")
        self._status_lbl.setWordWrap(True)
        root.addWidget(self._status_lbl)

        model_box = QGroupBox("Model checkpoint")
        ml = QVBoxLayout(model_box)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Weights"))
        self._checkpoint_combo = QComboBox()
        self._checkpoint_combo.setMinimumWidth(220)
        mrow.addWidget(self._checkpoint_combo, stretch=1)
        ml.addLayout(mrow)
        self._gpu = QCheckBox("Use GPU (NVIDIA CUDA)")
        self._gpu.setToolTip(
            "Requires an NVIDIA GPU with CUDA-enabled PyTorch in the DLC conda env"
        )
        ml.addWidget(self._gpu)
        root.addWidget(model_box)

        heatmap_box = QGroupBox("Saved heatmaps")
        hf = QFormLayout(heatmap_box)
        self._use_saved_heatmaps_cb = QCheckBox("Use saved heatmaps (skip model inference)")
        self._use_saved_heatmaps_cb.setToolTip(
            "Re-run constrained decode from heatmaps already on disk. "
            "Adjust seed frame and decode settings below, then Run Auto Label."
        )
        self._use_saved_heatmaps_cb.toggled.connect(self._on_use_saved_heatmaps_toggled)
        hf.addRow("", self._use_saved_heatmaps_cb)
        self._finish_labeling_cb = QCheckBox("Finish labeling (infer missing frames into archive)")
        self._finish_labeling_cb.setToolTip(
            "Run the model only for frames missing heatmaps in the selected archive, "
            "then decode all frames. New heatmaps are written into the same archive folder."
        )
        self._finish_labeling_cb.toggled.connect(self._on_finish_labeling_toggled)
        hf.addRow("", self._finish_labeling_cb)
        self._heatmap_combo = QComboBox()
        self._heatmap_combo.setMinimumWidth(260)
        self._heatmap_combo.setToolTip("Folder of per-frame heatmap .npz archives under ai_labelled/.")
        self._heatmap_combo.currentIndexChanged.connect(self._on_heatmap_archive_changed)
        hf.addRow("Archive", self._heatmap_combo)
        self._heatmap_file_list = ArtifactFileList()
        self._heatmap_file_list.delete_requested.connect(self._on_delete_heatmap_archive)
        hf.addRow("", self._heatmap_file_list)
        root.addWidget(heatmap_box)

        seed_box = QGroupBox("Seed frame (human labels)")
        sf = QFormLayout(seed_box)
        seed_row = QHBoxLayout()
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(0, 999_999)
        self._seed_spin.setToolTip(
            "First frame used as ground truth. All bodyparts must be labeled on this frame."
        )
        self._seed_spin.valueChanged.connect(self._refresh_seed_status)
        seed_row.addWidget(self._seed_spin, stretch=1)
        self._pick_seed_btn = QPushButton("Use first complete frame")
        self._pick_seed_btn.setToolTip(
            "Set the seed to the earliest frame with every bodypart labeled."
        )
        self._pick_seed_btn.clicked.connect(self._on_pick_first_complete_seed)
        seed_row.addWidget(self._pick_seed_btn)
        sf.addRow("Seed frame", seed_row)
        root.addWidget(seed_box)

        decode_box = QGroupBox("Constrained decode")
        df = QFormLayout(decode_box)
        self._radius_spin = QDoubleSpinBox()
        self._radius_spin.setRange(5.0, 200.0)
        self._radius_spin.setValue(45.0)
        self._radius_spin.setSuffix(" px")
        self._likelihood_spin = QDoubleSpinBox()
        self._likelihood_spin.setRange(0.05, 0.99)
        self._likelihood_spin.setSingleStep(0.05)
        self._likelihood_spin.setValue(0.6)
        self._bone_ratio_spin = QDoubleSpinBox()
        self._bone_ratio_spin.setRange(1.2, 4.0)
        self._bone_ratio_spin.setSingleStep(0.1)
        self._bone_ratio_spin.setValue(2.0)
        self._save_heatmaps_cb = QCheckBox("Save full crop heatmaps to disk")
        self._save_heatmaps_cb.setChecked(True)
        df.addRow("Search radius", self._radius_spin)
        df.addRow("Min likelihood", self._likelihood_spin)
        df.addRow("Bone stretch flag", self._bone_ratio_spin)
        df.addRow("", self._save_heatmaps_cb)
        root.addWidget(decode_box)

        row = QHBoxLayout()
        self._run_btn = QPushButton("Run Auto Label…")
        self._run_btn.clicked.connect(self._on_run)
        row.addWidget(self._run_btn)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)

    def set_dlc_python(self, path: str) -> None:
        self._dlc_python = (path or "").strip()

    def load_session(self, session: Session | None, project_id: str = "default") -> None:
        self._session = session
        self._project_id = project_id
        self._restore_job_path()
        self._refresh_model_lists()
        self._refresh_heatmap_archives()
        self._auto_pick_seed_if_needed()
        self._refresh_seed_status()
        self._sync_enabled()

    def set_video_id(self, video_id: str | None) -> None:
        self._video_id = video_id
        self._refresh_heatmap_archives()
        self._auto_pick_seed_if_needed()
        self._refresh_seed_status()
        self._sync_enabled()

    def _restore_job_path(self) -> None:
        self._job_path = None
        if self._session is None:
            return
        path = find_train_job_path(self._session.getName(), self._project_id)
        if path is not None:
            self._job_path = path

    def _human_labels(self):
        if self._session is None or not self._video_id:
            return None
        return load_labels(
            human_labelled_dir(self._session.getName(), self._project_id, self._video_id)
        )

    def _auto_pick_seed_if_needed(self) -> None:
        ds = self._human_labels()
        if ds is None:
            return
        seed = self._seed_spin.value()
        ok, _ = seed_frame_is_complete(ds, seed)
        if ok:
            return
        picked = nearest_complete_seed_frame(ds, seed)
        if picked is not None:
            self._seed_spin.blockSignals(True)
            self._seed_spin.setValue(picked)
            self._seed_spin.blockSignals(False)

    def _on_pick_first_complete_seed(self) -> None:
        ds = self._human_labels()
        if ds is None:
            return
        picked = first_complete_seed_frame(ds)
        if picked is None:
            QMessageBox.warning(
                self,
                "Auto Label",
                "No frame has all bodyparts labeled yet. Complete one full frame on the Label tab.",
            )
            return
        self._seed_spin.setValue(picked)
        self._refresh_seed_status()
        self._sync_enabled()

    def _refresh_seed_status(self) -> None:
        ds = self._human_labels()
        seed = self._seed_spin.value()
        if ds is None:
            self._status_lbl.setText("Select a video with human labels.")
            return
        ok, missing = seed_frame_is_complete(ds, seed)
        complete = first_complete_seed_frame(ds)
        if ok:
            self._status_lbl.setText(
                f"Seed frame {seed}: all {len(ds.bodyparts())} bodyparts labeled. "
                "Ready to propagate forward and backward."
            )
        else:
            hint = ""
            if complete is not None:
                hint = f" Try seed frame {complete} (first complete frame), or click Use first complete frame."
            self._status_lbl.setText(
                f"Seed frame {seed}: missing {len(missing)} bodypart(s) "
                f"({', '.join(missing[:5])}{'…' if len(missing) > 5 else ''})."
                f"{hint}"
            )

    def _using_saved_heatmaps(self) -> bool:
        return self._use_saved_heatmaps_cb.isChecked() and self._use_saved_heatmaps_cb.isEnabled()

    def _finishing_archive(self) -> bool:
        return self._finish_labeling_cb.isChecked() and self._finish_labeling_cb.isEnabled()

    def _selected_heatmap_archive(self) -> HeatmapArchive | None:
        key = self._heatmap_combo.currentData()
        if not key:
            return None
        for archive in self._heatmap_archives:
            if archive.key == key:
                return archive
        return None

    def _refresh_heatmap_archives(self) -> None:
        self._heatmap_archives = []
        self._heatmap_combo.blockSignals(True)
        self._heatmap_combo.clear()
        if self._session is not None and self._video_id:
            self._heatmap_archives = list_heatmap_archives(
                self._session.getName(),
                self._project_id,
                self._video_id,
            )
            for archive in self._heatmap_archives:
                self._heatmap_combo.addItem(archive.label, archive.key)
        has_archives = bool(self._heatmap_archives)
        self._use_saved_heatmaps_cb.setEnabled(has_archives)
        self._heatmap_combo.setEnabled(has_archives and self._using_saved_heatmaps())
        if not has_archives:
            self._use_saved_heatmaps_cb.setChecked(False)
            self._heatmap_combo.setToolTip(
                "No saved heatmaps for this video yet. Run Auto Label with "
                "\"Save full crop heatmaps\" enabled to create an archive."
            )
        else:
            self._heatmap_combo.setToolTip(
                "Folder of per-frame heatmap .npz archives under ai_labelled/."
            )
        self._heatmap_combo.blockSignals(False)
        self._refresh_heatmap_file_list()
        self._sync_finish_labeling_state()
        self._sync_inference_controls()
        self._sync_enabled()

    def _archive_missing_count(self, archive: HeatmapArchive | None) -> int:
        if archive is None:
            return 0
        total = self._frame_count()
        if total <= 0:
            return 0
        return len(archive_missing_frames(archive.path, total))

    def _sync_finish_labeling_state(self) -> None:
        archive = self._selected_heatmap_archive()
        missing = self._archive_missing_count(archive)
        can_finish = archive is not None and missing > 0
        self._finish_labeling_cb.blockSignals(True)
        self._finish_labeling_cb.setEnabled(can_finish)
        if not can_finish:
            self._finish_labeling_cb.setChecked(False)
        elif self._finish_labeling_cb.isChecked():
            self._use_saved_heatmaps_cb.setChecked(False)
        if can_finish and not self._finish_labeling_cb.isChecked():
            self._finish_labeling_cb.setToolTip(
                f"Infer heatmaps for {missing:,} missing frame(s) into the selected archive, "
                "then decode labels."
            )
        self._finish_labeling_cb.blockSignals(False)
        if archive is not None and missing > 0 and self._using_saved_heatmaps():
            self._heatmap_combo.setToolTip(
                f"Archive has {archive.frame_count:,} / {self._frame_count():,} frames. "
                "Enable Finish labeling to infer the rest."
            )
        elif archive is not None and missing == 0 and self._frame_count() > 0:
            self._heatmap_combo.setToolTip(
                "Archive is complete for this video — re-decode without re-running the model."
            )

    def _on_heatmap_archive_changed(self, _index: int) -> None:
        self._sync_finish_labeling_state()
        self._sync_inference_controls()
        self._sync_enabled()

    def _on_finish_labeling_toggled(self, checked: bool) -> None:
        if checked:
            self._use_saved_heatmaps_cb.blockSignals(True)
            self._use_saved_heatmaps_cb.setChecked(False)
            self._use_saved_heatmaps_cb.blockSignals(False)
        self._heatmap_combo.setEnabled(bool(self._heatmap_archives))
        self._sync_inference_controls()
        self._sync_enabled()

    def _refresh_heatmap_file_list(self) -> None:
        entries = [
            ArtifactEntry(key=archive.key, label=archive.label, path=archive.path)
            for archive in self._heatmap_archives
        ]
        self._heatmap_file_list.set_entries(entries)

    def _on_delete_heatmap_archive(self, key: str) -> None:
        archive = next((a for a in self._heatmap_archives if a.key == key), None)
        if archive is None:
            return
        if (
            QMessageBox.question(
                self,
                "Delete heatmaps",
                f"Delete saved heatmap archive from disk?\n\n{archive.label}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            delete_heatmap_archive(archive.path)
        except OSError as exc:
            QMessageBox.critical(self, "Delete heatmaps", str(exc))
            return
        if self._heatmap_combo.currentData() == key:
            self._heatmap_combo.setCurrentIndex(-1)
        self._refresh_heatmap_archives()

    def _on_use_saved_heatmaps_toggled(self, checked: bool) -> None:
        if checked:
            self._finish_labeling_cb.blockSignals(True)
            self._finish_labeling_cb.setChecked(False)
            self._finish_labeling_cb.blockSignals(False)
        self._heatmap_combo.setEnabled(
            (checked or self._finishing_archive()) and bool(self._heatmap_archives)
        )
        self._sync_inference_controls()
        self._sync_enabled()

    def _sync_inference_controls(self) -> None:
        use_saved = self._using_saved_heatmaps()
        finishing = self._finishing_archive()
        needs_model = not use_saved or finishing
        self._checkpoint_combo.setEnabled(needs_model)
        self._gpu.setEnabled(self._cuda_available and needs_model)
        if use_saved or finishing:
            self._save_heatmaps_cb.setChecked(False)
        self._save_heatmaps_cb.setEnabled(not use_saved and not finishing)

    def _disable_reason(self) -> str:
        if self._session is None:
            return "Open a session first."
        if not self._video_id:
            return "Select a video in the Videos tab."
        ds = self._human_labels()
        if ds is None:
            return "Human labels not found for this video."
        ok, missing = seed_frame_is_complete(ds, self._seed_spin.value())
        if not ok:
            return (
                f"Seed frame {self._seed_spin.value()} is missing: {', '.join(missing[:6])}"
                f"{'…' if len(missing) > 6 else ''}."
            )
        if self._finishing_archive():
            archive = self._selected_heatmap_archive()
            if archive is None:
                return "Select a heatmap archive to finish."
            missing = self._archive_missing_count(archive)
            if missing <= 0:
                return "Selected archive already has heatmaps for every frame."
            if self._job_path is None or not self._job_path.is_file():
                return "No training bundle — train a model on the Train tab first."
            if self._checkpoint_combo.count() == 0:
                return "No model checkpoint on disk — train a model first."
            return ""
        if self._using_saved_heatmaps():
            if not self._selected_heatmap_archive():
                return "Select a saved heatmap archive."
            return ""
        if self._job_path is None or not self._job_path.is_file():
            return "No training bundle — train a model on the Train tab first."
        if self._checkpoint_combo.count() == 0:
            return "No model checkpoint on disk — train a model first."
        return ""

    def _sync_enabled(self) -> None:
        reason = self._disable_reason()
        enabled = not reason
        self._run_btn.setEnabled(enabled)
        self._run_btn.setToolTip(
            "Propagate from the seed frame through all frames into ai_labelled/."
            if enabled
            else reason
        )

    def _refresh_model_lists(self) -> None:
        self._checkpoint_combo.blockSignals(True)
        self._checkpoint_combo.clear()
        self._model_runs = []
        if self._session is not None:
            self._model_runs = list_model_runs(self._session.getName(), self._project_id)
            work_dir = (
                self._job_path.parent
                if self._job_path is not None
                else pose_models_dir(self._session.getName(), self._project_id) / DLC_WORK_DIRNAME
            )
            fallback = self._model_runs[0] if self._model_runs else None
            options: list[AnalyzeCheckpoint] = []
            if work_dir.is_dir():
                options = list_analyze_checkpoints(work_dir, fallback_run=fallback)
            for opt in options:
                self._checkpoint_combo.addItem(opt.label, opt.key)
            default = pick_default_checkpoint(options)
            if default is not None:
                idx = self._checkpoint_combo.findData(default.key)
                if idx >= 0:
                    self._checkpoint_combo.setCurrentIndex(idx)
        self._checkpoint_combo.blockSignals(False)
        if self._session is not None:
            self._probe_gpu()
        self._sync_inference_controls()
        self._sync_enabled()

    def _probe_gpu(self) -> None:
        python_exe = self._dlc_python or sys.executable
        if self._gpu_probe_worker is not None and self._gpu_probe_worker.isRunning():
            return
        self._gpu.setToolTip("Checking GPU availability…")
        self._gpu_probe_worker = GpuProbeWorker(python_exe, self)
        self._gpu_probe_worker.finished_ok.connect(self._on_gpu_probe_done)
        self._gpu_probe_worker.finished.connect(self._on_gpu_probe_finished)
        self._gpu_probe_worker.start()

    def _on_gpu_probe_finished(self) -> None:
        self._gpu_probe_worker = None

    def _on_gpu_probe_done(self, status) -> None:
        self._cuda_available = status.cuda_available
        self._gpu.setEnabled(self._cuda_available and (not self._using_saved_heatmaps() or self._finishing_archive()))
        tip = (status.summary or "").strip() or (
            "Requires an NVIDIA GPU with CUDA-enabled PyTorch in the DLC conda env"
        )
        self._gpu.setToolTip(tip)
        if not status.cuda_available:
            self._gpu.setChecked(False)
        self._sync_inference_controls()

    def _selected_checkpoint(self) -> AnalyzeCheckpoint | None:
        key = self._checkpoint_combo.currentData()
        if not key or self._job_path is None:
            return None
        work_dir = self._job_path.parent
        fallback = self._model_runs[0] if self._model_runs else None
        for opt in list_analyze_checkpoints(work_dir, fallback_run=fallback):
            if opt.key == key:
                return opt
        return None

    def _write_job_for_auto_label(self, checkpoint: AnalyzeCheckpoint | None) -> None:
        if self._job_path is None:
            return
        job = json.loads(self._job_path.read_text(encoding="utf-8"))
        if checkpoint is not None:
            job["snapshot_path"] = str(checkpoint.path)
            job["snapshot_label"] = checkpoint.label
            if checkpoint.epoch is not None:
                job["snapshot_epoch"] = checkpoint.epoch
        else:
            job.pop("snapshot_path", None)
            job.pop("snapshot_label", None)
            job.pop("snapshot_epoch", None)
        archive = self._selected_heatmap_archive()
        use_saved = self._using_saved_heatmaps()
        finishing = self._finishing_archive()
        job["auto_label"] = {
            "seed_frame": self._seed_spin.value(),
            "search_radius_px": self._radius_spin.value(),
            "min_likelihood": self._likelihood_spin.value(),
            "bone_stretch_ratio": self._bone_ratio_spin.value(),
            "save_heatmaps": self._save_heatmaps_cb.isChecked() and not use_saved and not finishing,
            "use_existing_heatmaps": use_saved,
            "finish_incomplete_archive": finishing,
            "heatmap_source_dir": str(archive.path) if archive is not None else None,
        }
        if self._video_id:
            job["video_ids"] = [self._video_id]
        self._job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")

    def _frame_count(self) -> int:
        if self._session is None or not self._video_id:
            return 0
        vdir = pose_video_dir(self._session.getName(), self._project_id, self._video_id)
        meta = read_video_meta(vdir)
        return meta.frame_count if meta and meta.frame_count > 0 else 0

    def _gpu_ok(self, title: str) -> bool:
        if self._gpu.isChecked() and not self._gpu.isEnabled():
            QMessageBox.warning(
                self,
                title,
                "CUDA GPU is not available in the DLC Python environment.\n\n"
                f"{self._gpu.toolTip()}",
            )
            return False
        return True

    def _run_job_dialog(self, *, total_frames: int, use_gpu: bool = False) -> PoseJobDialog | None:
        if self._job_path is None or not self._job_path.is_file():
            QMessageBox.warning(self, "Auto Label", "Could not find train_job.json.")
            return None
        python_exe = self._dlc_python or sys.executable
        dlg = PoseJobDialog(
            self,
            python_exe=python_exe,
            job_path=self._job_path,
            step="auto_label",
            title="Auto Label",
            total_frames=total_frames,
            use_gpu=use_gpu,
        )
        self._subprocess_worker = dlg.worker
        try:
            dlg.exec_()
        finally:
            self._subprocess_worker = None
        return dlg

    def _on_run(self) -> None:
        reason = self._disable_reason()
        if reason:
            QMessageBox.warning(self, "Auto Label", reason)
            return
        if self._session is None or not self._video_id:
            return
        archive = self._selected_heatmap_archive()
        use_saved = self._using_saved_heatmaps()
        finishing = self._finishing_archive()
        checkpoint = None if use_saved else self._selected_checkpoint()
        if not use_saved and checkpoint is None:
            QMessageBox.warning(self, "Auto Label", "No model checkpoint available.")
            return
        if not use_saved and not self._gpu_ok("Auto Label"):
            return
        if (use_saved or finishing) and self._job_path is None:
            QMessageBox.warning(self, "Auto Label", "Could not find train_job.json for this project.")
            return

        self._write_job_for_auto_label(checkpoint)
        job = json.loads(self._job_path.read_text(encoding="utf-8"))
        total_frames = self._frame_count() or total_analyze_frames(job)

        dlg = self._run_job_dialog(
            total_frames=total_frames,
            use_gpu=(finishing or not use_saved) and self._gpu.isChecked(),
        )
        if dlg is None:
            return
        if dlg.result() == dlg.Accepted:
            self._refresh_heatmap_archives()
            self.labels_exported.emit()
            QMessageBox.information(
                self,
                "Auto Label",
                "Constrained labels saved under ai_labelled/.\n\n"
                "Open Verify Labels to review and fix outliers.",
            )
