"""Pose Studio Step 4 — train controller (Model scene hosts chrome)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QVBoxLayout, QWidget

from app_platform.paths import pose_models_dir
from core.pose.training.dlc_bundle import (
    DLC_WORK_DIRNAME,
    MIN_LABELED_FRAMES,
    ProjectLabelStats,
    TRAIN_JOB_FILENAME,
    find_train_job_path,
    gather_project_label_stats,
    load_train_job_if_present,
    training_bundle_is_stale,
)
from core.pose.training.dlc_subprocess import (
    load_training_loss_breakdown,
    load_training_loss_history,
    should_skip_create_training_dataset,
)
from core.pose.training.eta_estimate import estimate_remaining_seconds, format_duration
from core.pose.training.model_registry import (
    AnalyzeCheckpoint,
    ModelRun,
    delete_model_run,
    import_external_model_run,
    install_bundled_model_if_empty,
    list_active_branch_work_dirs,
    list_analyze_checkpoints,
    list_model_runs,
)
from session.session import Session
from ui.components.pose.model_epoch_tree import ModelEpochTree, build_model_tree_nodes
from ui.components.pose.training_loss_plot import TrainingLossPlot
from ui.pose_studio.scenes.model_scene import ModelScene
from ui.workers.gpu_probe_worker import GpuProbeWorker
from ui.workers.pose_subprocess_worker import PoseSubprocessWorker
from ui.workers.prepare_training_bundle_worker import PrepareTrainingBundleWorker
from ui.workers.reset_training_progress_worker import ResetTrainingProgressWorker


class PoseTrainWidget(QWidget):
    """Train model (DLC subprocess) — UI chrome lives on ``ModelScene`` when attached."""

    labels_imported = pyqtSignal()
    model_selection_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PoseTrainWidget")
        self._session: Session | None = None
        self._project_id: str = "default"
        self._dlc_python: str = ""
        self._model_scene: ModelScene | None = None

        # Keep a minimal layout so reparented widgets have a temporary parent.
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self._model_tree = ModelEpochTree()
        self._model_tree.selection_changed.connect(self._on_tree_selection_changed)
        self._model_tree.create_model_requested.connect(self._on_create_new_model)
        self._model_tree.delete_run_requested.connect(self._on_delete_model_run)
        root.addWidget(self._model_tree)

        self._loss_preview = TrainingLossPlot()
        root.addWidget(self._loss_preview, stretch=1)

        self.hide()

        self._job_path: Path | None = None
        self._bundle_worker: PrepareTrainingBundleWorker | None = None
        self._subprocess_worker: PoseSubprocessWorker | None = None
        self._reset_worker: ResetTrainingProgressWorker | None = None
        self._gpu_probe_worker: GpuProbeWorker | None = None
        self._pending_train_after_bundle: str | None = None
        self._model_runs: list[ModelRun] = []
        self._want_new_model_branch = False
        self._train_stop_requested = False
        self._train_running = False
        self._saved_run: dict | None = None
        self._epoch_times: list[float] = []
        self._job_started = 0.0
        self._last_epoch_mark = 0.0

    def attach_to_model_scene(self, scene: ModelScene) -> None:
        """Move tree + loss into the Model scene; wire side controls."""
        self._model_scene = scene
        scene.set_model_tree_widget(self._model_tree)
        self._loss_preview.setMaximumHeight(16777215)
        scene.set_plot_widget(self._loss_preview)

        scene.train_requested.connect(self._on_train)
        scene.stop_train_requested.connect(self._on_stop_train)
        scene.create_model_requested.connect(self._on_create_new_model)
        scene.upload_model_requested.connect(self._on_upload_model)
        scene.dataset_selection_changed.connect(self._on_dataset_selection_changed)
        scene.max_epochs_combo.currentIndexChanged.connect(self._refresh_training_progress)
        scene.reset_progress_btn.clicked.connect(self._on_reset_training_progress)
        scene.save_every_spin.valueChanged.connect(self._persist_save_every)

        meta = self._project_meta()
        if meta.get("max_epochs"):
            scene.set_max_epochs(int(meta["max_epochs"]))
        if meta.get("save_every_n_epochs"):
            scene.save_every_spin.setValue(int(meta["save_every_n_epochs"]))

    def selected_model_label(self) -> str:
        return self._model_tree.selected_label()

    def selected_dataset_summary(self) -> str:
        ids = self._training_video_ids()
        if not ids:
            return "—"
        if len(ids) == 1:
            return ids[0]
        return f"{len(ids)} videos"

    def _scene(self) -> ModelScene | None:
        return self._model_scene

    def _set_status(self, text: str, *, tooltip: str | None = None) -> None:
        scene = self._scene()
        if scene is not None:
            scene.set_status(text, tooltip=tooltip)

    def _epochs_value(self) -> int:
        scene = self._scene()
        if scene is not None:
            return scene.max_epochs()
        return 50

    def _use_gpu(self) -> bool:
        scene = self._scene()
        return bool(scene.use_gpu()) if scene is not None else False

    def _save_every_n(self) -> int:
        scene = self._scene()
        if scene is not None:
            return scene.save_every_n_epochs()
        return 5

    def _training_video_ids(self) -> list[str]:
        scene = self._scene()
        if scene is not None:
            selected = scene.selected_training_source_ids()
            if selected:
                return selected
        return self._all_video_ids()

    def _all_video_ids(self) -> list[str]:
        if self._session is None:
            return []
        return self._session.get_pose_video_ids()

    def _dlc_work_dir(self) -> Path | None:
        meta = self._project_meta()
        branch = meta.get("active_branch_work_dir")
        if branch:
            branch_path = Path(str(branch))
            if branch_path.is_dir():
                return branch_path
        if self._job_path is not None:
            return self._job_path.parent
        if self._session is None:
            return None
        return pose_models_dir(self._session.getName(), self._project_id) / DLC_WORK_DIRNAME

    def _main_dlc_work_dir(self) -> Path | None:
        """Primary ``models/dlc_work`` regardless of active branch."""
        if self._session is None:
            return None
        return pose_models_dir(self._session.getName(), self._project_id) / DLC_WORK_DIRNAME

    def _project_meta(self) -> dict:
        if self._session is None:
            return {}
        return self._session.pose_projects.setdefault(self._project_id, {})

    def _persist_save_every(self, value: int) -> None:
        meta = self._project_meta()
        meta["save_every_n_epochs"] = int(value)
        if self._session is not None:
            self._session.save()

    def _on_dataset_selection_changed(self) -> None:
        meta = self._project_meta()
        meta["training_video_ids"] = self._training_video_ids()
        if self._session is not None:
            self._session.save()
        self._job_path = None  # force re-check stale vs new selection
        self._refresh_stats()
        self._sync_train_enabled()
        self.model_selection_changed.emit()

    def _refresh_training_dataset_list(self) -> None:
        scene = self._scene()
        if scene is None or self._session is None:
            return
        vids = self._all_video_ids()
        stats = gather_project_label_stats(
            self._session.getName(), self._project_id, vids
        )
        items: list[tuple[str, str]] = []
        for vid in vids:
            entry = self._session.get_pose_video_entry(vid) or {}
            name = entry.get("display_name") or vid
            n = int(stats.per_video.get(vid, 0))
            missing = " [missing]" if entry.get("missing") else ""
            items.append((vid, f"{name}{missing} — {n} labeled"))
        preferred = self._project_meta().get("training_video_ids")
        if isinstance(preferred, list) and preferred:
            selected = [str(v) for v in preferred if str(v) in {i[0] for i in items}]
        else:
            selected = [vid for vid, _ in items if stats.per_video.get(vid, 0) > 0] or [
                i[0] for i in items
            ]
        scene.set_training_sources(items, selected_ids=selected)

    def _sync_train_button_label(self) -> None:
        scene = self._scene()
        if scene is None:
            return
        scene.set_train_button_text("Train")
        scene.train_btn.setToolTip(
            "Train or resume in the current work folder. Raise Max Epochs above "
            "the last completed epoch to continue; the loss chart is kept."
        )

    def _refresh_training_progress(self) -> None:
        work_dir = self._dlc_work_dir()
        scene = self._scene()
        target_epochs = self._epochs_value()
        if work_dir is None or not work_dir.is_dir():
            self._loss_preview.clear()
            if scene is not None and not self._train_running:
                scene.progress.reset()
            return

        history = load_training_loss_breakdown(work_dir)
        if not history:
            self._loss_preview.clear()
            if scene is not None and not self._train_running:
                scene.progress.set_progress(
                    0,
                    target_epochs,
                    activity="Training Progress",
                    unit="Epochs",
                )
                scene.progress.set_eta_avg(None)
                scene.progress.set_eta_current(None)
        else:
            self._loss_preview.set_breakdown_history(
                [(row.epoch, row.total_loss, row.heatmap_loss) for row in history]
            )
            last = history[-1]
            if scene is not None and not self._train_running:
                scene.progress.set_progress(
                    last.epoch,
                    target_epochs,
                    activity="Training Progress",
                    unit="Epochs",
                )
                scene.progress.set_eta_avg(None)
                scene.progress.set_eta_current(None)

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
                "The next Train run will start from epoch 1.\n\n"
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
                "A Train job is still running. Stop it and delete checkpoints?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if stop_answer != QMessageBox.Yes:
                return
            worker.terminate_process()
            worker.wait(3000)

        if self._reset_worker is not None and self._reset_worker.isRunning():
            return

        self._set_train_busy("Resetting training progress…")
        self._reset_worker = ResetTrainingProgressWorker(work_dir, self)
        self._reset_worker.finished_ok.connect(self._on_reset_training_done)
        self._reset_worker.failed.connect(self._on_reset_training_failed)
        self._reset_worker.finished.connect(self._on_reset_training_thread_finished)
        self._reset_worker.start()

    def _on_reset_training_done(self, cleared: int) -> None:
        self._clear_train_busy()
        self._refresh_model_list()
        self._refresh_training_progress()
        self._set_status(
            f"Training progress reset (cleared through epoch {cleared}). "
            "Train will start from epoch 1."
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

    def _train_action_buttons(self):
        scene = self._scene()
        if scene is None:
            return ()
        return (
            scene.train_btn,
            scene.reset_progress_btn,
            self._model_tree.create_btn,
            self._model_tree.delete_btn,
            scene.select_all_btn,
            scene.select_none_btn,
        )

    def _set_train_busy(self, message: str) -> None:
        scene = self._scene()
        if scene is not None:
            scene.progress.set_busy_message(message)
            scene.set_status(message)
        for btn in self._train_action_buttons():
            btn.setEnabled(False)
        if scene is not None:
            scene.set_train_controls_enabled(train=False, stop=self._train_running)

    def _clear_train_busy(self) -> None:
        for btn in self._train_action_buttons():
            btn.setEnabled(True)
        self._sync_train_enabled()
        self._refresh_training_progress()

    def _sync_train_enabled(self) -> None:
        scene = self._scene()
        if scene is None:
            return
        can = self._can_train() and not self._train_running
        scene.set_train_controls_enabled(train=can, stop=self._train_running)
        self._sync_train_button_label()

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
        self._refresh_model_list()

    def _on_tree_selection_changed(self) -> None:
        sel = self._model_tree.selection()
        meta = self._project_meta()
        if sel.run_id:
            meta["active_model_run_id"] = sel.run_id
            self._want_new_model_branch = False
        if sel.checkpoint_key:
            meta["active_checkpoint_path"] = sel.checkpoint_key
            if sel.checkpoint_epoch is not None:
                meta["active_checkpoint_epoch"] = sel.checkpoint_epoch
            elif sel.is_best:
                meta.pop("active_checkpoint_epoch", None)
        if self._session is not None:
            self._session.save()
        self._sync_train_enabled()
        self.model_selection_changed.emit()

    def _on_create_new_model(self) -> None:
        self._want_new_model_branch = True
        meta = self._project_meta()
        meta.pop("active_model_run_id", None)
        meta.pop("active_checkpoint_path", None)
        meta.pop("active_checkpoint_epoch", None)
        meta.pop("active_branch_work_dir", None)
        if self._session is not None:
            self._session.save()
        self._model_tree.clear_selection(label="(new model)")
        self._set_status(
            "New model branch selected. Train to create the first epoch; "
            "optionally Reset training progress first for a clean dlc_work."
        )
        self._sync_train_button_label()
        self.model_selection_changed.emit()

    def _on_upload_model(self) -> None:
        if self._session is None:
            QMessageBox.warning(self, "Upload model", "Open a session first.")
            return
        folder = QFileDialog.getExistingDirectory(
            self,
            "Import DeepLabCut model folder",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if not folder:
            return
        try:
            record = import_external_model_run(
                self._session.getName(),
                self._project_id,
                Path(folder),
            )
        except (OSError, FileNotFoundError, ValueError) as exc:
            QMessageBox.critical(self, "Upload model", str(exc))
            return
        meta = self._project_meta()
        meta["active_model_run_id"] = record.run_id
        meta["active_checkpoint_path"] = record.snapshot_path
        self._want_new_model_branch = False
        self._session.save()
        self._refresh_model_list()
        self._set_status(f"Imported model: {record.display_label()}")
        self.model_selection_changed.emit()

    def _on_delete_model_run(self, run_id: str) -> None:
        if self._session is None:
            return
        run = next((r for r in self._model_runs if r.run_id == run_id), None)
        label = run.display_label() if run else run_id
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
        self._set_status(f"Deleted model run {label}.")

    def _selected_model(self) -> ModelRun | None:
        if self._session is None:
            return None
        run_id = self._model_tree.selected_run_id()
        if not run_id:
            return None
        for run in self._model_runs:
            if run.run_id == run_id and Path(run.snapshot_path).is_file():
                return run
        return None

    def _resolve_job_path(self) -> Path | None:
        if self._job_path is not None and self._job_path.is_file():
            return self._job_path
        work_dir = self._dlc_work_dir()
        if work_dir is not None:
            candidate = work_dir / TRAIN_JOB_FILENAME
            if candidate.is_file():
                return candidate
        if self._session is None:
            return None
        return find_train_job_path(self._session.getName(), self._project_id)

    def _bundle_on_disk_is_stale(self) -> bool:
        if self._session is None:
            return True
        job = load_train_job_if_present(self._session.getName(), self._project_id)
        if job is None:
            return True
        return training_bundle_is_stale(
            self._session.getName(),
            self._project_id,
            self._training_video_ids(),
            job,
        )

    def _can_train(self) -> bool:
        if self._session is None:
            return False
        vids = self._training_video_ids()
        if not vids:
            return False
        stats = gather_project_label_stats(
            self._session.getName(),
            self._project_id,
            vids,
        )
        return stats.meets_minimum()

    def set_dlc_python(self, path: str) -> None:
        self._dlc_python = (path or "").strip()
        self._refresh_gpu_status()

    def _refresh_gpu_status(self) -> None:
        python_exe = self._dlc_python or sys.executable
        if self._gpu_probe_worker is not None and self._gpu_probe_worker.isRunning():
            return
        scene = self._scene()
        if scene is not None:
            scene.set_gpu_status("Checking GPU availability…")
        self._gpu_probe_worker = GpuProbeWorker(python_exe, self)
        self._gpu_probe_worker.finished_ok.connect(self._on_gpu_probe_done)
        self._gpu_probe_worker.finished.connect(self._on_gpu_probe_finished)
        self._gpu_probe_worker.start()

    def _on_gpu_probe_finished(self) -> None:
        self._gpu_probe_worker = None

    def _on_gpu_probe_done(self, status) -> None:
        scene = self._scene()
        if scene is None:
            return
        scene.set_gpu_status(status.summary)
        scene.set_gpu_enabled(status.cuda_available)
        if not status.cuda_available:
            scene.set_use_gpu(False)

    def load_session(self, session: Session | None, project_id: str) -> None:
        self._session = session
        self._project_id = project_id
        self._job_path = None
        self._pending_train_after_bundle = None
        self._want_new_model_branch = False
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            self._bundle_worker.requestInterruption()
        self._clear_train_busy()
        if self._session is not None:
            self._restore_job_path_from_disk()
            installed = install_bundled_model_if_empty(
                self._session.getName(), self._project_id
            )
            if installed is not None:
                meta = self._project_meta()
                meta.setdefault("active_model_run_id", installed.run_id)
                meta.setdefault("active_checkpoint_path", installed.snapshot_path)
                self._session.save()
        self.refresh_project_context(session, project_id)

    def refresh_project_context(self, session: Session | None, project_id: str) -> None:
        self._session = session
        self._project_id = project_id
        if self._session is not None:
            self._restore_job_path_from_disk()
        self._refresh_training_dataset_list()
        self._refresh_stats()
        self._refresh_gpu_status()
        self._refresh_model_list()
        self._sync_train_enabled()
        self._refresh_training_progress()

    def _restore_job_path_from_disk(self) -> None:
        path = self._resolve_job_path()
        if path is None or self._bundle_on_disk_is_stale():
            self._job_path = None
            return
        self._job_path = path

    def _refresh_stats(self) -> None:
        scene = self._scene()
        if scene is None:
            return
        if self._session is None:
            scene.set_stats("Open a session with labeled videos.")
            return
        vids = self._training_video_ids()
        if not vids:
            scene.set_stats("Select at least one video in Training dataset.")
            return
        stats = gather_project_label_stats(
            self._session.getName(),
            self._project_id,
            vids,
        )
        if not stats.bodyparts:
            scene.set_stats("No human labels yet — use the Label tab first.")
            return
        all_parts = ", ".join(
            f"{bp}: {stats.per_bodypart.get(bp, 0)}" for bp in stats.bodyparts
        )
        preview_parts = ", ".join(
            f"{bp}: {stats.per_bodypart.get(bp, 0)}" for bp in stats.bodyparts[:5]
        )
        suffix = "…" if len(stats.bodyparts) > 5 else ""
        ok = "✓" if stats.meets_minimum() else "✗"
        need = f" (need {MIN_LABELED_FRAMES}+ to train)" if not stats.meets_minimum() else ""
        summary = (
            f"{ok} {stats.total_labeled_frames} labeled frames in {len(vids)} selected video(s)"
            f"{need}. Counts: {preview_parts}{suffix}"
        )
        full = (
            f"{ok} {stats.total_labeled_frames} labeled frames in {len(vids)} selected video(s)"
            f"{need}.\nCounts: {all_parts}"
        )
        scene.set_stats(summary, tooltip=full)

    def _branch_checkpoints_map(self) -> dict[str, list[AnalyzeCheckpoint]]:
        if self._session is None:
            return {}
        out: dict[str, list[AnalyzeCheckpoint]] = {}
        for branch_dir in list_active_branch_work_dirs(
            self._session.getName(), self._project_id
        ):
            if branch_dir.is_dir():
                ckpts = list_analyze_checkpoints(
                    branch_dir,
                    loss_by_epoch={
                        row.epoch: row.total_loss
                        for row in load_training_loss_breakdown(branch_dir)
                    },
                )
                if ckpts:
                    out[str(branch_dir.resolve())] = ckpts
        return out

    def _current_training_label(self) -> str:
        meta = self._project_meta()
        branch = meta.get("active_branch_work_dir")
        if branch:
            return f"Branch {Path(str(branch)).name}"
        return "Current training"

    def _refresh_model_list(self) -> None:
        self._model_runs = []
        if self._session is not None:
            self._model_runs = list_model_runs(self._session.getName(), self._project_id)
        meta = self._project_meta()
        work_dir = self._dlc_work_dir()
        nodes = build_model_tree_nodes(
            runs=self._model_runs,
            current_label=self._current_training_label(),
            current_checkpoints=self._checkpoint_options(),
            current_work_dir=str(work_dir.resolve()) if work_dir and work_dir.is_dir() else None,
            branch_checkpoints=self._branch_checkpoints_map(),
        )
        if self._want_new_model_branch:
            self._model_tree.set_tree(
                nodes=nodes,
                preferred_run_id=None,
                preferred_checkpoint_key=None,
                select_none=True,
            )
            return
        preferred_run = meta.get("active_model_run_id")
        preferred_ckpt = meta.get("active_checkpoint_path")
        self._model_tree.set_tree(
            nodes=nodes,
            preferred_run_id=str(preferred_run) if preferred_run else None,
            preferred_checkpoint_key=str(preferred_ckpt) if preferred_ckpt else None,
        )

    def _start_prepare_bundle(
        self,
        *,
        on_success,
        error_title: str = "Train",
    ) -> None:
        if self._session is None:
            QMessageBox.warning(self, error_title, "Open a session first.")
            return
        vids = self._training_video_ids()
        if not vids:
            QMessageBox.warning(
                self, error_title, "Select at least one video in Training dataset."
            )
            return
        if self._bundle_worker is not None and self._bundle_worker.isRunning():
            return
        self._set_train_busy("Preparing training bundle…")
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
        self._set_status(
            f"Bundle ready ({stats.total_labeled_frames} frames from "
            f"{len(stats.per_video)} video(s))."
        )
        self._refresh_stats()
        if on_success is not None:
            on_success(stats)
        self._refresh_training_progress()
        pending = self._pending_train_after_bundle
        self._pending_train_after_bundle = None
        if pending == "train":
            self._start_train_in_panel()

    def _on_prepare_bundle_failed(self, msg: str, *, error_title: str) -> None:
        self._clear_train_busy()
        self._pending_train_after_bundle = None
        if "Need at least" in msg or "No bodyparts" in msg or "No training crop" in msg:
            QMessageBox.warning(self, error_title, msg)
        else:
            QMessageBox.critical(self, error_title, msg)

    def _gpu_ok(self, title: str) -> bool:
        scene = self._scene()
        if scene is not None and scene.use_gpu() and not scene.gpu_check.isEnabled():
            QMessageBox.warning(
                self,
                title,
                "CUDA GPU is not available in the DLC Python environment.\n\n"
                f"{scene.gpu_check.toolTip()}\n\n"
                "See docs/POSE_DLC_ENV.md for installing CUDA PyTorch.",
            )
            return False
        return True

    def _ensure_training_bundle(self, *, error_title: str) -> bool:
        if self._session is None:
            QMessageBox.warning(self, error_title, "Open a session first.")
            return False
        if not self._can_train():
            QMessageBox.warning(
                self,
                error_title,
                f"Need at least {MIN_LABELED_FRAMES} labeled frames in the selected "
                "training dataset before training.",
            )
            return False
        meta = self._project_meta()
        meta["max_epochs"] = self._epochs_value()
        meta["save_every_n_epochs"] = self._save_every_n()
        meta["training_video_ids"] = self._training_video_ids()
        self._session.save()
        self._restore_job_path_from_disk()
        if self._job_path is not None and self._job_path.is_file():
            self._start_train_in_panel()
            return True
        self._pending_train_after_bundle = "train"
        self._start_prepare_bundle(on_success=None, error_title=error_title)
        return True

    def _last_completed_epoch(self, work_dir: Path | None = None) -> int:
        path = work_dir if work_dir is not None else self._dlc_work_dir()
        if path is None or not path.is_dir():
            return 0
        history = load_training_loss_history(path)
        if not history:
            return 0
        return int(history[-1][0])

    def _skip_create_dataset_for_train(self) -> bool:
        if self._want_new_model_branch:
            # New model must rebuild shuffles for the current TrainingFraction.
            return False
        work_dir = self._dlc_work_dir()
        if work_dir is None:
            return False
        return should_skip_create_training_dataset(work_dir)

    def _start_train_in_panel(self) -> None:
        if not self._gpu_ok("Train"):
            return
        if self._train_running:
            return
        job_path = self._resolve_job_path()
        if job_path is None or not job_path.is_file():
            QMessageBox.warning(self, "Train", "Could not find or prepare the training bundle.")
            return
        self._job_path = job_path
        work_dir = job_path.parent
        python_exe = self._dlc_python or sys.executable
        epochs = self._epochs_value()
        last_ep = self._last_completed_epoch(work_dir)
        if last_ep >= epochs:
            QMessageBox.information(
                self,
                "Train",
                (
                    f"This model is already trained through epoch {last_ep}. "
                    f"Raise Max Epochs above {last_ep} to resume. "
                    "The loss chart stays in place and new epochs append to it."
                ),
            )
            return

        self._train_running = True
        self._train_stop_requested = False
        self._saved_run = None
        self._epoch_times = []
        self._job_started = time.monotonic()
        self._last_epoch_mark = self._job_started
        scene = self._scene()
        if scene is not None:
            scene.progress.set_progress(
                last_ep,
                epochs,
                activity="Training Progress",
                unit="Epochs",
            )
            scene.progress.set_eta_avg(None)
            scene.progress.set_eta_current(None)
            if last_ep > 0:
                scene.set_status(
                    f"Resuming training from epoch {last_ep} toward {epochs}…"
                )
            else:
                scene.set_status("Training — preparing first epoch…")
        self._sync_train_enabled()

        self._subprocess_worker = PoseSubprocessWorker(
            python_exe=python_exe,
            job_path=job_path,
            step="train",
            epochs=epochs,
            use_gpu=self._use_gpu(),
            work_dir=work_dir,
            skip_create_dataset=self._skip_create_dataset_for_train(),
            save_every_n=self._save_every_n(),
            parent=self,
        )
        self._subprocess_worker.progress.connect(self._on_train_progress)
        self._subprocess_worker.finished_ok.connect(self._on_train_finished)
        self._subprocess_worker.failed.connect(self._on_train_failed)
        self._subprocess_worker.start()

    def _on_stop_train(self) -> None:
        if self._subprocess_worker is not None and self._subprocess_worker.isRunning():
            self._train_stop_requested = True
            self._subprocess_worker.request_stop_after_epoch()
            self._set_status("Stopping after the current epoch…")
            scene = self._scene()
            if scene is not None:
                scene.stop_train_btn.setEnabled(False)

    def _on_train_progress(self, obj: dict) -> None:
        scene = self._scene()
        if scene is None:
            return
        typ = obj.get("type")
        if typ == "epoch":
            ep = int(obj.get("epoch", 0))
            total = int(obj.get("total_epochs", self._epochs_value()))
            now = time.monotonic()
            if self._last_epoch_mark > 0:
                self._epoch_times.append(now - self._last_epoch_mark)
            self._last_epoch_mark = now
            scene.progress.set_progress(
                ep,
                total,
                activity="Training Progress",
                unit="Epochs",
            )
            elapsed = now - self._job_started
            wall = estimate_remaining_seconds(elapsed, ep, total)
            if wall is not None:
                scene.progress.set_eta_avg(format_duration(wall))
            else:
                scene.progress.set_eta_avg(None)
            if len(self._epoch_times) >= 2:
                avg = sum(self._epoch_times[-5:]) / len(self._epoch_times[-5:])
                cur = max(0, int(avg * max(0, total - ep)))
                scene.progress.set_eta_current(format_duration(cur))
            else:
                scene.progress.set_eta_current(None)
            total_loss = obj.get("total_loss")
            heatmap = obj.get("heatmap_loss")
            bits = []
            if total_loss is not None:
                bits.append(f"total {float(total_loss):.4f}")
            if heatmap is not None:
                bits.append(f"heatmap {float(heatmap):.4f}")
            loss_txt = f" ({', '.join(bits)})" if bits else ""
            scene.set_status(f"Training — epoch {ep}/{total}{loss_txt}")
            self._refresh_training_progress()
        elif typ == "model_saved":
            self._saved_run = dict(obj.get("run") or {})
            scene.set_status(str(self._saved_run.get("label", "Model saved")))
        elif typ in ("phase", "status", "heartbeat"):
            message = str(obj.get("message") or obj.get("phase") or "Training…")
            scene.set_status(message)
        elif typ == "stopped":
            self._train_stop_requested = True
            scene.set_status(str(obj.get("message", "Stopped after current epoch.")))

    def _on_train_finished(self, work_dir: str) -> None:
        stopped = self._train_stop_requested
        self._train_running = False
        self._train_stop_requested = False
        self._subprocess_worker = None
        self._clear_train_busy()
        if self._session is None:
            return
        if self._saved_run:
            meta = self._project_meta()
            meta["stage"] = "trained"
            meta["active_model_run_id"] = self._saved_run.get("run_id")
            meta["last_model_dir"] = str(
                pose_models_dir(self._session.getName(), self._project_id)
            )
            meta.pop("active_branch_work_dir", None)
            self._want_new_model_branch = False
            self._session.save()
            self._refresh_model_list()
            self._set_status(
                f"Training saved as {self._saved_run.get('label', 'model run')}. "
                "Use Auto Label to propagate predictions."
            )
        elif stopped or self._last_completed_epoch(Path(work_dir)) > 0:
            last = self._last_completed_epoch(Path(work_dir))
            self._set_status(
                f"Training stopped at epoch {last}. "
                "Raise Max Epochs and click Train to continue from this chart."
            )
        else:
            err_summary, err_full = self._summarize_train_failure(Path(work_dir))
            self._set_status(err_summary, tooltip=err_full)
            QMessageBox.warning(self, "Train", err_full)
        self._refresh_training_progress()
        self.model_selection_changed.emit()

    def _summarize_train_failure(self, work_dir: Path) -> tuple[str, str]:
        """Return (short status, full tooltip/dialog text) from dlc_stderr when no run was saved."""
        log_path = work_dir / "dlc_stderr.log"
        detail = ""
        if log_path.is_file():
            try:
                detail = log_path.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                detail = ""
        # Prefer the last ValueError / Exception line for a readable summary.
        last_err = ""
        for line in reversed(detail.splitlines()):
            s = line.strip()
            if s.startswith("ValueError:") or s.startswith("RuntimeError:") or s.startswith(
                "Exception:"
            ):
                last_err = s
                break
            if "Couldn't find any shuffles" in s or "shuffles" in s.lower() and "Error" in s:
                last_err = s
                break
        if last_err:
            short = f"Training failed before epoch 1: {last_err}"
        else:
            short = (
                f"Training finished without a saved run ({work_dir}). "
                "Check dlc_stderr.log."
            )
        full = short
        if detail:
            # Keep tooltip useful but bounded.
            tail = detail[-2500:] if len(detail) > 2500 else detail
            full = f"{short}\n\n--- dlc_stderr.log ---\n{tail}"
        return short, full

    def _on_train_failed(self, msg: str) -> None:
        stopped = self._train_stop_requested
        self._train_running = False
        self._train_stop_requested = False
        self._subprocess_worker = None
        self._clear_train_busy()
        if stopped:
            last = self._last_completed_epoch()
            self._set_status(
                f"Training stopped at epoch {last}. "
                "Raise Max Epochs and click Train to continue from this chart."
            )
            return
        QMessageBox.critical(self, "Train", msg)
        self._set_status("Training failed.")

    def _on_train(self) -> None:
        self._ensure_training_bundle(error_title="Train")
