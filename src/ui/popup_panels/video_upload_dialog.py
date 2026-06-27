"""Copy vs reference choice for video upload."""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.pose.video.video_registry import LARGE_FILE_WARNING_BYTES
from ui.components.chrome.dialog_title_bar import DialogTitleBar
from ui.platform.frameless_resize import FramelessResizeMixin


class VideoUploadDialog(FramelessResizeMixin, QDialog):
    """Ask copy vs reference; optional remember; large-file warning."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        file_count: int,
        large_file: bool,
        default_policy: str = "ask",
    ):
        super().__init__(parent)
        self.setObjectName("VideoUploadDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setModal(True)

        self._policy: str | None = None
        self._remember = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(DialogTitleBar(self, "Upload Video", self))
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 16)

        bl.addWidget(
            QLabel(f"Register {file_count} video file(s) in this session project.")
        )
        if large_file:
            warn = QLabel(
                f"One or more files are ≥ {LARGE_FILE_WARNING_BYTES // (1024 ** 3)} GB. "
                "Copying uses more disk space but keeps the session portable."
            )
            warn.setWordWrap(True)
            warn.setObjectName("SettingsHintLabel")
            bl.addWidget(warn)

        row = QHBoxLayout()
        copy_btn = QPushButton("Copy into session")
        ref_btn = QPushButton("Reference original")
        copy_btn.clicked.connect(lambda: self._accept("copy"))
        ref_btn.clicked.connect(lambda: self._accept("reference"))
        row.addWidget(copy_btn)
        row.addWidget(ref_btn)
        bl.addLayout(row)

        self._remember_cb = QCheckBox("Remember my choice")
        bl.addWidget(self._remember_cb)

        if default_policy == "always_copy":
            copy_btn.setDefault(True)
        elif default_policy == "always_reference":
            ref_btn.setDefault(True)

        outer.addWidget(body)

    def _accept(self, policy: str) -> None:
        self._policy = policy
        self._remember = self._remember_cb.isChecked()
        self.accept()

    @property
    def chosen_policy(self) -> str:
        return self._policy or "copy"

    @property
    def remember_choice(self) -> bool:
        return self._remember
