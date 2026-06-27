"""Pose Studio Step 4 — train and predict tab."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
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

from app_platform.paths import pose_models_dir
from core.pose.training.dlc_bundle import (
    MIN_LABELED_FRAMES,
    RECOMMENDED_LABELED_FRAMES,
    ProjectLabelStats,
    gather_project_label_stats,
)
from core.pose.training.gpu_support import probe_pose_gpu
from core.pose.dataset.retrain_loop import (
    append_retrain_log,
    import_project_sources_into_human,
    total_points_added,
)
from session.session import Session
from ui.popup_panels.pose_train_dialog import PoseTrainDialog
from ui.workers.prepare_training_bundle_worker import PrepareTrainingBundleWorker


class PoseTrainWidget(QWidget):
    """Train model (DLC subprocess) after sufficient human labels."""

    labels_imported = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseTrainWidget")
        self._session: Session | None = None
        self._project_id: str = "default"
        self._dlc_python: str = ""

        root = QVBoxLayout(self)
        intro = QLabel(
            "Train a pose model on human labels (DLC 3 PyTorch in an isolated subprocess). "
            f"Minimum {MIN_LABELED_FRAMES} labeled frames; {RECOMMENDED_LABELED_FRAMES}+ recommended. "
            "Install the pose conda env later (see environment-pose.yml); until then training runs in simulated mode."
        )
        intro.setWordWrap(True)
        intro.setObjectName("SettingsHintLabel")
        root.addWidget(intro)

        self._stats_lbl = QLabel("Open a session with labeled videos.")
        self._stats_lbl.setObjectName("SettingsHintLabel")
        root.addWidget(self._stats_lbl)

        opts = QGroupBox("Training options")
        form = QFormLayout(opts)
        self._epochs = QSpinBox()
        self._epochs.setRange(1, 500)
        self._epochs.setValue(50)
        form.addRow("Epochs", self._epochs)
        self._gpu = QCheckBox("Use GPU (NVIDIA CUDA)")
        self._gpu.setChecked(False)
        self._gpu.setToolTip(
            "Requires an NVIDIA GPU with CUDA-enabled PyTorch in the DLC conda env."
        )
        form.addRow(self._gpu)
        self._gpu_status = QLabel("")
        self._gpu_status.setObjectName("SettingsHintLabel")
        self._gpu_status.setWordWrap(True)
        form.addRow(self._gpu_status)
        root.addWidget(opts)

        row = QHBoxLayout()
        self._prepare_btn = QPushButton("Prepare training bundle")
        self._prepare_btn.clicked.connect(self._on_prepare)
        self._train_btn = QPushButton("Train Model…")
        self._train_btn.clicked.connect(self._on_train)
        self._train_btn.setEnabled(False)
        row.addWidget(self._prepare_btn)
        row.addWidget(self._train_btn)
        row.addStretch(1)
        root.addLayout(row)

        retrain_box = QGroupBox("Retrain loop")
        rl = QVBoxLayout(retrain_box)
        self._iter_lbl = QLabel("Iteration: 0")
        self._iter_lbl.setObjectName("SettingsHintLabel")
        rl.addWidget(self._iter_lbl)
        rrow = QHBoxLayout()
        self._import_ai_btn = QPushButton("Import AI into human labels")
        self._import_ai_btn.setToolTip(
            "Fill gaps in human_labelled from ai_labelled (manual points are kept)."
        )
        self._import_ai_btn.clicked.connect(self._on_import_ai)
        self._retrain_btn = QPushButton("Merge & Retrain…")
        self._retrain_btn.setToolTip(
            "Import AI gaps for all videos, rebuild training bundle, then train."
        )
        self._retrain_btn.clicked.connect(self._on_merge_retrain)
        rrow.addWidget(self._import_ai_btn)
        rrow.addWidget(self._retrain_btn)
        rrow.addStretch(1)
        rl.addLayout(rrow)
        root.addWidget(retrain_box)

        self._status = QLabel("")
        self._status.setObjectName("SettingsHintLabel")
        root.addWidget(self._status)
        root.addStretch(1)

        self._job_path: Path | None = None
        self._bundle_worker: PrepareTrainingBundleWorker | None = None
        self._loading_dots = 0
        self._loading_base = ""
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading_label)
        self._pending_merge_retrain: dict | None = None

    def _train_action_buttons(self) -> tuple[QPushButton, ...]:
        return (
            self._prepare_btn,
            self._train_btn,
            self._import_ai_btn,
            self._retrain_btn,
        )

    def _set_train_busy(self, message: str) -> None:
        self._loading_base = message
        self._loading_dots = 0
        self._tick_loading_label()
        self._loading_timer.start(400)
        for btn in self._train_action_buttons():
            btn.setEnabled(False)

    def _clear_train_busy(self) -> None:
        self._loading_timer.stop()
        self._loading_base = ""
        for btn in self._train_action_buttons():
            btn.setEnabled(True)
        if self._job_path is None or not self._job_path.is_file():
            self._train_btn.setEnabled(False)

    def _tick_loading_label(self) -> None:
        if not self._loading_base:
            return
        self._loading_dots = (self._loading_dots + 1) % 4
        self._status.setText(self._loading_base + "." * self._loading_dots)

    def _start_prepare_bundle(
        self,
        *,
        on_success,
        error_title: str = "Train Model",
    ) -> None:
        if self._session is None:
            QMessageBox.warning(self, error_title, "Open a session first.")
            return
        vids = self._session.get_pose_video_ids()
        if not vids:
            QMessageBox.warning(self, error_title, "Upload at least one video.")
            return
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            return
        self._set_train_busy("Preparing training bundle")
        self._bundle_worker = PrepareTrainingBundleWorker(
            self._session.getName(),
            self._project_id,
            vids,
        )
        self._bundle_worker.finished_ok.connect(
            lambda job_path, stats: self._on_prepare_bundle_done(
                job_path, stats, on_success=on_success
            )
        )
        self._bundle_worker.failed.connect(
            lambda msg: self._on_prepare_bundle_failed(msg, error_title=error_title)
        )
        self._bundle_worker.start()

    def _on_prepare_bundle_done(
        self,
        job_path: str,
        stats: ProjectLabelStats,
        *,
        on_success,
    ) -> None:
        self._clear_train_busy()
        self._job_path = Path(job_path)
        self._train_btn.setEnabled(True)
        self._status.setText(
            f"Bundle ready ({stats.total_labeled_frames} frames, "
            f"{self._job_path.parent}). Configure DLC python in Settings if needed."
        )
        self._refresh_stats()
        if on_success is not None:
            on_success(stats)

    def _on_prepare_bundle_failed(self, msg: str, *, error_title: str) -> None:
        self._clear_train_busy()
        if "Need at least" in msg or "No bodyparts" in msg or "No training crop" in msg:
            QMessageBox.warning(self, error_title, msg)
        else:
            QMessageBox.critical(self, error_title, msg)

    def _project_meta(self) -> dict:
        if self._session is None:
            return {}
        return self._session.pose_projects.setdefault(self._project_id, {})

    def _retrain_iteration(self) -> int:
        return int(self._project_meta().get("retrain_iteration", 0) or 0)

    def _bump_retrain_iteration(self) -> int:
        meta = self._project_meta()
        n = self._retrain_iteration() + 1
        meta["retrain_iteration"] = n
        meta["last_retrain_at"] = datetime.now(timezone.utc).isoformat()
        return n

    def set_dlc_python(self, path: str) -> None:
        self._dlc_python = (path or "").strip()
        self._refresh_gpu_status()

    def _refresh_gpu_status(self) -> None:
        python_exe = self._dlc_python or sys.executable
        status = probe_pose_gpu(python_exe)
        self._gpu_status.setText(status.summary)
        self._gpu.setEnabled(status.cuda_available)
        if not status.cuda_available:
            self._gpu.setChecked(False)

    def load_session(self, session: Session | None, project_id: str) -> None:
        self._session = session
        self._project_id = project_id
        self._job_path = None
        self._pending_merge_retrain = None
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            self._bundle_worker.requestInterruption()
        self._clear_train_busy()
        self._train_btn.setEnabled(False)
        self._refresh_stats()
        self._iter_lbl.setText(f"Iteration: {self._retrain_iteration()}")
        self._refresh_gpu_status()

    def _refresh_stats(self) -> None:
        if self._session is None:
            self._stats_lbl.setText("Open a session with labeled videos.")
            return
        vids = self._session.get_pose_video_ids()
        stats = gather_project_label_stats(
            self._session.getName(),
            self._project_id,
            vids,
        )
        if not stats.bodyparts:
            self._stats_lbl.setText("No human labels yet — use the Label tab first.")
            return
        parts = ", ".join(f"{bp}: {stats.per_bodypart.get(bp, 0)}" for bp in stats.bodyparts[:5])
        suffix = "…" if len(stats.bodyparts) > 5 else ""
        ok = "✓" if stats.meets_minimum() else "✗"
        self._stats_lbl.setText(
            f"{ok} {stats.total_labeled_frames} labeled frames across {len(stats.per_video)} video(s). "
            f"Counts: {parts}{suffix}"
        )

    def _on_prepare(self) -> None:
        self._start_prepare_bundle(on_success=None)

    def _on_train(self) -> None:
        if self._job_path is None or not self._job_path.is_file():
            QMessageBox.warning(self, "Train Model", "Prepare the training bundle first.")
            return
        if self._gpu.isChecked() and not self._gpu.isEnabled():
            QMessageBox.warning(
                self,
                "Train Model",
                "CUDA GPU is not available in the DLC Python environment.\n\n"
                f"{self._gpu_status.text()}\n\n"
                "See docs/POSE_DLC_ENV.md for installing CUDA PyTorch.",
            )
            return
        python_exe = self._dlc_python or sys.executable
        dlg = PoseTrainDialog(
            self,
            python_exe=python_exe,
            job_path=self._job_path,
            epochs=self._epochs.value(),
            use_gpu=self._gpu.isChecked(),
        )
        dlg.exec_()
        if self._session is not None:
            proj = self._session.pose_projects.setdefault(self._project_id, {})
            proj["stage"] = "trained"
            models = pose_models_dir(self._session.getName(), self._project_id)
            proj["last_model_dir"] = str(models)
            self._session.save()
        self._status.setText("Training run finished. Check ai_labelled/ for predictions.")

    def _on_import_ai(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Retrain", "Open a session first.")
            return
        vids = self._session.get_pose_video_ids()
        if not vids:
            QMessageBox.warning(self, "Retrain", "No videos in project.")
            return
        results = import_project_sources_into_human(
            self._session.getName(),
            self._project_id,
            vids,
            source="ai",
            only_missing=True,
        )
        added = total_points_added(results)
        self._session.save()
        self.labels_imported.emit()
        self._refresh_stats()
        QMessageBox.information(
            self,
            "Retrain",
            f"Imported {added} AI point(s) into human labels (gaps only).\n"
            "Edit corrections on the Label tab, then Merge & Retrain.",
        )

    def _on_merge_retrain(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Retrain", "Open a session first.")
            return
        vids = self._session.get_pose_video_ids()
        if not vids:
            QMessageBox.warning(self, "Retrain", "No videos in project.")
            return

        self._set_train_busy("Importing AI labels")
        QTimer.singleShot(0, self._merge_retrain_after_import)

    def _merge_retrain_after_import(self) -> None:
        if self._session is None:
            self._clear_train_busy()
            return
        vids = self._session.get_pose_video_ids()
        results = import_project_sources_into_human(
            self._session.getName(),
            self._project_id,
            vids,
            source="ai",
            only_missing=True,
        )
        added = total_points_added(results)
        self.labels_imported.emit()
        self._pending_merge_retrain = {"results": results, "added": added}
        self._set_train_busy("Preparing training bundle")
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            return
        self._bundle_worker = PrepareTrainingBundleWorker(
            self._session.getName(),
            self._project_id,
            vids,
        )
        self._bundle_worker.finished_ok.connect(
            lambda job_path, stats: self._on_prepare_bundle_done(
                job_path, stats, on_success=self._finish_merge_retrain
            )
        )
        self._bundle_worker.failed.connect(
            lambda msg: self._on_prepare_bundle_failed(msg, error_title="Retrain")
        )
        self._bundle_worker.start()

    def _finish_merge_retrain(self, stats: ProjectLabelStats) -> None:
        if self._session is None or self._pending_merge_retrain is None:
            return
        results = self._pending_merge_retrain["results"]
        added = self._pending_merge_retrain["added"]
        self._pending_merge_retrain = None

        iteration = self._bump_retrain_iteration()
        append_retrain_log(
            self._session.getName(),
            self._project_id,
            iteration=iteration,
            import_results=results,
            job_path=self._job_path,
        )
        self._session.save()
        self._iter_lbl.setText(f"Iteration: {iteration}")

        python_exe = self._dlc_python or sys.executable
        dlg = PoseTrainDialog(
            self,
            python_exe=python_exe,
            job_path=self._job_path,
            epochs=self._epochs.value(),
            use_gpu=self._gpu.isChecked(),
        )
        dlg.exec_()

        proj = self._project_meta()
        proj["stage"] = "retrained"
        proj["last_model_dir"] = str(pose_models_dir(self._session.getName(), self._project_id))
        self._session.save()
        self._refresh_stats()
        self._status.setText(
            f"Retrain iteration {iteration} complete "
            f"(imported {added} AI points, {stats.total_labeled_frames} training frames)."
        )
