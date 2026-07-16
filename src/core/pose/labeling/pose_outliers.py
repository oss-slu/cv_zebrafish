"""Heuristic outlier frames for pose QC review."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import normalize_edge


@dataclass
class PoseOutlierResult:
    """Outlier frames plus per-frame bodypart/bone highlights for review UI."""

    frames: set[int] = field(default_factory=set)
    reasons: dict[int, list[str]] = field(default_factory=dict)
    bodyparts: dict[int, set[str]] = field(default_factory=dict)
    bones: dict[int, set[tuple[str, str]]] = field(default_factory=dict)


def _bone_lengths(
    dataset: LabelDataset, frame_index: int
) -> list[tuple[tuple[str, str], float]]:
    names = dataset.bodyparts()
    if not names:
        return []
    lengths: list[tuple[tuple[str, str], float]] = []
    for i, j in dataset.schema.edges:
        edge = normalize_edge(i, j)
        if edge is None:
            continue
        a, b = names[edge[0]], names[edge[1]]
        pa = dataset.get_point(frame_index, a)
        pb = dataset.get_point(frame_index, b)
        if pa is None or pb is None:
            continue
        d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
        lengths.append(((a, b), d))
    return lengths


def _bone_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def detect_pose_outlier_frames(
    dataset: LabelDataset,
    frame_count: int,
    *,
    jump_px: float = 45.0,
    bone_deviation_ratio: float = 0.35,
    min_labeled_frames: int = 3,
) -> PoseOutlierResult:
    """
    Flag frames with large inter-frame jumps or abnormal bone lengths.

    Returns structured highlights for orange QC rendering on Verify Labels.
    """
    result = PoseOutlierResult()
    if frame_count <= 0 or not dataset.frames:
        return result

    labeled = sorted(dataset.frames.keys())
    if len(labeled) < min_labeled_frames:
        return result

    def _flag(frame_index: int, reason: str) -> None:
        result.frames.add(frame_index)
        result.reasons.setdefault(frame_index, []).append(reason)

    def _flag_bodypart(frame_index: int, name: str) -> None:
        result.bodyparts.setdefault(frame_index, set()).add(name)

    def _flag_bone(frame_index: int, a: str, b: str) -> None:
        result.bones.setdefault(frame_index, set()).add(_bone_key(a, b))
        _flag_bodypart(frame_index, a)
        _flag_bodypart(frame_index, b)

    # Inter-frame displacement spikes.
    prev_idx: int | None = None
    for fi in labeled:
        if prev_idx is not None:
            max_jump = 0.0
            worst_bp = ""
            for bp in dataset.bodyparts():
                p0 = dataset.get_point(prev_idx, bp)
                p1 = dataset.get_point(fi, bp)
                if p0 is None or p1 is None:
                    continue
                d = math.hypot(p0[0] - p1[0], p0[1] - p1[1])
                if d > max_jump:
                    max_jump = d
                    worst_bp = bp
            if max_jump >= jump_px:
                _flag(fi, f"Jump {max_jump:.0f}px ({worst_bp})")
                if worst_bp:
                    _flag_bodypart(fi, worst_bp)
                    for pair, _ in _bone_lengths(dataset, fi):
                        if worst_bp in pair:
                            _flag_bone(fi, pair[0], pair[1])
        prev_idx = fi

    # Bone length deviation from per-bone medians.
    bone_samples: dict[tuple[str, str], list[float]] = {}
    for fi in labeled:
        for pair, length in _bone_lengths(dataset, fi):
            bone_samples.setdefault(pair, []).append(length)

    bone_medians = {pair: median(vals) for pair, vals in bone_samples.items() if vals}
    for fi in labeled:
        for pair, length in _bone_lengths(dataset, fi):
            med = bone_medians.get(pair)
            if med is None or med <= 1e-6:
                continue
            ratio = abs(length - med) / med
            if ratio >= bone_deviation_ratio:
                a, b = pair
                _flag(fi, f"Bone {a}–{b} {ratio * 100:.0f}% off median")
                _flag_bone(fi, a, b)

    return result
