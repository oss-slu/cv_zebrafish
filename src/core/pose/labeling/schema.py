"""Lab zebrafish keypoint schema (11-point Sengupta preset)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.pose.labeling.labels_store import LabelDataset

# Head + BF + 2 per fin (center, tip — not body attachment) + 5 tail (T1–T5).
LAB_BODYPARTS: list[str] = [
    "Head",
    "BF",
    "LF1",
    "LF2",
    "RF1",
    "RF2",
    "T1",
    "T2",
    "T3",
    "T4",
    "T5",
]

# LF1/RF1 = fin center; LF2/RF2 = fin tip (distal). Attachment at body is not labeled.
FIN_CENTER_NAMES = frozenset({"LF1", "RF1"})
FIN_TIP_NAMES = frozenset({"LF2", "RF2"})


@dataclass
class PoseSchema:
    """User-editable bodypart list + skeleton edges (index pairs)."""

    bodyparts: list[str] = field(default_factory=lambda: list(LAB_BODYPARTS))
    edges: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "bodyparts": list(self.bodyparts),
            "edges": [[a, b] for a, b in self.edges],
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "PoseSchema":
        if not raw:
            return default_lab_schema()
        parts = list(raw.get("bodyparts") or LAB_BODYPARTS)
        edges_raw = raw.get("edges") or []
        edges: list[tuple[int, int]] = []
        for item in edges_raw:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                edges.append((int(item[0]), int(item[1])))
        return cls(bodyparts=parts, edges=edges)


def edges_for_bodyparts(names: list[str]) -> list[tuple[int, int]]:
    """Skeleton edges for whatever bodyparts are present (e.g. 3- or 5-point tail)."""
    idx = {n: i for i, n in enumerate(names)}
    edges: list[tuple[int, int]] = []

    def link(a: str, b: str) -> None:
        if a in idx and b in idx:
            edges.append((idx[a], idx[b]))

    # Fins attach near the body (BF), not the head tip — matches Label-tab bone tool.
    link("Head", "BF")
    link("BF", "LF1")
    link("LF1", "LF2")
    link("BF", "RF1")
    link("RF1", "RF2")
    tail = sorted(
        (n for n in names if len(n) > 1 and n.startswith("T") and n[1:].isdigit()),
        key=lambda n: int(n[1:]),
    )
    if tail:
        link("BF", tail[0])
        for i in range(len(tail) - 1):
            link(tail[i], tail[i + 1])
    return edges


def canonical_lab_schema() -> PoseSchema:
    """Session2_3 reference: 11-point lab preset + skeleton edges."""
    names = list(LAB_BODYPARTS)
    return PoseSchema(bodyparts=names, edges=edges_for_bodyparts(names))


def default_lab_schema() -> PoseSchema:
    """Alias for :func:`canonical_lab_schema`."""
    return canonical_lab_schema()


def apply_canonical_schema(dataset: "LabelDataset") -> "LabelDataset":
    """
    Force Session2_3 bodyparts and bones on ``dataset``.

    Keeps labeled coordinates for bodyparts that exist in the canonical schema;
    drops extras (custom points, alternate tail sets, etc.).
    """
    canonical = canonical_lab_schema()
    allowed = frozenset(canonical.bodyparts)
    for frame in dataset.frames.values():
        frame.points = {
            name: xy for name, xy in frame.points.items() if name in allowed
        }
    dataset.schema = deepcopy(canonical)
    return dataset


def normalize_edge(a: int, b: int) -> tuple[int, int]:
    return (min(a, b), max(a, b))


def bone_display_name(a: str, b: str) -> str:
    return f"{a} — {b}"


def edges_after_bodypart_removed(
    edges: list[tuple[int, int]], removed_index: int
) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for a, b in edges:
        if a == removed_index or b == removed_index:
            continue
        na = a - 1 if a > removed_index else a
        nb = b - 1 if b > removed_index else b
        out.append(normalize_edge(na, nb))
    return out


def edges_after_bodypart_reorder(
    edges: list[tuple[int, int]],
    names_before: list[str],
    names_after: list[str],
) -> list[tuple[int, int]]:
    """Remap edge indices after bodyparts list reorder (edges stored by name)."""
    idx = {n: i for i, n in enumerate(names_after)}
    out: list[tuple[int, int]] = []
    for a, b in edges:
        if a >= len(names_before) or b >= len(names_before):
            continue
        na, nb = names_before[a], names_before[b]
        if na not in idx or nb not in idx:
            continue
        out.append(normalize_edge(idx[na], idx[nb]))
    return out


def transfer_schema_edges(
    source_bodyparts: list[str],
    source_edges: list[tuple[int, int]],
    target_bodyparts: list[str],
) -> list[tuple[int, int]]:
    """Copy skeleton bones onto a (possibly reordered) bodypart list by name."""
    return edges_after_bodypart_reorder(source_edges, source_bodyparts, target_bodyparts)
