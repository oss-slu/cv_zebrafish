"""Background loading of fish files for the Compare Fish panel."""

from __future__ import annotations

from typing import Any, Dict, Sequence

from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from src.core.comparison.fish_data import load_fish_batch


class FishLoadWorker(QObject):
    """Runs :func:`load_fish_batch` on a worker thread."""

    progress = pyqtSignal(int, int, str)  # (file number, total files, file name)
    finished = pyqtSignal(object, object)  # (loaded fish, [(path, message), ...])
    failed = pyqtSignal(str)

    def __init__(
        self,
        csv_paths: Sequence[str],
        config: Dict[str, Any],
        existing_labels: Sequence[str],
        first_number: int,
    ):
        super().__init__()
        self._csv_paths = list(csv_paths)
        self._config = config
        self._existing_labels = list(existing_labels)
        self._first_number = first_number

    @pyqtSlot()
    def run(self) -> None:
        try:
            loaded, failures = load_fish_batch(
                self._csv_paths,
                self._config,
                existing_labels=self._existing_labels,
                first_number=self._first_number,
                on_progress=self.progress.emit,
            )
            self.finished.emit(loaded, failures)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            thread = self.thread()
            if thread is not None:
                thread.quit()