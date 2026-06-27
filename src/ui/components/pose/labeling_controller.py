"""Undo/redo state for Pose Studio labeling."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import PoseSchema, edges_for_bodyparts


@dataclass
class _Snapshot:
    schema: PoseSchema
    frames: dict
    gap: int
    active_bodypart: str | None
    queue_index: int
    add_point_mode: bool


class LabelingController:
    """One bodypart × many frames; undo stack over full label state."""

    def __init__(self) -> None:
        self.dataset = LabelDataset()
        self.frame_queue: list[int] = []
        self.queue_index: int = 0
        self.active_bodypart: str | None = None
        self.add_point_mode: bool = False
        self.auto_advance_frames: bool = True
        self._undo: list[_Snapshot] = []
        self._redo: list[_Snapshot] = []
        self._listeners: list[Callable[[], None]] = []

    def bind_listener(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in self._listeners:
            cb()

    def _snapshot(self) -> _Snapshot:
        return _Snapshot(
            schema=deepcopy(self.dataset.schema),
            frames=deepcopy(self.dataset.frames),
            gap=self.dataset.gap,
            active_bodypart=self.active_bodypart,
            queue_index=self.queue_index,
            add_point_mode=self.add_point_mode,
        )

    def _restore(self, snap: _Snapshot) -> None:
        self.dataset.schema = deepcopy(snap.schema)
        self.dataset.frames = deepcopy(snap.frames)
        self.dataset.gap = snap.gap
        self.active_bodypart = snap.active_bodypart
        self.queue_index = snap.queue_index
        self.add_point_mode = snap.add_point_mode

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def load_dataset(self, dataset: LabelDataset, frame_queue: list[int]) -> None:
        self.dataset = dataset
        self.frame_queue = list(frame_queue)
        self.queue_index = 0
        self.active_bodypart = dataset.bodyparts()[0] if dataset.bodyparts() else None
        self.add_point_mode = False
        self._undo.clear()
        self._redo.clear()
        self._notify()

    def set_gap(
        self,
        gap: int,
        frame_queue: list[int],
        *,
        record_undo: bool = False,
    ) -> None:
        if record_undo:
            self._push_undo()
        self.dataset.gap = gap
        self.frame_queue = list(frame_queue)
        self.queue_index = min(self.queue_index, max(0, len(self.frame_queue) - 1))
        self._notify()

    def set_active_bodypart(self, name: str | None) -> None:
        self.add_point_mode = False
        self.active_bodypart = name
        if self.frame_queue:
            self.queue_index = max(0, min(self.queue_index, len(self.frame_queue) - 1))
        self._notify()

    def enter_add_point_mode(self) -> None:
        self.add_point_mode = True
        self.active_bodypart = None
        self._notify()

    def add_bodypart(self, name: str) -> None:
        self._push_undo()
        if name not in self.dataset.schema.bodyparts:
            self.dataset.schema.bodyparts.append(name)
        self.active_bodypart = name
        self.add_point_mode = False
        self._notify()

    def rename_bodypart(self, old_name: str, new_name: str) -> bool:
        new_name = (new_name or "").strip()
        if not new_name or old_name == new_name:
            return False
        if new_name in self.dataset.bodyparts():
            return False
        if old_name not in self.dataset.bodyparts():
            return False
        self._push_undo()
        idx = self.dataset.schema.bodyparts.index(old_name)
        self.dataset.schema.bodyparts[idx] = new_name
        for fl in self.dataset.frames.values():
            if old_name in fl.points:
                fl.points[new_name] = fl.points.pop(old_name)
        if self.active_bodypart == old_name:
            self.active_bodypart = new_name
        self._notify()
        return True

    def remove_bodypart(self, name: str) -> bool:
        if name not in self.dataset.bodyparts() or len(self.dataset.bodyparts()) <= 1:
            return False
        self._push_undo()
        self.dataset.schema.bodyparts.remove(name)
        self.dataset.schema.edges = edges_for_bodyparts(self.dataset.bodyparts())
        for fl in self.dataset.frames.values():
            fl.points.pop(name, None)
        if self.active_bodypart == name:
            self.active_bodypart = (
                self.dataset.bodyparts()[0] if self.dataset.bodyparts() else None
            )
        self._notify()
        return True

    def clear_all_bodyparts(self) -> None:
        self._push_undo()
        self.dataset.schema.bodyparts = []
        self.dataset.schema.edges = []
        self.dataset.frames.clear()
        self.active_bodypart = None
        self.add_point_mode = False
        self._notify()

    def current_frame_index(self) -> int:
        if not self.frame_queue:
            return 0
        return self.frame_queue[min(self.queue_index, len(self.frame_queue) - 1)]

    def place_active_point(self, x: float, y: float) -> None:
        if not self.active_bodypart:
            return
        self._push_undo()
        self.dataset.set_point(self.current_frame_index(), self.active_bodypart, x, y)
        if self.auto_advance_frames:
            self._advance_queue()
        self._notify()

    def place_new_point_at(self, name: str, x: float, y: float) -> None:
        self._push_undo()
        if name not in self.dataset.schema.bodyparts:
            self.dataset.schema.bodyparts.append(name)
        self.dataset.set_point(self.current_frame_index(), name, x, y)
        self.active_bodypart = name
        self.add_point_mode = False
        if self.auto_advance_frames:
            self._advance_queue()
        self._notify()

    def delete_active_point(self) -> bool:
        """Remove the active bodypart label on the current queue frame."""
        if not self.active_bodypart:
            return False
        frame_index = self.current_frame_index()
        if self.dataset.get_point(frame_index, self.active_bodypart) is None:
            return False
        self._push_undo()
        self.dataset.clear_point(frame_index, self.active_bodypart)
        self._notify()
        return True

    def set_auto_advance_frames(self, enabled: bool) -> None:
        self.auto_advance_frames = bool(enabled)

    def _advance_queue(self) -> None:
        if self.frame_queue and self.queue_index < len(self.frame_queue) - 1:
            self.queue_index += 1

    def begin_point_move(self) -> None:
        self._push_undo()

    def move_point(self, bodypart: str, x: float, y: float) -> None:
        self.dataset.set_point(self.current_frame_index(), bodypart, x, y)
        self._notify()

    def go_to_queue_index(self, index: int) -> None:
        if not self.frame_queue:
            return
        self.queue_index = max(0, min(index, len(self.frame_queue) - 1))
        self._notify()

    def go_prev_frame(self) -> None:
        self.go_to_queue_index(self.queue_index - 1)

    def go_next_frame(self) -> None:
        self.go_to_queue_index(self.queue_index + 1)

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._redo.append(self._snapshot())
        self._restore(self._undo.pop())
        self._notify()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        self._undo.append(self._snapshot())
        self._restore(self._redo.pop())
        self._notify()
        return True

    def progress_label(self) -> str:
        total = len(self.frame_queue)
        if total == 0:
            return "0 / 0"
        return f"{self.queue_index + 1} / {total}"

    def next_default_point_name(self) -> str:
        n = 1
        existing = set(self.dataset.bodyparts())
        while f"P{n}" in existing:
            n += 1
        return f"P{n}"
