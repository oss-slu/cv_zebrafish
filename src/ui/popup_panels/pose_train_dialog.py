"""Pose Studio job progress dialog (train or analyze)."""

from __future__ import annotations

import time
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.pose.training.dlc_subprocess import load_training_loss_breakdown
from core.pose.training.eta_estimate import estimate_remaining_seconds, format_duration
from ui.components.chrome.dialog_title_bar import DialogTitleBar
from ui.components.pose.training_loss_plot import TrainingLossPlot
from ui.platform.frameless_resize import FramelessResizeMixin
from ui.workers.pose_subprocess_worker import PoseSubprocessWorker


class PoseJobDialog(FramelessResizeMixin, QDialog):
    """Run DLC train or analyze with live progress."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        python_exe: str,
        job_path: Path,
        step: str,
        title: str,
        epochs: int = 50,
        total_frames: int = 0,
        use_gpu: bool = False,
        skip_create_dataset: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("PoseJobDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self._job_path = Path(job_path)
        self._work_dir = self._job_path.parent
        self._step = step
        self._epochs = epochs
        self._total_frames = max(0, int(total_frames))
        self._analyze_mode = step in ("analyze", "auto_label")
        self._auto_label_mode = step == "auto_label"
        self._frame_times: list[float] = []
        self._last_frame_mark = 0.0
        self._epoch_times: list[float] = []
        self._last_epoch_mark = 0.0
        self._job_started = 0.0
        self._saved_run: dict | None = None
        self._stopped = False
        self._worker: PoseSubprocessWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, title, self))
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(14, 12, 14, 14)

        self._phase_lbl = QLabel("Preparing…")
        self._phase_lbl.setObjectName("SettingsHintLabel")
        bl.addWidget(self._phase_lbl)

        self._eta_lbl = QLabel("")
        self._eta_lbl.setObjectName("SettingsHintLabel")
        bl.addWidget(self._eta_lbl)

        self._progress = QProgressBar()
        if self._analyze_mode:
            max_val = max(1, self._total_frames)
            self._progress.setRange(0, max_val)
            if self._auto_label_mode:
                self._progress.setFormat("Completed %v / %m")
            else:
                self._progress.setFormat("Frame %v / %m")
            self._progress.setValue(0)
        else:
            self._progress.setRange(0, max(1, epochs))
        bl.addWidget(self._progress)

        self._loss_plot = TrainingLossPlot()
        if self._analyze_mode:
            self._loss_plot.hide()
        bl.addWidget(self._loss_plot, stretch=1)

        btn_row = QHBoxLayout()
        self._stop_btn = QPushButton("Stop after current epoch")
        if self._analyze_mode:
            self._stop_btn.hide()
        self._stop_btn.clicked.connect(self._on_stop)
        self._close_btn = QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._close_btn)
        bl.addLayout(btn_row)

        outer.addWidget(body)
        self.resize(520, 420 if not self._analyze_mode else 220)

        if not self._analyze_mode:
            self._restore_checkpoint_state()

        self._worker = PoseSubprocessWorker(
            python_exe=python_exe,
            job_path=self._job_path,
            step=step,
            epochs=epochs,
            use_gpu=use_gpu,
            work_dir=self._work_dir,
            skip_create_dataset=skip_create_dataset,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    @property
    def worker(self) -> PoseSubprocessWorker | None:
        return self._worker

    @property
    def saved_run(self) -> dict | None:
        return self._saved_run

    def _mark_job_started(self) -> None:
        if self._job_started <= 0:
            now = time.monotonic()
            self._job_started = now
            self._last_epoch_mark = now

    def _restore_checkpoint_state(self) -> None:
        history = load_training_loss_breakdown(self._work_dir)
        if not history:
            return
        self._loss_plot.set_breakdown_history(
            [(row.epoch, row.total_loss, row.heatmap_loss) for row in history]
        )
        last = history[-1]
        self._progress.setValue(last.epoch)
        self._phase_lbl.setText(
            f"Checkpoint on disk — epoch {last.epoch} / {self._epochs} "
            f"({self._format_epoch_losses(last.total_loss, last.heatmap_loss, last.locref_loss)}, "
            f"{len(history)} epochs logged)"
        )
        self._set_eta_label(
            elapsed_s=0,
            completed=last.epoch,
            total=self._epochs,
        )

    @staticmethod
    def _format_epoch_losses(
        total_loss: float,
        heatmap_loss: float | None = None,
        locref_loss: float | None = None,
    ) -> str:
        parts = [f"total {total_loss:.4f}"]
        if heatmap_loss is not None:
            parts.append(f"heatmap {heatmap_loss:.4f}")
        if locref_loss is not None:
            parts.append(f"locref {locref_loss:.4f}")
        return ", ".join(parts)

    def _loss_text_from_progress(self, obj: dict) -> str:
        heatmap = obj.get("heatmap_loss")
        locref = obj.get("locref_loss")
        return self._format_epoch_losses(
            float(obj.get("loss", 0)),
            float(heatmap) if heatmap is not None else None,
            float(locref) if locref is not None else None,
        )

    def _set_eta_label(
        self,
        *,
        elapsed_s: float,
        completed: int,
        total: int,
        pending: str = "",
    ) -> None:
        eta_s = estimate_remaining_seconds(elapsed_s, completed, total)
        if eta_s is not None:
            self._eta_lbl.setText(f"ETA ~ {format_duration(eta_s)}")
        elif pending:
            self._eta_lbl.setText(
                f"Elapsed {format_duration(int(elapsed_s))} — {pending}"
            )
        else:
            self._eta_lbl.setText("")

    def _on_progress(self, obj: dict) -> None:
        typ = obj.get("type")
        if typ == "start":
            self._mark_job_started()
            self._phase_lbl.setText(f"Starting {obj.get('step', self._step)}…")
        elif typ == "phase":
            phase = obj.get("phase", "")
            if phase == "analyze":
                total = int(obj.get("total_frames") or self._total_frames or 0)
                if total > 0:
                    self._total_frames = total
                    self._progress.setRange(0, total)
                    self._progress.setFormat("Frame %v / %m")
                self._phase_lbl.setText(f"Analyzing video — {total or '?'} frames")
            elif phase == "auto_label":
                total = int(obj.get("total_frames") or self._total_frames or 0)
            if total > 0:
                self._total_frames = total
                if self._progress.maximum() != total:
                    self._progress.setRange(0, total)
                    if self._auto_label_mode:
                        self._progress.setFormat("Completed %v / %m")
                    else:
                        self._progress.setFormat("Frame %v / %m")
                self._phase_lbl.setText(f"Auto-labeling — {total or '?'} frames")
            else:
                self._phase_lbl.setText(f"Phase: {phase}")
        elif typ == "analyze_start":
            self._mark_job_started()
            total = int(obj.get("total_frames") or self._total_frames or 0)
            if total > 0:
                self._total_frames = total
                self._progress.setRange(0, total)
                if self._auto_label_mode:
                    self._progress.setFormat("Completed %v / %m")
                else:
                    self._progress.setFormat("Frame %v / %m")
            verb = "Auto-labeling" if self._auto_label_mode else "Analyzing"
            if self._auto_label_mode:
                self._phase_lbl.setText(f"{verb} — 0 / {total or '?'} completed")
            else:
                self._phase_lbl.setText(f"{verb} — 0 / {total or '?'} frames")
            if total > 0:
                self._set_eta_label(
                    elapsed_s=0,
                    completed=0,
                    total=total,
                    pending="estimating after first frame",
                )
        elif typ == "status":
            self._phase_lbl.setText(str(obj.get("message", "")))
        elif typ == "heartbeat":
            if self._analyze_mode:
                return
            self._mark_job_started()
            elapsed = int(obj.get("elapsed_s", 0))
            msg = str(obj.get("message", "Working…"))
            self._phase_lbl.setText(
                f"{msg}  ({format_duration(elapsed)} elapsed)"
            )
            if self._progress.value() == 0 and self._loss_plot and not self._loss_plot.has_points():
                self._progress.setRange(0, 0)
                self._set_eta_label(
                    elapsed_s=elapsed,
                    completed=0,
                    total=self._epochs,
                    pending="estimating after epoch 1",
                )
        elif typ == "frame":
            self._mark_job_started()
            frame = int(obj.get("frame", 0))
            total = int(obj.get("total_frames") or self._total_frames or 0)
            if total > 0:
                self._total_frames = total
                if self._progress.maximum() != total:
                    self._progress.setRange(0, total)
                    if self._auto_label_mode:
                        self._progress.setFormat("Completed %v / %m")
                    else:
                        self._progress.setFormat("Frame %v / %m")
            self._progress.setValue(min(frame, self._progress.maximum()))
            verb = "Auto-labeling" if self._auto_label_mode else "Analyzing"
            if self._auto_label_mode:
                self._phase_lbl.setText(f"{verb} — {frame} / {total or '?'} completed")
            else:
                self._phase_lbl.setText(f"{verb} — frame {frame} / {total or '?'}")
            now = time.monotonic()
            if self._last_frame_mark > 0 and frame > 0:
                self._frame_times.append(now - self._last_frame_mark)
            self._last_frame_mark = now
            elapsed = now - self._job_started
            if len(self._frame_times) >= 2 and total > frame:
                avg = sum(self._frame_times[-8:]) / len(self._frame_times[-8:])
                frame_eta = max(0, int(avg * max(0, total - frame)))
                wall_eta = estimate_remaining_seconds(elapsed, frame, total)
                if wall_eta is not None:
                    eta_s = max(wall_eta, frame_eta)
                    self._eta_lbl.setText(f"ETA ~ {format_duration(eta_s)}")
                else:
                    self._eta_lbl.setText(f"ETA ~ {format_duration(frame_eta)}")
            else:
                self._set_eta_label(
                    elapsed_s=elapsed,
                    completed=frame,
                    total=total,
                    pending="estimating after a few frames",
                )
        elif typ == "epoch":
            self._mark_job_started()
            if self._progress.maximum() == 0:
                self._progress.setRange(0, max(1, self._epochs))
            now = time.monotonic()
            ep = int(obj.get("epoch", 0))
            total = int(obj.get("total_epochs", self._epochs))
            loss = float(obj.get("loss", 0))
            if self._last_epoch_mark > 0:
                self._epoch_times.append(now - self._last_epoch_mark)
            self._last_epoch_mark = now
            if not obj.get("resumed"):
                self._loss_plot.add_point(
                    ep,
                    loss,
                    heatmap_loss=obj.get("heatmap_loss"),
                )
            self._progress.setValue(ep)
            loss_text = self._loss_text_from_progress(obj)
            if obj.get("resumed"):
                self._phase_lbl.setText(
                    f"Resuming — epoch {ep} / {total}  ({loss_text}, checkpoint on disk)"
                )
            else:
                self._phase_lbl.setText(f"Training — epoch {ep} / {total}  ({loss_text})")
            elapsed = now - self._job_started
            wall_eta = estimate_remaining_seconds(elapsed, ep, total)
            if len(self._epoch_times) >= 2:
                avg = sum(self._epoch_times[-5:]) / len(self._epoch_times[-5:])
                epoch_eta = max(0, int(avg * max(0, total - ep)))
                if wall_eta is not None:
                    eta_s = max(wall_eta, epoch_eta)
                    self._eta_lbl.setText(f"ETA ~ {format_duration(eta_s)}")
                else:
                    self._eta_lbl.setText(f"ETA ~ {format_duration(epoch_eta)}")
            else:
                self._set_eta_label(
                    elapsed_s=elapsed,
                    completed=ep,
                    total=total,
                )
        elif typ == "model_saved":
            self._saved_run = dict(obj.get("run") or {})
            label = self._saved_run.get("label", "Model saved")
            self._eta_lbl.setText(str(label))
        elif typ == "stopped":
            self._stopped = True
            self._phase_lbl.setText(str(obj.get("message", "Stopped.")))
            self._enable_close()

    def _on_stop(self) -> None:
        self._stop_btn.setEnabled(False)
        self._phase_lbl.setText("Stopping after current epoch…")
        if self._worker is not None:
            self._worker.request_stop_after_epoch()

    def _enable_close(self) -> None:
        self._stop_btn.setEnabled(False)
        self._close_btn.setEnabled(True)

    def _on_finished(self, work_dir: str) -> None:
        if self._stopped:
            self._enable_close()
            return
        if self._analyze_mode and self._total_frames > 0:
            self._progress.setValue(self._total_frames)
            verb = "Auto-labeling" if self._auto_label_mode else "Analyzing"
            if self._auto_label_mode:
                self._phase_lbl.setText(f"{verb} complete — {self._total_frames} frames")
            else:
                self._phase_lbl.setText(f"{verb} complete — {self._total_frames} frames")
        else:
            self._progress.setValue(self._progress.maximum())
            self._phase_lbl.setText(f"Complete. Outputs in {work_dir}")
        self._eta_lbl.setText("")
        self._enable_close()
        self.accept()

    def _on_failed(self, msg: str) -> None:
        self._enable_close()
        QMessageBox.critical(self, "Pose Studio", msg)

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            if not self._analyze_mode:
                self._worker.request_stop_after_epoch()
            if not self._worker.wait(3000):
                self._worker.terminate_process()
                self._worker.wait(5000)
        super().closeEvent(event)


PoseTrainDialog = PoseJobDialog
