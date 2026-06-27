"""Background worker: build DLC training bundle without blocking the UI."""

from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.training.dlc_bundle import ProjectLabelStats, prepare_training_bundle


class PrepareTrainingBundleWorker(QThread):
    finished_ok = pyqtSignal(str, object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        session_name: str,
        project_id: str,
        video_ids: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self._session_name = session_name
        self._project_id = project_id
        self._video_ids = list(video_ids)

    def run(self) -> None:
        try:
            job_path, stats = prepare_training_bundle(
                self._session_name,
                self._project_id,
                self._video_ids,
            )
            self.finished_ok.emit(str(job_path), stats)
        except Exception as exc:
            self.failed.emit(str(exc))
