"""Reference bone lengths from manual labels (for constrained decode)."""

from __future__ import annotations

import math
from statistics import median

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import normalize_edge


def bone_lengths_on_frame(
    dataset: LabelDataset,
    frame_index: int,
) -> dict[tuple[str, str], float]:
    """Edge lengths on one frame (full-frame pixels)."""
    names = dataset.bodyparts()
    if not names:
        return {}
    lengths: dict[tuple[str, str], float] = {}
    for i, j in dataset.schema.edges:
        edge = normalize_edge(i, j)
        if edge is None:
            continue
        a, b = names[edge[0]], names[edge[1]]
        pa = dataset.get_point(frame_index, a)
        pb = dataset.get_point(frame_index, b)
        if pa is None or pb is None:
            continue
        lengths[(a, b)] = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
    return lengths


def median_bone_lengths(
    dataset: LabelDataset,
    *,
    frame_indices: list[int] | None = None,
    max_frames: int = 20,
) -> dict[tuple[str, str], float]:
    """
    Median bone length per edge from manual labels.

    Uses the first ``max_frames`` labeled frames when ``frame_indices`` is omitted.
    """
    if frame_indices is None:
        labeled = sorted(dataset.frames.keys())
        frame_indices = labeled[:max_frames]
    samples: dict[tuple[str, str], list[float]] = {}
    for fi in frame_indices:
        for edge, length in bone_lengths_on_frame(dataset, fi).items():
            samples.setdefault(edge, []).append(length)
    return {edge: float(median(vals)) for edge, vals in samples.items() if vals}
