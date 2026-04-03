"""
Modal session registry: list, create, upload, open, remove.
Mirrors LandingScene discovery under app_platform.paths.sessions_dir().
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_platform.paths import sessions_dir
from session.session import Session, load_session_from_json
from styles.themes import THEMES, apply_theme

from ui.components.chrome_separators import horizontal_separator
from ui.components.dialog_title_bar import DialogTitleBar

_ROLE_PATH = Qt.UserRole + 1
_ROLE_VALID = Qt.UserRole + 2


class _SessionTableWidget(QTableWidget):
    """Tracks hovered row so the delegate can paint a full-row hover (not one cell)."""

    def __init__(self, rows=0, columns=0, parent=None):
        super().__init__(rows, columns, parent)
        self._hover_row = -1
        self.viewport().installEventFilter(self)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            if event.type() == QEvent.HoverMove:
                r = self.rowAt(event.pos().y())
                if r != self._hover_row:
                    self._hover_row = r
                    self.viewport().update()
            elif event.type() == QEvent.Leave:
                if self._hover_row != -1:
                    self._hover_row = -1
                    self.viewport().update()
        return super().eventFilter(obj, event)


class _SessionTableDelegate(QStyledItemDelegate):
    """Full-row selection/hover; path column uses left elide (explicit paint for all styles)."""

    def paint(self, painter, option, index):
        widget = option.widget
        if widget is None:
            return super().paint(painter, option, index)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        sm = widget.selectionModel()
        selected_rows = {idx.row() for idx in sm.selectedRows()} if sm else set()

        row = index.row()
        hover_row = getattr(widget, "_hover_row", -1)
        rect = opt.rect
        pal = opt.palette

        selected = row in selected_rows
        hovered = hover_row == row and not selected

        painter.save()
        painter.setClipRect(rect)

        if selected:
            bg_hex = getattr(widget, "_selection_row_bg", None)
            fg_hex = getattr(widget, "_selection_row_fg", None)
            if bg_hex and fg_hex:
                painter.fillRect(rect, QColor(bg_hex))
                fg = QColor(fg_hex)
            else:
                painter.fillRect(rect, pal.brush(QPalette.Highlight))
                fg = pal.color(QPalette.HighlightedText)
        elif hovered:
            painter.fillRect(rect, pal.brush(QPalette.Mid))
            fg = pal.color(QPalette.Text)
        else:
            painter.fillRect(rect, pal.brush(QPalette.Base))
            fg = pal.color(QPalette.Text)

        it0 = widget.item(row, 0)
        if it0 is not None and it0.data(_ROLE_VALID) is False:
            fg = Qt.gray

        raw = index.data(Qt.DisplayRole)
        text = "" if raw is None else str(raw)
        inner = rect.adjusted(8, 0, -8, 0)
        w = max(0, inner.width())
        if index.column() == 1:
            text = opt.fontMetrics.elidedText(text, Qt.ElideLeft, w)
        else:
            text = opt.fontMetrics.elidedText(text, Qt.ElideRight, w)

        painter.setFont(opt.font)
        painter.setPen(fg)
        painter.drawText(inner, Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.restore()


def _safe_session_stem(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    s = s.strip(" .")
    return s


def unique_session_stem(base: str) -> str:
    """If base.json exists, return base_2, base_3, … (spec: append a number)."""
    root = sessions_dir()
    root.mkdir(parents=True, exist_ok=True)
    b = _safe_session_stem(base) or "session"
    candidate = b
    n = 2
    while (root / f"{candidate}.json").exists():
        candidate = f"{b}_{n}"
        n += 1
    return candidate


@dataclass
class _Row:
    path: Path
    display_name: str
    last_mtime: float
    valid: bool


def _scan_sessions() -> list[_Row]:
    root = sessions_dir()
    if not root.is_dir():
        return []
    rows: list[_Row] = []
    for p in sorted(root.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        valid = True
        display = p.stem
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data.get("name"):
                display = str(data["name"])
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            valid = False
        rows.append(_Row(path=p, display_name=display, last_mtime=mtime, valid=valid))
    return rows


class SessionSelectDialog(QDialog):
    """Application-modal dialog; on accept, ``selected_path`` is the chosen session JSON path."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SessionSelectDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumSize(560, 420)
        self.resize(720, 480)

        self.selected_path: str | None = None

        theme_name = "dark"
        p = parent
        while p is not None:
            if hasattr(p, "current_theme"):
                theme_name = getattr(p, "current_theme", "dark") or "dark"
                break
            p = p.parentWidget()
        theme = THEMES[theme_name]
        apply_theme(self, theme)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._title_bar = DialogTitleBar(self, "Session Select", self)
        outer.addWidget(self._title_bar)
        outer.addWidget(horizontal_separator())

        body = QWidget()
        body.setObjectName("SessionSelectBody")
        body.setAttribute(Qt.WA_StyledBackground, True)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(14, 12, 14, 12)
        body_layout.setSpacing(10)

        actions = QHBoxLayout()
        self._btn_create = QPushButton("+ Create New")
        self._btn_create.setCursor(Qt.PointingHandCursor)
        self._btn_create.clicked.connect(self._on_create_new)

        self._btn_upload = QPushButton("  Upload New")
        if self.style():
            self._btn_upload.setIcon(self.style().standardIcon(QStyle.SP_ArrowUp))
        self._btn_upload.setCursor(Qt.PointingHandCursor)
        self._btn_upload.clicked.connect(self._on_upload_new)
        actions.addWidget(self._btn_create)
        actions.addWidget(self._btn_upload)
        actions.addStretch(1)
        body_layout.addLayout(actions)

        self._table = _SessionTableWidget(0, 3)
        self._table._selection_row_bg = theme["chrome_button"]
        self._table._selection_row_fg = theme["text"]
        self._table.setObjectName("SessionSelectTable")
        self._table.setAttribute(Qt.WA_StyledBackground, True)
        self._table.setHorizontalHeaderLabels(["Session name", "File location", "Last opened"])
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setMinimumSectionSize(80)
        hh.setHighlightSections(False)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(False)
        self._table.setTextElideMode(Qt.ElideRight)
        self._table.setItemDelegate(_SessionTableDelegate(self._table))
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        body_layout.addWidget(self._table, stretch=1)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        body_layout.addLayout(bottom)

        outer.addWidget(body, stretch=1)

        self._populate_table()

    def _populate_table(self) -> None:
        rows = _scan_sessions()
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            p = row.path
            path_str = str(p)
            name_item = QTableWidgetItem(row.display_name)
            name_item.setData(_ROLE_PATH, path_str)
            name_item.setData(_ROLE_VALID, row.valid)
            if not row.valid:
                name_item.setForeground(Qt.gray)
            loc_item = QTableWidgetItem(path_str)
            loc_item.setToolTip(path_str)
            loc_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            if not row.valid:
                loc_item.setForeground(Qt.gray)
            when = datetime.fromtimestamp(row.last_mtime).strftime("%Y-%m-%d %H:%M")
            when_item = QTableWidgetItem(when)
            when_item.setFlags(when_item.flags() & ~Qt.ItemIsEditable)
            if not row.valid:
                when_item.setForeground(Qt.gray)
            self._table.setItem(i, 0, name_item)
            self._table.setItem(i, 1, loc_item)
            self._table.setItem(i, 2, when_item)
        self._table.resizeColumnToContents(0)
        self._table.resizeColumnToContents(2)

    def _current_json_path(self) -> Path | None:
        r = self._table.currentRow()
        if r < 0:
            return None
        it = self._table.item(r, 0)
        if not it:
            return None
        raw = it.data(_ROLE_PATH)
        if not raw:
            return None
        return Path(str(raw))

    def _validate_and_accept(self, path: Path) -> None:
        if not path.exists():
            QMessageBox.warning(self, "Session missing", f"The session file is no longer present:\n{path}")
            self._populate_table()
            return
        try:
            load_session_from_json(str(path))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid session", str(e))
            return
        self.selected_path = str(path.resolve())
        self.accept()

    def _open_current(self) -> None:
        path = self._current_json_path()
        if path is None:
            QMessageBox.information(self, "Session Select", "Select a session row first.")
            return
        r = self._table.currentRow()
        it = self._table.item(r, 0)
        if it and not it.data(_ROLE_VALID):
            QMessageBox.warning(
                self,
                "Invalid session file",
                "This JSON could not be read. Fix or remove the file and try again.",
            )
            return
        self._validate_and_accept(path)

    def _on_double_click(self, _index) -> None:
        self._open_current()

    def _on_context_menu(self, pos) -> None:
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        self._table.selectRow(idx.row())
        menu = QMenu(self)
        open_act = menu.addAction("Open")
        remove_act = menu.addAction("Remove from registry")
        chosen = menu.exec_(self._table.viewport().mapToGlobal(pos))
        if chosen == open_act:
            self._open_current()
        elif chosen == remove_act:
            self._remove_current()

    def _remove_current(self) -> None:
        path = self._current_json_path()
        if path is None:
            return
        name = path.stem
        ans = QMessageBox.question(
            self,
            "Remove session",
            f"Remove “{name}” from the registry?\n\nThis deletes the session file:\n{path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            QMessageBox.warning(self, "Remove failed", str(e))
            return
        self._populate_table()

    def _on_create_new(self) -> None:
        text, ok = QInputDialog.getText(self, "Create New Session", "Session name:")
        if not ok:
            return
        desired = _safe_session_stem(text)
        if not desired:
            QMessageBox.warning(self, "Invalid name", "Please enter a session name.")
            return
        stem = unique_session_stem(text)
        if stem != desired:
            QMessageBox.information(
                self,
                "Session name",
                f"A session with that name already exists.\nCreated: {stem}",
            )
        session = Session(stem)
        session.save()
        self._populate_table()
        self._select_path(sessions_dir() / f"{stem}.json")

    def _select_path(self, path: Path) -> None:
        try:
            target = path.resolve()
        except OSError:
            target = path
        for r in range(self._table.rowCount()):
            it = self._table.item(r, 0)
            if not it:
                continue
            raw = it.data(_ROLE_PATH)
            if not raw:
                continue
            try:
                if Path(str(raw)).resolve() == target:
                    self._table.selectRow(r)
                    return
            except OSError:
                continue

    def _on_upload_new(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Upload session JSON",
            "",
            "Session JSON (*.json);;All files (*.*)",
        )
        if not path_str:
            return
        src = Path(path_str)
        if not src.is_file():
            return
        try:
            with open(src, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
            QMessageBox.warning(self, "Invalid JSON", f"Could not read session file:\n{e}")
            return
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid JSON", "File must contain a JSON object.")
            return

        root = sessions_dir()
        root.mkdir(parents=True, exist_ok=True)
        stem = unique_session_stem(src.stem)
        dst = root / f"{stem}.json"
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            QMessageBox.warning(self, "Upload failed", str(e))
            return

        data["name"] = stem
        try:
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except OSError as e:
            QMessageBox.warning(self, "Upload failed", str(e))
            dst.unlink(missing_ok=True)
            return

        try:
            load_session_from_json(str(dst))
        except ValueError as e:
            QMessageBox.warning(self, "Invalid session", str(e))
            dst.unlink(missing_ok=True)
            return

        self._populate_table()
        self._select_path(dst)
