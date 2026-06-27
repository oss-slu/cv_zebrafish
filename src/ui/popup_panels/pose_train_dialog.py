"""Pose Studio training progress dialog (Step 4)."""

from __future__ import annotations

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

from ui.components.chrome.dialog_title_bar import DialogTitleBar
from ui.components.pose.training_loss_plot import TrainingLossPlot
from ui.platform.frameless_resize import FramelessResizeMixin
from ui.workers.pose_subprocess_worker import PoseSubprocessWorker


class PoseTrainDialog(FramelessResizeMixin, QDialog):
    """Train + predict with live loss curve and stop-after-epoch."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        python_exe: str,
        job_path: Path,
        epochs: int,
        use_gpu: bool,
    ):
        super().__init__(parent)
        self.setObjectName("PoseTrainDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self._job_path = Path(job_path)
        self._work_dir = self._job_path.parent
        self._epochs = epochs
        self._epoch_times: list[float] = []
        self._last_epoch_mark = 0.0
        self._worker: PoseSubprocessWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(DialogTitleBar(self, "Train Model", self))
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
        self._progress.setRange(0, max(1, epochs))
        bl.addWidget(self._progress)

        self._loss_plot = TrainingLossPlot()
        bl.addWidget(self._loss_plot, stretch=1)

        btn_row = QHBoxLayout()
        self._stop_btn = QPushButton("Stop after current epoch")
        self._stop_btn.clicked.connect(self._on_stop)
        self._close_btn = QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._close_btn)
        bl.addLayout(btn_row)

        outer.addWidget(body)
        self.resize(520, 420)

        self._worker = PoseSubprocessWorker(
            python_exe=python_exe,
            job_path=self._job_path,
            step="pipeline",
            epochs=epochs,
            use_gpu=use_gpu,
            work_dir=self._work_dir,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_ok.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_progress(self, obj: dict) -> None:
        typ = obj.get("type")
        if typ == "phase":
            phase = obj.get("phase", "")
            self._phase_lbl.setText(f"Phase: {phase}")
        elif typ == "status":
            self._phase_lbl.setText(str(obj.get("message", "")))
        elif typ == "epoch":
            import time

            now = time.monotonic()
            ep = int(obj.get("epoch", 0))
            total = int(obj.get("total_epochs", self._epochs))
            loss = float(obj.get("loss", 0))
            if self._last_epoch_mark > 0:
                self._epoch_times.append(now - self._last_epoch_mark)
            self._last_epoch_mark = now
            self._loss_plot.add_point(ep, loss)
            self._progress.setValue(ep)
            self._phase_lbl.setText(f"Training — epoch {ep} / {total}  (loss {loss:.4f})")
            if self._epoch_times:
                avg = sum(self._epoch_times) / len(self._epoch_times)
                remaining = max(0, total - ep)
                eta_s = int(avg * remaining)
                mins, secs = divmod(eta_s, 60)
                self._eta_lbl.setText(f"ETA ~ {mins}m {secs}s")
        elif typ == "stopped":
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
        self._progress.setValue(self._progress.maximum())
        self._phase_lbl.setText(f"Complete. Outputs in {work_dir}")
        self._eta_lbl.setText("")
        self._enable_close()

    def _on_failed(self, msg: str) -> None:
        self._enable_close()
        QMessageBox.critical(self, "Train Model", msg)

    def closeEvent(self, event) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop_after_epoch()
            self._worker.wait(3000)
        super().closeEvent(event)
