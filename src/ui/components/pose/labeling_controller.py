"""Undo/redo state for Pose Studio labeling."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Callable

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import (
    PoseSchema,
    edges_after_bodypart_removed,
    edges_after_bodypart_reorder,
    normalize_edge,
)


@dataclass
class _Snapshot:
    schema: PoseSchema
    frames: dict
    gap: int
    active_bodypart: str | None
    queue_index: int
    add_point_mode: bool
    bone_mode: bool


class LabelingController:
    """One bodypart × many frames; undo stack over full label state."""

    def __init__(self) -> None:
        self.dataset = LabelDataset()
        self.frame_queue: list[int] = []
        self.queue_index: int = 0
        self.active_bodypart: str | None = None
        self.add_point_mode: bool = False
        self.bone_mode: bool = False
        self._bone_mode_return_bodypart: str | None = None
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
            bone_mode=self.bone_mode,
        )

    def _restore(self, snap: _Snapshot) -> None:
        self.dataset.schema = deepcopy(snap.schema)
        self.dataset.frames = deepcopy(snap.frames)
        self.dataset.gap = snap.gap
        self.active_bodypart = snap.active_bodypart
        self.queue_index = snap.queue_index
        self.add_point_mode = snap.add_point_mode
        self.bone_mode = snap.bone_mode

    def _push_undo(self) -> None:
        self._undo.append(self._snapshot())
        self._redo.clear()

    def load_dataset(self, dataset: LabelDataset, frame_queue: list[int]) -> None:
        self.dataset = dataset
        self.frame_queue = list(frame_queue)
        self.queue_index = 0
        self.active_bodypart = dataset.bodyparts()[0] if dataset.bodyparts() else None
        self.add_point_mode = False
        self.bone_mode = False
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
        self.bone_mode = False
        self.active_bodypart = name
        if self.frame_queue:
            self.queue_index = max(0, min(self.queue_index, len(self.frame_queue) - 1))
        self._notify()

    def enter_add_point_mode(self) -> None:
        self.add_point_mode = True
        self.bone_mode = False
        self.active_bodypart = None
        self._notify()

    def enter_bone_mode(self) -> None:
        self._bone_mode_return_bodypart = self.active_bodypart
        self.bone_mode = True
        self.add_point_mode = False
        self.active_bodypart = None
        self._notify()

    def exit_bone_mode(self) -> None:
        if not self.bone_mode:
            return
        self.bone_mode = False
        self._notify()

    def _finish_bone_mode(self) -> None:
        """Exit bone tool and restore the bodypart selected before it was activated."""
        self.bone_mode = False
        self.active_bodypart = self._bone_mode_return_bodypart
        self._bone_mode_return_bodypart = None
        self._notify()

    def cancel_bone_mode(self) -> None:
        """Exit bone tool without creating a bone (0–1 picks pending)."""
        if not self.bone_mode:
            return
        self._finish_bone_mode()

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
        idx = self.dataset.schema.bodyparts.index(name)
        self.dataset.schema.bodyparts.remove(name)
        self.dataset.schema.edges = edges_after_bodypart_removed(
            self.dataset.schema.edges, idx
        )
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
        self.bone_mode = False
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

    def go_to_absolute_frame(self, frame_index: int) -> None:
        """Jump to a video frame index (frame_queue must list video indices)."""
        if not self.frame_queue:
            return
        try:
            qi = self.frame_queue.index(int(frame_index))
        except ValueError:
            qi = max(0, min(int(frame_index), len(self.frame_queue) - 1))
        self.go_to_queue_index(qi)

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

    def bone_name_pairs(self) -> list[tuple[str, str]]:
        names = self.dataset.bodyparts()
        pairs: list[tuple[str, str]] = []
        for a, b in self.dataset.schema.edges:
            if 0 <= a < len(names) and 0 <= b < len(names):
                lo, hi = min(a, b), max(a, b)
                pairs.append((names[lo], names[hi]))
        return pairs

    def add_bone(self, a: str, b: str) -> bool:
        if a == b:
            return False
        names = self.dataset.bodyparts()
        if a not in names or b not in names:
            return False
        edge = normalize_edge(names.index(a), names.index(b))
        if edge in self.dataset.schema.edges:
            return False
        self._push_undo()
        self.dataset.schema.edges.append(edge)
        if self.bone_mode:
            self._finish_bone_mode()
        else:
            self._notify()
        return True

    def remove_bone(self, a: str, b: str) -> bool:
        names = self.dataset.bodyparts()
        if a not in names or b not in names:
            return False
        edge = normalize_edge(names.index(a), names.index(b))
        if edge not in self.dataset.schema.edges:
            return False
        self._push_undo()
        self.dataset.schema.edges = [
            e for e in self.dataset.schema.edges if e != edge
        ]
        self._notify()
        return True

    def reorder_bodypart(self, name: str, target_index: int) -> bool:
        parts = self.dataset.schema.bodyparts
        if name not in parts:
            return False
        old_index = parts.index(name)
        target_index = max(0, min(target_index, len(parts) - 1))
        if old_index == target_index:
            return False
        self._push_undo()
        names_before = list(parts)
        parts.pop(old_index)
        if target_index > old_index:
            target_index -= 1
        parts.insert(target_index, name)
        self.dataset.schema.edges = edges_after_bodypart_reorder(
            self.dataset.schema.edges,
            names_before,
            list(parts),
        )
        self._notify()
        return True
