"""Rows of on-disk artifacts with optional size column and delete."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from app_platform.file_size import (
    ARTIFACT_SIZE_COLUMN_BYTES,
    format_byte_size,
    path_size_bytes,
)


@dataclass(frozen=True)
class ArtifactEntry:
    """One deletable artifact (file or directory)."""

    key: str
    label: str
    path: Path


class _ArtifactRow(QWidget):
    delete_requested = pyqtSignal(str)

    def __init__(self, entry: ArtifactEntry, size_bytes: int, parent=None):
        super().__init__(parent)
        self.setObjectName("ArtifactFileRow")
        self._key = entry.key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        name = QLabel(entry.label)
        name.setObjectName("ArtifactFileName")
        name.setWordWrap(False)
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(name, stretch=1)

        size_lbl = QLabel("")
        size_lbl.setObjectName("ArtifactFileSize")
        size_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        size_lbl.setMinimumWidth(64)
        if size_bytes >= ARTIFACT_SIZE_COLUMN_BYTES:
            size_lbl.setText(format_byte_size(size_bytes))
        lay.addWidget(size_lbl, 0)

        delete = QToolButton()
        delete.setObjectName("ArtifactFileDeleteButton")
        delete.setText("\u00d7")
        delete.setToolTip("Delete from disk")
        delete.setCursor(Qt.PointingHandCursor)
        delete.clicked.connect(lambda: self.delete_requested.emit(self._key))
        lay.addWidget(delete, 0)


class ArtifactFileList(QWidget):
    """Vertical list of project artifacts with size (≥1 MB) and delete."""

    delete_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ArtifactFileList")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._rows: list[_ArtifactRow] = []
        self._entries: dict[str, ArtifactEntry] = {}

    def set_entries(self, entries: list[ArtifactEntry]) -> None:
        for row in self._rows:
            self._layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._entries.clear()

        for entry in entries:
            self._entries[entry.key] = entry
            size = path_size_bytes(entry.path)
            row = _ArtifactRow(entry, size, self)
            row.delete_requested.connect(self.delete_requested.emit)
            self._layout.addWidget(row)
            self._rows.append(row)

        self.setVisible(bool(entries))

    def entry_for_key(self, key: str) -> ArtifactEntry | None:
        return self._entries.get(key)
