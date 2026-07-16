"""Pose Studio Step 4 — train and predict tab."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
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
    DLC_WORK_DIRNAME,
    MIN_LABELED_FRAMES,
    RECOMMENDED_LABELED_FRAMES,
    ProjectLabelStats,
    find_train_job_path,
    gather_project_label_stats,
    load_train_job_if_present,
    training_bundle_is_stale,
)
from core.pose.training.dlc_subprocess import (
    SNAPSHOT_SAVE_EPOCHS,
    load_training_loss_breakdown,
    load_training_loss_history,
    reset_training_progress,
    should_skip_create_training_dataset,
)
from core.pose.training.model_registry import (
    AnalyzeCheckpoint,
    ModelRun,
    copy_model_run,
    delete_model_run,
    list_analyze_checkpoints,
    list_model_runs,
    pick_default_checkpoint,
)
from core.pose.dataset.retrain_loop import (
    append_retrain_log,
    import_project_sources_into_human,
    total_points_added,
)
from session.session import Session
from ui.components.pose.training_loss_plot import TrainingLossPlot
from ui.components.widgets.artifact_file_list import ArtifactEntry, ArtifactFileList
from ui.popup_panels.pose_train_dialog import PoseJobDialog
from ui.workers.gpu_probe_worker import GpuProbeWorker
from ui.workers.pose_subprocess_worker import PoseSubprocessWorker
from ui.workers.prepare_training_bundle_worker import PrepareTrainingBundleWorker
from ui.workers.reset_training_progress_worker import ResetTrainingProgressWorker


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
            "Train saves model weights under models/runs/. Use the Auto Label tab "
            "to propagate predictions from a checkpoint. "
            f"Minimum {MIN_LABELED_FRAMES} labeled frames; {RECOMMENDED_LABELED_FRAMES}+ recommended. "
            "Train Model prepares the DLC bundle automatically when needed."
        )
        intro.setWordWrap(True)
        intro.setObjectName("SettingsHintLabel")
        root.addWidget(intro)

        self._stats_lbl = QLabel("Open a session with labeled videos.")
        self._stats_lbl.setObjectName("SettingsHintLabel")
        root.addWidget(self._stats_lbl)

        models_box = QGroupBox("Saved models")
        ml = QVBoxLayout(models_box)
        mrow = QHBoxLayout()
        mrow.addWidget(QLabel("Active model"))
        self._model_combo = QComboBox()
        self._model_combo.setToolTip(
            "Saved training run. Checkpoints below are used by Auto Label."
        )
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        mrow.addWidget(self._model_combo, stretch=1)
        self._refresh_models_btn = QPushButton("Refresh")
        self._refresh_models_btn.clicked.connect(self._refresh_model_list)
        self._copy_model_btn = QPushButton("Copy model…")
        self._copy_model_btn.setToolTip("Copy the selected saved run folder elsewhere.")
        self._copy_model_btn.clicked.connect(self._on_copy_model)
        mrow.addWidget(self._refresh_models_btn)
        mrow.addWidget(self._copy_model_btn)
        ml.addLayout(mrow)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Checkpoint"))
        self._checkpoint_combo = QComboBox()
        self._checkpoint_combo.setToolTip(
            "Weight checkpoint for reference and Auto Label. "
            "Pick an earlier epoch if a later one looks overfit on the loss curve."
        )
        self._checkpoint_combo.currentIndexChanged.connect(self._on_checkpoint_changed)
        crow.addWidget(self._checkpoint_combo, stretch=1)
        ml.addLayout(crow)
        runs_hdr = QLabel("On disk (saved runs)")
        runs_hdr.setObjectName("SettingsHintLabel")
        ml.addWidget(runs_hdr)
        self._runs_file_list = ArtifactFileList()
        self._runs_file_list.delete_requested.connect(self._on_delete_model_run)
        ml.addWidget(self._runs_file_list)
        root.addWidget(models_box)

        opts = QGroupBox("Training options")
        form = QFormLayout(opts)
        self._epochs = QSpinBox()
        self._epochs.setRange(1, 500)
        self._epochs.setValue(50)
        self._epochs.valueChanged.connect(self._refresh_training_progress)
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
        self._progress_lbl = QLabel("Training progress: not started")
        self._progress_lbl.setObjectName("SettingsHintLabel")
        self._progress_lbl.setWordWrap(True)
        form.addRow("Progress", self._progress_lbl)
        reset_row = QHBoxLayout()
        self._reset_progress_btn = QPushButton("Reset training progress")
        self._reset_progress_btn.setToolTip(
            "Delete DLC checkpoints and the saved loss log in models/dlc_work/ so the next "
            f"train starts at epoch 1. Checkpoints are saved every {SNAPSHOT_SAVE_EPOCHS} epochs. "
            "Human labels and the prepared training bundle are kept."
        )
        self._reset_progress_btn.clicked.connect(self._on_reset_training_progress)
        reset_row.addWidget(self._reset_progress_btn)
        reset_row.addStretch(1)
        reset_wrap = QWidget()
        reset_wrap.setLayout(reset_row)
        form.addRow("", reset_wrap)
        self._loss_preview = TrainingLossPlot()
        self._loss_preview.setMaximumHeight(150)
        form.addRow("Loss curve", self._loss_preview)
        root.addWidget(opts)

        row = QHBoxLayout()
        self._train_btn = QPushButton("Train Model…")
        self._train_btn.clicked.connect(self._on_train)
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
            "Import AI gaps for all videos, rebuild training bundle, then train (not analyze)."
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
        self._subprocess_worker: PoseSubprocessWorker | None = None
        self._reset_worker: ResetTrainingProgressWorker | None = None
        self._gpu_probe_worker: GpuProbeWorker | None = None
        self._loading_dots = 0
        self._loading_base = ""
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._tick_loading_label)
        self._pending_merge_retrain: dict | None = None
        self._pending_train_after_bundle: str | None = None
        self._model_runs: list[ModelRun] = []

    def _train_action_buttons(self) -> tuple[QPushButton, ...]:
        return (
            self._train_btn,
            self._import_ai_btn,
            self._retrain_btn,
            self._refresh_models_btn,
            self._copy_model_btn,
            self._reset_progress_btn,
        )

    def _dlc_work_dir(self) -> Path | None:
        if self._job_path is not None:
            return self._job_path.parent
        if self._session is None:
            return None
        return pose_models_dir(self._session.getName(), self._project_id) / DLC_WORK_DIRNAME

    def _refresh_training_progress(self) -> None:
        work_dir = self._dlc_work_dir()
        if work_dir is None or not work_dir.is_dir():
            self._loss_preview.clear()
            self._progress_lbl.setText("Training progress: not started")
            self._reset_progress_btn.setEnabled(self._session is not None)
            return

        history = load_training_loss_breakdown(work_dir)
        target_epochs = self._epochs.value()
        if not history:
            self._loss_preview.clear()
            self._progress_lbl.setText(
                f"Training progress: not started (target {target_epochs} epochs)"
            )
        else:
            self._loss_preview.set_breakdown_history(
                [(row.epoch, row.total_loss, row.heatmap_loss) for row in history]
            )
            last = history[-1]
            loss_bits = [f"total {last.total_loss:.4f}"]
            if last.heatmap_loss is not None:
                loss_bits.append(f"heatmap {last.heatmap_loss:.4f}")
            self._progress_lbl.setText(
                f"Training progress: epoch {last.epoch} / {target_epochs} "
                f"({', '.join(loss_bits)}, {len(history)} epochs logged on disk)"
            )
        self._reset_progress_btn.setEnabled(True)
        self._refresh_checkpoint_list()

    def _on_reset_training_progress(self) -> None:
        work_dir = self._dlc_work_dir()
        if work_dir is None:
            QMessageBox.warning(self, "Reset Training Progress", "Open a session first.")
            return
        if not work_dir.is_dir():
            QMessageBox.information(
                self,
                "Reset Training Progress",
                "No training work folder yet. Train a model first to create one.",
            )
            return

        history = load_training_loss_history(work_dir)
        if not history:
            QMessageBox.information(
                self,
                "Reset Training Progress",
                "There is no saved training progress to reset.",
            )
            return

        last_ep = history[-1][0]
        answer = QMessageBox.question(
            self,
            "Reset Training Progress",
            (
                f"This deletes DLC checkpoints and the loss log for epoch 1–{last_ep} "
                f"in:\n{work_dir}\n\n"
                "Human labels and the prepared training bundle are kept. "
                "The next Train Model run will start from epoch 1.\n\n"
                "Continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        worker = self._subprocess_worker
        if worker is not None and worker.isRunning():
            stop_answer = QMessageBox.question(
                self,
                "Reset Training Progress",
                "A Train Model job is still running. Stop it and delete checkpoints?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if stop_answer != QMessageBox.Yes:
                return
            worker.terminate_process()
            worker.wait(3000)

        if self._reset_worker is not None and self._reset_worker.isRunning():
            return

        self._set_train_busy("Stopping DLC and resetting training progress")
        self._reset_worker = ResetTrainingProgressWorker(work_dir, self)
        self._reset_worker.finished_ok.connect(self._on_reset_training_done)
        self._reset_worker.failed.connect(self._on_reset_training_failed)
        self._reset_worker.finished.connect(self._on_reset_training_thread_finished)
        self._reset_worker.start()

    def _on_reset_training_done(self, cleared: int) -> None:
        self._clear_train_busy()
        self._refresh_training_progress()
        self._status.setText(
            f"Training progress reset (cleared through epoch {cleared}). "
            "Train Model will start from epoch 1."
        )

    def _on_reset_training_failed(self, msg: str) -> None:
        self._clear_train_busy()
        QMessageBox.critical(
            self,
            "Reset Training Progress",
            f"{msg}\n\nIf this persists, close any python.exe running "
            "scripts/run_dlc_step.py in Task Manager, then try again.",
        )

    def _on_reset_training_thread_finished(self) -> None:
        self._reset_worker = None
        self._subprocess_worker = None

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
        self._sync_train_enabled()
        self._refresh_training_progress()

    def _sync_train_enabled(self) -> None:
        self._train_btn.setEnabled(self._can_train())

    def _loss_by_epoch(self) -> dict[int, float]:
        work_dir = self._dlc_work_dir()
        if work_dir is None:
            return {}
        return {
            row.epoch: row.total_loss
            for row in load_training_loss_breakdown(work_dir)
        }

    def _checkpoint_options(self) -> list[AnalyzeCheckpoint]:
        work_dir = self._dlc_work_dir()
        if work_dir is None or not work_dir.is_dir():
            return []
        return list_analyze_checkpoints(
            work_dir,
            loss_by_epoch=self._loss_by_epoch(),
            fallback_run=self._selected_model(),
        )

    def _refresh_checkpoint_list(self) -> None:
        self._checkpoint_combo.blockSignals(True)
        self._checkpoint_combo.clear()
        options = self._checkpoint_options()
        preferred = self._project_meta().get("active_checkpoint_path")
        for opt in options:
            self._checkpoint_combo.addItem(opt.label, opt.key)
        default = pick_default_checkpoint(options, preferred_path=preferred)
        if default is not None:
            idx = self._checkpoint_combo.findData(default.key)
            if idx >= 0:
                self._checkpoint_combo.setCurrentIndex(idx)
        self._checkpoint_combo.blockSignals(False)
        self._sync_train_enabled()

    def _refresh_runs_file_list(self) -> None:
        if self._session is None:
            self._runs_file_list.set_entries([])
            return
        from app_platform.paths import pose_models_dir

        runs_root = pose_models_dir(self._session.getName(), self._project_id) / "runs"
        entries: list[ArtifactEntry] = []
        for run in self._model_runs:
            run_dir = runs_root / run.run_id
            entries.append(
                ArtifactEntry(
                    key=run.run_id,
                    label=run.display_label(),
                    path=run_dir,
                )
            )
        self._runs_file_list.set_entries(entries)

    def _on_delete_model_run(self, run_id: str) -> None:
        if self._session is None:
            return
        entry = self._runs_file_list.entry_for_key(run_id)
        label = entry.label if entry else run_id
        if (
            QMessageBox.question(
                self,
                "Delete model run",
                f"Delete saved model run from disk?\n\n{label}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            != QMessageBox.Yes
        ):
            return
        try:
            delete_model_run(self._session.getName(), self._project_id, run_id)
        except OSError as exc:
            QMessageBox.critical(self, "Delete model run", str(exc))
            return
        meta = self._project_meta()
        if meta.get("active_model_run_id") == run_id:
            meta.pop("active_model_run_id", None)
            self._session.save()
        self._refresh_model_list()
        self._status.setText(f"Deleted model run {label}.")

    def _selected_checkpoint(self) -> AnalyzeCheckpoint | None:
        key = self._checkpoint_combo.currentData()
        if not key:
            return None
        for opt in self._checkpoint_options():
            if opt.key == key:
                return opt
        return None

    def _on_checkpoint_changed(self) -> None:
        opt = self._selected_checkpoint()
        if opt is not None:
            meta = self._project_meta()
            meta["active_checkpoint_path"] = opt.key
            if opt.epoch is not None:
                meta["active_checkpoint_epoch"] = opt.epoch
            elif opt.is_best:
                meta.pop("active_checkpoint_epoch", None)
            if self._session is not None:
                self._session.save()
        self._sync_train_enabled()

    def _project_video_ids(self) -> list[str]:
        if self._session is None:
            return []
        return self._session.get_pose_video_ids()

    def _resolve_job_path(self) -> Path | None:
        if self._job_path is not None and self._job_path.is_file():
            return self._job_path
        if self._session is None:
            return None
        path = find_train_job_path(self._session.getName(), self._project_id)
        return path

    def _bundle_on_disk_is_stale(self) -> bool:
        if self._session is None:
            return True
        job = load_train_job_if_present(self._session.getName(), self._project_id)
        if job is None:
            return True
        return training_bundle_is_stale(
            self._session.getName(),
            self._project_id,
            self._project_video_ids(),
            job,
        )

    def _can_train(self) -> bool:
        if self._session is None:
            return False
        vids = self._project_video_ids()
        if not vids:
            return False
        stats = gather_project_label_stats(
            self._session.getName(),
            self._project_id,
            vids,
        )
        return stats.meets_minimum()

    def _restore_job_path_from_disk(self) -> None:
        path = self._resolve_job_path()
        if path is None or self._bundle_on_disk_is_stale():
            self._job_path = None
            return
        self._job_path = path

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
        self._sync_train_enabled()
        self._status.setText(
            f"Bundle ready ({stats.total_labeled_frames} frames, "
            f"{self._job_path.parent}). Train Model when ready."
        )
        self._refresh_stats()
        if on_success is not None:
            on_success(stats)
        self._refresh_training_progress()
        pending = self._pending_train_after_bundle
        self._pending_train_after_bundle = None
        if pending == "train":
            self._start_train_dialog()

    def _on_prepare_bundle_failed(self, msg: str, *, error_title: str) -> None:
        self._clear_train_busy()
        self._pending_train_after_bundle = None
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
        if self._gpu_probe_worker is not None and self._gpu_probe_worker.isRunning():
            return
        self._gpu_status.setText("Checking GPU availability…")
        self._gpu_probe_worker = GpuProbeWorker(python_exe, self)
        self._gpu_probe_worker.finished_ok.connect(self._on_gpu_probe_done)
        self._gpu_probe_worker.finished.connect(self._on_gpu_probe_finished)
        self._gpu_probe_worker.start()

    def _on_gpu_probe_finished(self) -> None:
        self._gpu_probe_worker = None

    def _on_gpu_probe_done(self, status) -> None:
        self._gpu_status.setText(status.summary)
        self._gpu.setEnabled(status.cuda_available)
        if not status.cuda_available:
            self._gpu.setChecked(False)

    def load_session(self, session: Session | None, project_id: str) -> None:
        self._session = session
        self._project_id = project_id
        self._job_path = None
        self._pending_merge_retrain = None
        self._pending_train_after_bundle = None
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            self._bundle_worker.requestInterruption()
        self._clear_train_busy()
        if self._session is not None:
            self._restore_job_path_from_disk()
        self.refresh_project_context(session, project_id)

    def refresh_project_context(self, session: Session | None, project_id: str) -> None:
        """Refresh counts and models without clearing a valid on-disk training bundle."""
        self._session = session
        self._project_id = project_id
        if self._session is not None:
            self._restore_job_path_from_disk()
        self._refresh_stats()
        self._iter_lbl.setText(f"Iteration: {self._retrain_iteration()}")
        self._refresh_gpu_status()
        self._refresh_model_list()
        self._sync_train_enabled()
        self._refresh_training_progress()

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

    def _on_model_changed(self) -> None:
        self._refresh_checkpoint_list()

    def _refresh_model_list(self) -> None:
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_runs = []
        if self._session is not None:
            self._model_runs = list_model_runs(self._session.getName(), self._project_id)
        for run in self._model_runs:
            self._model_combo.addItem(run.display_label(), run.run_id)
        active = self._project_meta().get("active_model_run_id")
        if active:
            idx = self._model_combo.findData(active)
            if idx >= 0:
                self._model_combo.setCurrentIndex(idx)
        self._model_combo.blockSignals(False)
        self._refresh_checkpoint_list()
        self._refresh_runs_file_list()

    def _selected_model(self) -> ModelRun | None:
        if self._session is None:
            return None
        run_id = self._model_combo.currentData()
        if not run_id:
            return None
        for run in self._model_runs:
            if run.run_id == run_id:
                if Path(run.snapshot_path).is_file():
                    return run
        return None

    def _gpu_ok(self, title: str) -> bool:
        if self._gpu.isChecked() and not self._gpu.isEnabled():
            QMessageBox.warning(
                self,
                title,
                "CUDA GPU is not available in the DLC Python environment.\n\n"
                f"{self._gpu_status.text()}\n\n"
                "See docs/POSE_DLC_ENV.md for installing CUDA PyTorch.",
            )
            return False
        return True

    def _ensure_training_bundle(self, *, error_title: str) -> bool:
        """Prepare the DLC bundle when missing or stale; else start training."""
        if self._session is None:
            QMessageBox.warning(self, error_title, "Open a session first.")
            return False
        if not self._can_train():
            QMessageBox.warning(
                self,
                error_title,
                f"Need at least {MIN_LABELED_FRAMES} labeled frames before training.",
            )
            return False
        self._restore_job_path_from_disk()
        if self._job_path is not None and self._job_path.is_file():
            self._start_train_dialog()
            return True
        self._pending_train_after_bundle = "train"
        self._start_prepare_bundle(on_success=None, error_title=error_title)
        return True

    def _skip_create_dataset_for_train(self) -> bool:
        work_dir = self._dlc_work_dir()
        if work_dir is None:
            return False
        return should_skip_create_training_dataset(work_dir)

    def _run_job_dialog(
        self,
        *,
        step: str,
        title: str,
        total_frames: int = 0,
        skip_create_dataset: bool = False,
    ) -> PoseJobDialog | None:
        job_path = self._resolve_job_path()
        if job_path is None or not job_path.is_file():
            QMessageBox.warning(self, title, "Could not find or prepare the training bundle.")
            return None
        self._job_path = job_path
        python_exe = self._dlc_python or sys.executable
        dlg = PoseJobDialog(
            self,
            python_exe=python_exe,
            job_path=job_path,
            step=step,
            title=title,
            epochs=self._epochs.value(),
            total_frames=total_frames,
            use_gpu=self._gpu.isChecked(),
            skip_create_dataset=skip_create_dataset,
        )
        self._subprocess_worker = dlg.worker
        try:
            dlg.exec_()
        finally:
            self._subprocess_worker = None
        return dlg

    def _start_train_dialog(self) -> None:
        if not self._gpu_ok("Train Model"):
            return
        dlg = self._run_job_dialog(
            step="train",
            title="Train Model",
            skip_create_dataset=self._skip_create_dataset_for_train(),
        )
        if dlg is None or self._session is None:
            return
        if dlg.saved_run:
            meta = self._project_meta()
            meta["stage"] = "trained"
            meta["active_model_run_id"] = dlg.saved_run.get("run_id")
            meta["last_model_dir"] = str(pose_models_dir(self._session.getName(), self._project_id))
            self._session.save()
            self._refresh_model_list()
            self._refresh_checkpoint_list()
            self._status.setText(
                f"Training saved as {dlg.saved_run.get('label', 'model run')}. "
                "Use Auto Label to propagate predictions."
            )
        else:
            self._status.setText(
                "Training finished but no model weights were saved. Check dlc_stderr.log."
            )
        self._refresh_training_progress()

    def _on_train(self) -> None:
        self._ensure_training_bundle(error_title="Train Model")

    def _on_copy_model(self) -> None:
        run = self._selected_model()
        if run is None or self._session is None:
            QMessageBox.warning(self, "Copy Model", "Select a saved model first.")
            return
        dest = QFileDialog.getExistingDirectory(self, "Copy model run to…")
        if not dest:
            return
        try:
            out = copy_model_run(
                self._session.getName(),
                self._project_id,
                run,
                Path(dest),
            )
        except Exception as exc:
            QMessageBox.critical(self, "Copy Model", str(exc))
            return
        QMessageBox.information(self, "Copy Model", f"Copied to:\n{out}")

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

        if not self._gpu_ok("Retrain"):
            return
        dlg = self._run_job_dialog(
            step="train",
            title="Retrain Model",
            skip_create_dataset=False,
        )
        if dlg is None:
            return

        proj = self._project_meta()
        proj["stage"] = "retrained"
        if dlg.saved_run:
            proj["active_model_run_id"] = dlg.saved_run.get("run_id")
        proj["last_model_dir"] = str(pose_models_dir(self._session.getName(), self._project_id))
        self._session.save()
        self._refresh_model_list()
        self._refresh_stats()
        self._status.setText(
            f"Retrain iteration {iteration} complete "
            f"(imported {added} AI points, {stats.total_labeled_frames} training frames). "
            "Use Auto Label when ready."
        )
