"""Lab zebrafish keypoint schema (11-point Sengupta preset)."""

from __future__ import annotations

from dataclasses import dataclass, field

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

    link("Head", "BF")
    link("Head", "LF1")
    link("LF1", "LF2")
    link("Head", "RF1")
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


def default_lab_schema() -> PoseSchema:
    """11-point lab preset: head, BF, fin center+tip pairs, five tail segments."""
    names = list(LAB_BODYPARTS)
    return PoseSchema(bodyparts=names, edges=edges_for_bodyparts(names))
