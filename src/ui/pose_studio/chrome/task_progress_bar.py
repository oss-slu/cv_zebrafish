"""In-panel heavy-task progress: N/N, ETA avg, ETA current."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget


class TaskProgressBar(QWidget):
    """
    Progress for long Pose Studio jobs.

    - ``<activity> - N/M <unit>`` (e.g. Training Progress - 0/50 Epochs)
    - Time to completion (Avg)
    - Time to completion (Current) — or "Not enough data"
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PoseTaskProgressBar")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        top = QHBoxLayout()
        self._progress_lbl = QLabel("Progress 0/0")
        self._progress_lbl.setObjectName("PoseTaskProgressLabel")
        top.addWidget(self._progress_lbl)
        top.addStretch(1)
        self._avg_lbl = QLabel("ETA (Avg): —")
        self._avg_lbl.setObjectName("PoseTaskEtaLabel")
        self._cur_lbl = QLabel("ETA (Current): Not enough data")
        self._cur_lbl.setObjectName("PoseTaskEtaLabel")
        top.addWidget(self._avg_lbl)
        top.addWidget(self._cur_lbl)
        root.addLayout(top)

        self._bar = QProgressBar()
        self._bar.setObjectName("PoseTaskProgressMeter")
        self._bar.setTextVisible(False)
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        root.addWidget(self._bar)

        self._done = 0
        self._total = 0
        self._activity = "Progress"
        self._unit = ""

    def reset(self) -> None:
        self.set_progress(0, 0)
        self.set_eta_avg(None)
        self.set_eta_current(None)

    def set_activity(self, activity: str, *, unit: str = "") -> None:
        """Name of the active job shown in the progress label."""
        self._activity = (activity or "Progress").strip()
        self._unit = (unit or "").strip()
        self._refresh_label()

    def set_progress(
        self,
        done: int,
        total: int,
        *,
        activity: str | None = None,
        unit: str | None = None,
    ) -> None:
        self._done = max(0, int(done))
        self._total = max(0, int(total))
        if activity is not None:
            self._activity = activity.strip() or "Progress"
        if unit is not None:
            self._unit = unit.strip()
        self._refresh_label()
        if self._total <= 0:
            self._bar.setRange(0, 0)  # indeterminate
        else:
            self._bar.setRange(0, self._total)
            self._bar.setValue(min(self._done, self._total))

    def _refresh_label(self) -> None:
        activity = self._activity or "Progress"
        if self._total <= 0 and self._done <= 0:
            self._progress_lbl.setText(activity)
            return
        text = f"{activity} - {self._done}/{self._total}"
        if self._unit:
            text += f" {self._unit}"
        self._progress_lbl.setText(text)

    def set_eta_avg(self, text: str | None) -> None:
        self._avg_lbl.setText(f"ETA (Avg): {text}" if text else "ETA (Avg): —")

    def set_eta_current(self, text: str | None) -> None:
        if text:
            self._cur_lbl.setText(f"ETA (Current): {text}")
        else:
            self._cur_lbl.setText("ETA (Current): Not enough data")

    def set_busy_message(self, message: str) -> None:
        """Indeterminate mode with a status message in the progress label."""
        self._bar.setRange(0, 0)
        self._progress_lbl.setText(message)
