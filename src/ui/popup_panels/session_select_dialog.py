"""
Modal session picker: list, create, upload, open, remove.

Rows come from a machine-local registry (``data/local/session_registry.json``):
paths to each session JSON, display names, and last-opened times. Canonical
on-disk layout is ``data/sessions/<name>/session.json`` (graphs live beside it);
legacy flat ``data/sessions/<name>.json`` is still supported. Missing or invalid
paths use muted text. Payload always loads from the JSON file.
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
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
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

from app_platform.paths import (
    SESSION_JSON_FILENAME,
    display_stem_for_session_json,
    is_session_bundle_json,
    session_json_path,
    sessions_dir,
)
from app_platform.session_registry import remove_entry, sync_registry_with_disk, touch_last_opened
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
            fg_hex = getattr(widget, "_invalid_row_fg", None)
            fg = QColor(fg_hex) if fg_hex else QColor("#888888")

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


def _session_name_taken(root: Path, stem: str) -> bool:
    """Bundle ``<stem>/session.json`` or legacy flat ``<stem>.json``."""
    return session_json_path(stem).is_file() or (root / f"{stem}.json").is_file()


def unique_session_stem(base: str) -> str:
    """If that session id is already used on disk, return base_2, base_3, …"""
    root = sessions_dir()
    root.mkdir(parents=True, exist_ok=True)
    b = _safe_session_stem(base) or "session"
    candidate = b
    n = 2
    while _session_name_taken(root, candidate):
        candidate = f"{b}_{n}"
        n += 1
    return candidate


@dataclass
class _Row:
    path: Path
    display_name: str
    last_opened: float
    valid: bool


def _rows_from_registry() -> list[_Row]:
    entries = sync_registry_with_disk()
    rows: list[_Row] = []
    for e in entries:
        p = Path(str(e.get("path") or ""))
        try:
            last_opened = float(e.get("last_opened") or 0)
        except (TypeError, ValueError):
            last_opened = 0.0
        reg_name = str(e.get("name") or "").strip()
        display = reg_name or display_stem_for_session_json(p)
        valid = False
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("name"):
                    display = str(data["name"])
                if isinstance(data, dict):
                    try:
                        load_session_from_json(str(p))
                        valid = True
                    except ValueError:
                        valid = False
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                valid = False
        rows.append(_Row(path=p, display_name=display, last_opened=last_opened, valid=valid))
    return rows


class SessionSelectDialog(QDialog):
    """Window-modal to parent; on accept, ``selected_path`` is the chosen session JSON path."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SessionSelectDialog")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setModal(True)
        self.setWindowModality(Qt.WindowModal)
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
        self._muted_fg = QColor(theme["text_muted"])

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
        self._table._invalid_row_fg = theme["text_muted"]
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

        self._session_status = QLabel("")
        self._session_status.setObjectName("SessionSelectStatus")
        self._session_status.setWordWrap(True)
        self._session_status.hide()
        body_layout.addWidget(self._session_status)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        body_layout.addLayout(bottom)

        outer.addWidget(body, stretch=1)

        self._populate_table()

    def _show_dialog_status(self, text: str) -> None:
        """Inline feedback on this dialog (create / upload / remove / repair — not global toast)."""
        t = (text or "").strip()
        if not t:
            self._session_status.clear()
            self._session_status.hide()
            return
        self._session_status.setText(t)
        self._session_status.show()

    def _shell_theme_name(self) -> str:
        p = self.parentWidget()
        while p is not None:
            t = getattr(p, "current_theme", None)
            if t in THEMES:
                return str(t)
            p = p.parentWidget()
        return "dark"

    def _prompt_new_session_name(self) -> str | None:
        """Line edit with placeholder ``session``; OK with empty field uses ``session``."""
        theme_name = self._shell_theme_name()
        dlg = QDialog(self)
        dlg.setWindowTitle("Create New Session")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Session name:"))
        edit = QLineEdit()
        edit.setPlaceholderText("session")
        layout.addWidget(edit)
        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(dlg.accept)
        bbox.rejected.connect(dlg.reject)
        layout.addWidget(bbox)
        apply_theme(dlg, THEMES.get(theme_name, THEMES["dark"]))
        edit.setFocus()
        if dlg.exec_() != QDialog.Accepted:
            return None
        raw = edit.text().strip()
        return raw or "session"

    def _populate_table(self) -> None:
        rows = _rows_from_registry()
        self._table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            p = row.path
            path_str = str(p)
            name_item = QTableWidgetItem(row.display_name)
            name_item.setData(_ROLE_PATH, path_str)
            name_item.setData(_ROLE_VALID, row.valid)
            if not row.valid:
                name_item.setForeground(self._muted_fg)
            loc_item = QTableWidgetItem(path_str)
            loc_item.setToolTip(path_str)
            loc_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            if not row.valid:
                loc_item.setForeground(self._muted_fg)
            when = datetime.fromtimestamp(row.last_opened).strftime("%Y-%m-%d %H:%M")
            when_item = QTableWidgetItem(when)
            when_item.setFlags(when_item.flags() & ~Qt.ItemIsEditable)
            if not row.valid:
                when_item.setForeground(self._muted_fg)
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
            self._show_dialog_status(f"Session missing — file not found:\n{path}")
            self._populate_table()
            return
        try:
            load_session_from_json(str(path))
        except ValueError as e:
            self._show_dialog_status(f"Invalid session: {e}")
            return
        self.selected_path = str(path.resolve())
        self.accept()

    def _open_current(self) -> None:
        path = self._current_json_path()
        if path is None:
            self._show_dialog_status("Select a session row first (or double‑click a row to open).")
            return
        r = self._table.currentRow()
        it = self._table.item(r, 0)
        if it and not it.data(_ROLE_VALID):
            self._show_dialog_status(
                "This row is invalid — use Find location… or remove it, then refresh the list."
            )
            return
        self._validate_and_accept(path)

    def _on_double_click(self, _index) -> None:
        self._open_current()

    def _on_context_menu(self, pos) -> None:
        idx = self._table.indexAt(pos)
        if not idx.isValid():
            return
        r = idx.row()
        self._table.selectRow(r)
        it0 = self._table.item(r, 0)
        if not it0:
            return
        menu = QMenu(self)
        open_act = menu.addAction("Open")
        find_act = None
        if not it0.data(_ROLE_VALID):
            find_act = menu.addAction("Find location…")
        remove_act = menu.addAction("Remove session…")
        chosen = menu.exec_(self._table.viewport().mapToGlobal(pos))
        if chosen == open_act:
            self._open_current()
        elif find_act is not None and chosen == find_act:
            self._find_location_for_current()
        elif chosen == remove_act:
            self._remove_current()

    def _find_location_for_current(self) -> None:
        """Folder picker: copy a matching valid session JSON over this greyed registry file (spec)."""
        r = self._table.currentRow()
        if r < 0:
            return
        it0 = self._table.item(r, 0)
        if not it0 or it0.data(_ROLE_VALID):
            return
        raw_path = it0.data(_ROLE_PATH)
        if not raw_path:
            return
        dst = Path(str(raw_path))
        display_name = (it0.text() or "").strip()
        dst_id = display_stem_for_session_json(dst)
        start_dir = str(dst.parent if dst.parent.is_dir() else sessions_dir())
        folder = QFileDialog.getExistingDirectory(
            self,
            "Find folder containing a valid session JSON for this entry",
            start_dir,
        )
        if not folder:
            return
        root = Path(folder)
        matches: list[Path] = []

        def _consider(cand: Path) -> None:
            if not cand.is_file():
                return
            try:
                load_session_from_json(str(cand))
            except ValueError:
                return
            except Exception:
                return
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                return
            if not isinstance(data, dict):
                return
            json_name = str(data.get("name") or "").strip()
            bundle_id = (
                cand.parent.name
                if cand.name.lower() == SESSION_JSON_FILENAME.lower()
                else cand.stem
            )
            if (
                json_name == display_name
                or cand.stem == dst_id
                or bundle_id == dst_id
                or json_name == dst_id
            ):
                matches.append(cand)

        primary = root / SESSION_JSON_FILENAME
        if primary.is_file():
            _consider(primary)
        for cand in sorted(root.glob("*.json")):
            _consider(cand)
        # Preserve order, drop duplicates
        matches = list(dict.fromkeys(matches))
        if not matches:
            self._show_dialog_status(
                "No matching session JSON in that folder.\n"
                f"Expected name “{display_name}”, folder id “{dst_id}”, or “{SESSION_JSON_FILENAME}”."
            )
            return
        if len(matches) > 1:
            labels = [str(m) for m in matches]
            choice, ok = QInputDialog.getItem(
                self,
                "Choose session file",
                "Several JSON files matched. Pick one:",
                labels,
                0,
                False,
            )
            if not ok:
                return
            try:
                src = matches[labels.index(choice)]
            except ValueError:
                return
        else:
            src = matches[0]

        ans = QMessageBox.question(
            self,
            "Replace session file",
            f"Copy this file into the registry path?\n\n"
            f"To:\n{dst}\n\nFrom:\n{src}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        except OSError as e:
            self._show_dialog_status(f"Copy failed — {e}")
            return
        touch_last_opened(str(dst))
        self._populate_table()
        self._select_path(dst)
        self._show_dialog_status(
            "Session file updated — the list was refreshed. "
            "The row should show as valid if the JSON loads correctly."
        )

    def _remove_current(self) -> None:
        path = self._current_json_path()
        if path is None:
            return
        name = display_stem_for_session_json(path)
        ans = QMessageBox.question(
            self,
            "Remove session",
            f"Remove “{name}” from the local session list and delete its session data on disk?\n\n{path}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        try:
            if is_session_bundle_json(path):
                shutil.rmtree(path.parent, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
        except OSError as e:
            self._show_dialog_status(f"Remove failed — {e}")
            return
        remove_entry(str(path))
        self._populate_table()
        self._show_dialog_status(f"Removed “{name}” from the session list.")

    def _on_create_new(self) -> None:
        name = self._prompt_new_session_name()
        if name is None:
            return
        desired = _safe_session_stem(name) or "session"
        stem = unique_session_stem(name)
        suffix = ""
        if stem != desired:
            suffix = f"\n\nName was adjusted to “{stem}” because that name was already taken."
        json_path = session_json_path(stem)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        session = Session(stem)
        session.json_path = str(json_path.resolve())
        session.save()
        touch_last_opened(str(json_path.resolve()), stem)
        self._populate_table()
        self._select_path(json_path)
        self._show_dialog_status(f"Session “{stem}” created and added to the list.{suffix}")

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
            self._show_dialog_status(f"Invalid JSON — could not read file:\n{e}")
            return
        if not isinstance(data, dict):
            self._show_dialog_status("Invalid JSON — file must contain a JSON object.")
            return

        root = sessions_dir()
        root.mkdir(parents=True, exist_ok=True)
        stem = unique_session_stem(src.stem)
        bundle = root / stem
        bundle.mkdir(parents=True, exist_ok=True)
        dst = bundle / SESSION_JSON_FILENAME
        try:
            shutil.copy2(src, dst)
        except OSError as e:
            self._show_dialog_status(f"Upload failed — {e}")
            return

        data["name"] = stem
        try:
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except OSError as e:
            self._show_dialog_status(f"Upload failed — {e}")
            dst.unlink(missing_ok=True)
            return

        try:
            load_session_from_json(str(dst))
        except ValueError as e:
            self._show_dialog_status(f"Invalid session — {e}")
            dst.unlink(missing_ok=True)
            return

        touch_last_opened(str(dst), stem)
        self._populate_table()
        self._select_path(dst)
        self._show_dialog_status(f"Uploaded! Session “{stem}” is in the list.")
