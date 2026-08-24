"""Background worker: register videos (copy/reference) and probe metadata."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QThread, pyqtSignal

from core.pose.video.video_registry import register_video


class VideoRegisterWorker(QThread):
    """Register one or more videos off the UI thread."""

    progress = pyqtSignal(str, int, int)  # message, current (-1 unknown), total (-1 unknown)
    video_registered = pyqtSignal(str, str, dict)  # video_id, display_name, meta dict
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        session_name: str,
        project_id: str,
        items: list[tuple[Path, str]],
        existing_ids: set[str],
        preferred_ids: dict[str, str] | None = None,
        parent=None,
    ):
        """
        items: (path, policy)
        preferred_ids: map path.resolve() str → video_id for missing-stub re-link
        """
        super().__init__(parent)
        self._session_name = session_name
        self._project_id = project_id
        self._items = items
        self._existing = set(existing_ids)
        self._preferred = preferred_ids or {}

    def run(self) -> None:
        try:
            for path, policy in self._items:
                self.progress.emit(f"Registering {path.name}…", -1, -1)
                key = str(path.resolve())
                preferred = self._preferred.get(key)
                # Allow reusing preferred id even if already in existing set.
                existing = set(self._existing)
                if preferred:
                    existing.discard(preferred)
                vid, meta = register_video(
                    self._session_name,
                    self._project_id,
                    path,
                    policy=policy,
                    existing_video_ids=existing,
                    preferred_video_id=preferred,
                    progress=lambda msg, cur, tot: self.progress.emit(msg, cur, tot),
                )
                self._existing.add(vid)
                self.video_registered.emit(vid, path.name, meta.to_dict())
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
