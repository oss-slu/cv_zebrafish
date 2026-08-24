"""Model / Epoch tree picker for Pose Studio train UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PyQt5.QtCore import Qt, QSize, pyqtSignal
from PyQt5.QtGui import QFontMetrics
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.pose.training.model_registry import AnalyzeCheckpoint, ModelRun

MAX_VISIBLE_DEPTH = 3


@dataclass(frozen=True)
class ModelEpochSelection:
    """Current tree selection for train / Auto Label handoff."""

    run_id: str | None = None
    checkpoint_key: str | None = None
    checkpoint_epoch: int | None = None
    is_best: bool = False
    label: str = ""
    work_dir: str | None = None


@dataclass
class ModelTreeNode:
    """Logical node for nested model / epoch / branch rendering."""

    node_id: str
    label: str
    kind: str
    run_id: str | None = None
    checkpoint: AnalyzeCheckpoint | None = None
    work_dir: str | None = None
    children: list[ModelTreeNode] = field(default_factory=list)
    hidden_ancestor_count: int = 0


_ROLE_KIND = Qt.UserRole
_ROLE_RUN_ID = Qt.UserRole + 1
_ROLE_CKPT_KEY = Qt.UserRole + 2
_ROLE_EPOCH = Qt.UserRole + 3
_ROLE_IS_BEST = Qt.UserRole + 4
_ROLE_WORK_DIR = Qt.UserRole + 5
_ROLE_NODE_ID = Qt.UserRole + 6

_KIND_RUN = "run"
_KIND_CKPT = "ckpt"
_KIND_CURRENT = "current"
_KIND_COLLAPSED = "collapsed"


class _EpochRowWidget(QWidget):
    """Checkpoint row with hover → (branch) and X (delete run) actions."""

    branch_clicked = pyqtSignal()
    delete_clicked = pyqtSignal()

    def __init__(
        self,
        text: str,
        *,
        show_delete: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ModelEpochRow")
        self._full_text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)
        self._label = QLabel(text)
        self._label.setObjectName("ModelEpochRowLabel")
        self._label.setToolTip(text)
        layout.addWidget(self._label, stretch=1)
        self._branch_btn = QPushButton("→")
        self._branch_btn.setObjectName("ModelEpochBranchBtn")
        self._branch_btn.setFixedWidth(22)
        self._branch_btn.setToolTip("Train a new branch from this epoch")
        self._branch_btn.clicked.connect(self.branch_clicked.emit)
        self._delete_btn = QPushButton("X")
        self._delete_btn.setObjectName("ModelEpochDeleteBtn")
        self._delete_btn.setFixedWidth(22)
        self._delete_btn.setToolTip("Delete this saved model run")
        self._delete_btn.clicked.connect(self.delete_clicked.emit)
        if show_delete:
            layout.addWidget(self._delete_btn)
        self._branch_btn.hide()
        if show_delete:
            self._delete_btn.hide()

    def set_elided_text(self, width: int) -> None:
        """Elide the row label to ``width``; full text stays on the tooltip."""
        fm = QFontMetrics(self._label.font())
        reserve = 28
        avail = max(40, width - reserve)
        self._label.setText(fm.elidedText(self._full_text, Qt.ElideRight, avail))

    def enterEvent(self, event) -> None:  # noqa: N802
        if self._delete_btn.parentWidget() is self:
            self._delete_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._delete_btn.parentWidget() is self:
            self._delete_btn.hide()
        super().leaveEvent(event)


class _CompactTreeWidget(QTreeWidget):
    """Tree that reports a height fitting visible rows (no empty stretch area)."""

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), self._content_height())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(hint.width(), min(self._content_height(), 24))

    def _content_height(self) -> int:
        row_h = self.sizeHintForRow(0)
        if row_h <= 0:
            row_h = max(18, self.fontMetrics().height() + 6)
        visible = 0

        def walk(item: QTreeWidgetItem) -> None:
            nonlocal visible
            visible += 1
            if item.isExpanded():
                for i in range(item.childCount()):
                    walk(item.child(i))

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        visible = max(1, visible)
        frame = self.frameWidth() * 2
        return visible * row_h + frame + 4


class ModelEpochTree(QWidget):
    """
    Compact Model → Epoch picker (chained expand tree).

    Rows size to content (no blank stretch). Hover an epoch for → (branch)
    or X (delete). Deep levels compress with «N». Emits ``selection_changed``.
    """

    selection_changed = pyqtSignal()
    create_model_requested = pyqtSignal()
    delete_run_requested = pyqtSignal(str)
    branch_from_checkpoint_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ModelEpochTree")
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        hdr = QHBoxLayout()
        hdr.setContentsMargins(0, 0, 0, 0)
        self.best_lbl = QLabel("BEST: —")
        self.best_lbl.setObjectName("ModelBestEpochLabel")
        self.best_lbl.setToolTip("Highest-quality checkpoint for the selected branch")
        hdr.addWidget(self.best_lbl, stretch=1)
        root.addLayout(hdr)

        self.tree = _CompactTreeWidget()
        self.tree.setObjectName("ModelEpochTreeWidget")
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAnimated(False)
        self.tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Height is fitted to rows; only scroll when the archive cap is hit.
        self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.tree.setToolTip(
            "Select a model run and epoch. BEST marks the highest-quality checkpoint. "
            "Hover an epoch for X (delete run). Raise Max Epochs and Train to resume."
        )
        self.tree.currentItemChanged.connect(self._on_current_changed)
        self.tree.itemExpanded.connect(lambda *_: self._fit_tree_height())
        self.tree.itemCollapsed.connect(lambda *_: self._fit_tree_height())
        root.addWidget(self.tree, stretch=0)

        self.create_btn = QPushButton("Create new")
        self.create_btn.setToolTip("Start a new model branch (0 epochs)")
        self.create_btn.clicked.connect(self.create_model_requested.emit)
        root.addWidget(self.create_btn)
        self.delete_btn = QPushButton("Delete…")
        self.delete_btn.setToolTip("Delete the selected saved model run from disk")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        root.addWidget(self.delete_btn)

        self._selection = ModelEpochSelection()
        self._block = False
        self._collapsed_nodes: dict[str, list[ModelTreeNode]] = {}

    def selection(self) -> ModelEpochSelection:
        return self._selection

    def selected_run_id(self) -> str | None:
        return self._selection.run_id

    def selected_checkpoint_key(self) -> str | None:
        return self._selection.checkpoint_key

    def selected_label(self) -> str:
        return self._selection.label or "—"

    def clear_selection(self, *, label: str = "(new model)") -> None:
        """Clear tree highlight for a fresh model branch."""
        self._block = True
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self._block = False
        self._selection = ModelEpochSelection(label=label)
        self.best_lbl.setText("BEST: —")
        self.delete_btn.setEnabled(False)
        self.selection_changed.emit()

    def set_tree(
        self,
        *,
        nodes: list[ModelTreeNode],
        preferred_run_id: str | None = None,
        preferred_checkpoint_key: str | None = None,
        select_none: bool = False,
    ) -> None:
        """Rebuild the tree from logical nodes and restore preferred selection."""
        self._block = True
        self.tree.clear()
        self._collapsed_nodes.clear()
        for node in nodes:
            self._add_node(node, parent_item=None, depth=0)

        if select_none:
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
            self._selection = ModelEpochSelection(label="(new model)")
            self.best_lbl.setText("BEST: —")
            self.delete_btn.setEnabled(False)
            self._block = False
            self.selection_changed.emit()
            self._fit_tree_height()
            return

        target: QTreeWidgetItem | None = None
        if preferred_checkpoint_key:
            target = self._find_ckpt_by_key(preferred_checkpoint_key)
        if target is None and preferred_run_id:
            target = self._find_run_leaf(preferred_run_id)
        if target is None and self.tree.topLevelItemCount():
            top = self.tree.topLevelItem(0)
            target = self._first_checkpoint(top) or top

        if target is not None:
            self.tree.setCurrentItem(target)
            self._apply_item(target)
        else:
            self._selection = ModelEpochSelection()
            self.best_lbl.setText("BEST: —")
            self.delete_btn.setEnabled(False)

        self._block = False
        self.selection_changed.emit()
        self._fit_tree_height()

    def _add_node(
        self,
        node: ModelTreeNode,
        *,
        parent_item: QTreeWidgetItem | None,
        depth: int,
    ) -> QTreeWidgetItem | None:
        if node.hidden_ancestor_count > 0 and node.kind == _KIND_COLLAPSED:
            item = QTreeWidgetItem([f"«{node.hidden_ancestor_count}»"])
            item.setData(0, _ROLE_KIND, _KIND_COLLAPSED)
            item.setData(0, _ROLE_NODE_ID, node.node_id)
            item.setToolTip(
                0,
                f"{node.hidden_ancestor_count} hidden ancestor level(s) — click to expand",
            )
            self._collapsed_nodes[node.node_id] = list(node.children)
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            return item

        if depth >= MAX_VISIBLE_DEPTH and node.children:
            collapsed = ModelTreeNode(
                node_id=node.node_id,
                label=node.label,
                kind=_KIND_COLLAPSED,
                hidden_ancestor_count=depth - MAX_VISIBLE_DEPTH + 1,
                children=node.children,
            )
            return self._add_node(collapsed, parent_item=parent_item, depth=depth)

        if node.kind == _KIND_CKPT and node.checkpoint is not None:
            item = self._make_ckpt_item(
                node.checkpoint,
                run_id=node.run_id,
                work_dir=node.work_dir,
            )
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            for child in node.children:
                self._add_node(child, parent_item=item, depth=depth + 1)
            return item

        item = QTreeWidgetItem([node.label])
        item.setData(0, _ROLE_KIND, node.kind)
        item.setData(0, _ROLE_RUN_ID, node.run_id)
        item.setData(0, _ROLE_WORK_DIR, node.work_dir)
        item.setData(0, _ROLE_NODE_ID, node.node_id)
        item.setToolTip(0, node.label)
        if parent_item is None:
            self.tree.addTopLevelItem(item)
        else:
            parent_item.addChild(item)
        if node.kind in (_KIND_CURRENT, _KIND_RUN):
            item.setExpanded(True)
        for child in node.children:
            self._add_node(child, parent_item=item, depth=depth + 1)
        return item

    def _make_ckpt_item(
        self,
        ckpt: AnalyzeCheckpoint,
        *,
        run_id: str | None,
        work_dir: str | None,
    ) -> QTreeWidgetItem:
        label = ckpt.label
        if ckpt.is_best and not label.upper().startswith("BEST"):
            label = f"BEST — {label}"
        elif ckpt.is_best:
            label = f"★ {label}"
        item = QTreeWidgetItem()
        item.setData(0, _ROLE_KIND, _KIND_CKPT)
        item.setData(0, _ROLE_RUN_ID, run_id)
        item.setData(0, _ROLE_CKPT_KEY, ckpt.key)
        item.setData(0, _ROLE_EPOCH, ckpt.epoch)
        item.setData(0, _ROLE_IS_BEST, bool(ckpt.is_best))
        item.setData(0, _ROLE_WORK_DIR, work_dir)
        item.setToolTip(0, ckpt.key)
        row = _EpochRowWidget(label, show_delete=bool(run_id))
        ckpt_key = ckpt.key
        row.branch_clicked.connect(
            lambda k=ckpt_key: self.branch_from_checkpoint_requested.emit(k)
        )
        if run_id:
            row.delete_clicked.connect(
                lambda rid=run_id: self.delete_run_requested.emit(rid)
            )
        self.tree.setItemWidget(item, 0, row)
        return item

    def _find_ckpt_by_key(self, key: str) -> QTreeWidgetItem | None:
        key_norm = str(key)

        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if str(item.data(0, _ROLE_CKPT_KEY) or "") == key_norm:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(i))
            if found is not None:
                return found
        return None

    def _find_run_leaf(self, run_id: str) -> QTreeWidgetItem | None:
        rid = str(run_id)

        def walk(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if str(item.data(0, _ROLE_RUN_ID) or "") == rid:
                if item.data(0, _ROLE_KIND) == _KIND_CKPT:
                    return item
                if item.childCount():
                    return self._first_checkpoint(item)
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(i))
            if found is not None:
                return found
        return None

    def _first_checkpoint(self, parent: QTreeWidgetItem) -> QTreeWidgetItem | None:
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, _ROLE_KIND) == _KIND_CKPT:
                return child
            nested = self._first_checkpoint(child)
            if nested is not None:
                return nested
        return None

    def _on_current_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if self._block:
            return
        if current is not None and current.data(0, _ROLE_KIND) == _KIND_COLLAPSED:
            self._expand_collapsed(current)
            return
        self._apply_item(current)
        self.selection_changed.emit()

    def _expand_collapsed(self, item: QTreeWidgetItem) -> None:
        node_id = str(item.data(0, _ROLE_NODE_ID) or "")
        children = self._collapsed_nodes.get(node_id)
        if not children:
            return
        parent = item.parent()
        index = parent.indexOfChild(item) if parent is not None else self.tree.indexOfTopLevelItem(item)
        self._block = True
        if parent is None:
            self.tree.takeTopLevelItem(index)
        else:
            parent.takeChild(index)
        insert_parent = parent
        for child in children:
            self._add_node(child, parent_item=insert_parent, depth=MAX_VISIBLE_DEPTH - 1)
        self._block = False

    def _apply_item(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            self._selection = ModelEpochSelection()
            self.best_lbl.setText("BEST: —")
            self.delete_btn.setEnabled(False)
            return
        kind = item.data(0, _ROLE_KIND)
        if kind == _KIND_RUN:
            if item.childCount():
                child = item.child(0)
                for i in range(item.childCount()):
                    c = item.child(i)
                    if c.data(0, _ROLE_KIND) == _KIND_CKPT:
                        child = c
                        break
                self._block = True
                self.tree.setCurrentItem(child)
                self._block = False
                self._apply_item(child)
                return
            run_id = item.data(0, _ROLE_RUN_ID)
            self._selection = ModelEpochSelection(
                run_id=str(run_id) if run_id else None,
                work_dir=str(item.data(0, _ROLE_WORK_DIR) or "") or None,
                label=str(
                    item.data(0, Qt.UserRole + 20) or item.toolTip(0) or item.text(0)
                ),
            )
            self.best_lbl.setText("BEST: —")
            self.delete_btn.setEnabled(bool(run_id))
            return
        if kind == _KIND_CURRENT:
            if item.childCount():
                child = item.child(0)
                for i in range(item.childCount()):
                    c = item.child(i)
                    if c.data(0, _ROLE_IS_BEST):
                        child = c
                        break
                self._block = True
                self.tree.setCurrentItem(child)
                self._block = False
                self._apply_item(child)
            return
        if kind != _KIND_CKPT:
            return
        run_id = item.data(0, _ROLE_RUN_ID)
        ckpt_key = item.data(0, _ROLE_CKPT_KEY)
        epoch = item.data(0, _ROLE_EPOCH)
        is_best = bool(item.data(0, _ROLE_IS_BEST))
        work_dir = item.data(0, _ROLE_WORK_DIR)
        row_widget = self.tree.itemWidget(item, 0)
        if isinstance(row_widget, _EpochRowWidget):
            label = row_widget._full_text
        else:
            label = str(
                item.data(0, Qt.UserRole + 20) or item.toolTip(0) or item.text(0)
            )
        self._selection = ModelEpochSelection(
            run_id=str(run_id) if run_id else None,
            checkpoint_key=str(ckpt_key) if ckpt_key else None,
            checkpoint_epoch=int(epoch) if epoch is not None else None,
            is_best=is_best,
            work_dir=str(work_dir) if work_dir else None,
            label=label,
        )
        if is_best:
            self.best_lbl.setText(f"BEST: {label}")
        elif epoch is not None:
            self.best_lbl.setText(f"BEST: —  (selected ep {epoch})")
        else:
            self.best_lbl.setText("BEST: —")
        parent = item.parent()
        if parent is not None and not is_best:
            for i in range(parent.childCount()):
                sib = parent.child(i)
                if sib.data(0, _ROLE_IS_BEST):
                    sib_label = sib.text(0)
                    w = self.tree.itemWidget(sib, 0)
                    if isinstance(w, _EpochRowWidget):
                        sib_label = w._full_text
                    else:
                        sib_label = str(
                            sib.data(0, Qt.UserRole + 20)
                            or sib.toolTip(0)
                            or sib.text(0)
                        )
                    self.best_lbl.setText(f"BEST: {sib_label}")
                    break
        self.delete_btn.setEnabled(bool(run_id))

    def _fit_tree_height(self) -> None:
        """Shrink the tree viewport to visible rows so the side panel has no blank gap."""
        width = max(self.tree.viewport().width(), self.tree.width(), 120)

        def walk(item: QTreeWidgetItem) -> None:
            row = self.tree.itemWidget(item, 0)
            if isinstance(row, _EpochRowWidget):
                row.set_elided_text(width - 28)
            else:
                full = item.data(0, Qt.UserRole + 20) or item.toolTip(0) or item.text(0)
                if full:
                    item.setData(0, Qt.UserRole + 20, str(full))
                    item.setToolTip(0, str(full))
                    fm = QFontMetrics(self.tree.font())
                    item.setText(
                        0, fm.elidedText(str(full), Qt.ElideRight, max(40, width - 40))
                    )
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        h = self.tree._content_height()
        # Cap so a huge archive list still scrolls inside a reasonable band.
        capped = min(max(h, 28), 280)
        self.tree.setFixedHeight(capped)
        # Avoid a second scrollbar when rows already fit the fitted height.
        if h <= capped:
            self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        else:
            self.tree.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_tree_height()

    def _on_delete_clicked(self) -> None:
        run_id = self._selection.run_id
        if run_id:
            self.delete_run_requested.emit(str(run_id))


def build_model_tree_nodes(
    *,
    runs: list[ModelRun],
    current_label: str,
    current_checkpoints: list[AnalyzeCheckpoint],
    current_work_dir: str | None,
    branch_checkpoints: dict[str, list[AnalyzeCheckpoint]],
) -> list[ModelTreeNode]:
    """Build hierarchical tree nodes from runs, active work, and branch work dirs."""
    runs_by_id = {r.run_id: r for r in runs}

    def _matching_children(
        parent_run_id: str | None, checkpoint_key: str | None
    ) -> list[ModelRun]:
        ck_norm = (
            str(Path(checkpoint_key).resolve()) if checkpoint_key else None
        )
        matched: list[ModelRun] = []
        for run in runs:
            if parent_run_id is not None:
                if run.parent_run_id != parent_run_id:
                    continue
            elif run.parent_run_id is not None and run.parent_run_id not in runs_by_id:
                pass
            elif run.parent_run_id is not None:
                continue
            if ck_norm and run.parent_checkpoint_key:
                if str(Path(run.parent_checkpoint_key).resolve()) != ck_norm:
                    continue
            elif run.parent_checkpoint_key or ck_norm:
                continue
            matched.append(run)
        return matched

    def _run_children(
        parent_run_id: str | None, checkpoint_key: str | None
    ) -> list[ModelTreeNode]:
        out: list[ModelTreeNode] = []
        for child in _matching_children(parent_run_id, checkpoint_key):
            snap = Path(child.snapshot_path)
            ckpt = AnalyzeCheckpoint(
                key=str(snap.resolve()),
                label=child.snapshot_name or snap.name,
                path=snap,
                epoch=child.epochs,
                is_best=False,
            )
            branch_work = child.work_dir
            branch_ckpts = branch_checkpoints.get(branch_work, [])
            child_nodes: list[ModelTreeNode] = []
            if branch_ckpts:
                child_nodes = [
                    ModelTreeNode(
                        node_id=f"branch-{child.run_id}-{c.key}",
                        label=c.label,
                        kind=_KIND_CKPT,
                        run_id=child.run_id,
                        checkpoint=c,
                        work_dir=branch_work,
                        children=_run_children(child.run_id, c.key),
                    )
                    for c in branch_ckpts
                ]
            else:
                child_nodes = [
                    ModelTreeNode(
                        node_id=f"run-{child.run_id}",
                        label=child.display_label(),
                        kind=_KIND_RUN,
                        run_id=child.run_id,
                        work_dir=branch_work,
                        children=[
                            ModelTreeNode(
                                node_id=f"run-{child.run_id}-ckpt",
                                label=ckpt.label,
                                kind=_KIND_CKPT,
                                run_id=child.run_id,
                                checkpoint=ckpt,
                                work_dir=branch_work,
                            )
                        ],
                    )
                ]
            out.extend(child_nodes)
        return out

    roots = [
        run
        for run in runs
        if not run.parent_run_id or run.parent_run_id not in runs_by_id
    ]

    nodes: list[ModelTreeNode] = []
    if current_checkpoints:
        ckpt_nodes = [
            ModelTreeNode(
                node_id=f"current-{c.key}",
                label=c.label,
                kind=_KIND_CKPT,
                checkpoint=c,
                work_dir=current_work_dir,
                children=_run_children(None, c.key) if not c.is_best else [],
            )
            for c in current_checkpoints
        ]
        nodes.append(
            ModelTreeNode(
                node_id="current-training",
                label=current_label,
                kind=_KIND_CURRENT,
                work_dir=current_work_dir,
                children=ckpt_nodes,
            )
        )

    for run in roots:
        snap = Path(run.snapshot_path)
        ckpt = AnalyzeCheckpoint(
            key=str(snap.resolve()),
            label=run.snapshot_name or snap.name,
            path=snap,
            epoch=run.epochs,
            is_best=False,
        )
        branch_ckpts = branch_checkpoints.get(run.work_dir, [])
        if branch_ckpts:
            children = [
                ModelTreeNode(
                    node_id=f"archived-{run.run_id}-{c.key}",
                    label=c.label,
                    kind=_KIND_CKPT,
                    run_id=run.run_id,
                    checkpoint=c,
                    work_dir=run.work_dir,
                    children=_run_children(run.run_id, c.key),
                )
                for c in branch_ckpts
            ]
        else:
            children = [
                ModelTreeNode(
                    node_id=f"archived-{run.run_id}-ckpt",
                    label=ckpt.label,
                    kind=_KIND_CKPT,
                    run_id=run.run_id,
                    checkpoint=ckpt,
                    work_dir=run.work_dir,
                    children=_run_children(run.run_id, ckpt.key),
                )
            ]
        nodes.append(
            ModelTreeNode(
                node_id=f"run-{run.run_id}",
                label=run.display_label(),
                kind=_KIND_RUN,
                run_id=run.run_id,
                work_dir=run.work_dir,
                children=children,
            )
        )
    return nodes
