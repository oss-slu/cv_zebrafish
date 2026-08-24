"""Tests for frame_sampler and labels_store."""

from pathlib import Path

import numpy as np

from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.labeling.frame_sampler import (
    _phase1_farthest_shape_picks,
    _phase2_fill_gaps,
    _pick_widest_gap_frame,
    _refinement_indices,
    build_diverse_label_frame_queue,
    build_label_frame_queue,
    coarse_stride_for_gap,
    gap_from_frames_to_analyze,
    rank_queue_by_uniqueness,
    reduce_queue_using_ranks,
    shape_scan_coarse_stride,
    shape_distance,
    target_label_frame_count,
)
from core.pose.labeling.labels_store import LabelDataset, load_labels, save_labels
from core.pose.labeling.schema import default_lab_schema


def _unit_vec(i: int, dim: int = 32) -> np.ndarray:
    v = np.zeros(dim, dtype=np.float32)
    v[i % dim] = 1.0
    return v


def test_coarse_stride_matches_gap():
    assert coarse_stride_for_gap(15) == 15
    assert coarse_stride_for_gap(0) == 1


def test_shape_scan_coarse_stride_denser_than_queue_gap():
    assert shape_scan_coarse_stride(33) == 8
    assert shape_scan_coarse_stride(15) < coarse_stride_for_gap(15)
    assert shape_scan_coarse_stride(1) == 1


def test_refinement_indices_only_inside_wide_gaps():
    n = 100
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, n, 10):
        fps[i] = _unit_vec(0)
    refine = _refinement_indices(n, 10, fps)
    assert all(0 <= i < n for i in refine)
    assert all(i % 10 != 0 or i in (0, n - 1) for i in refine)


def test_gap_from_frames_to_analyze():
    assert gap_from_frames_to_analyze(10_001, 300) == 33
    assert gap_from_frames_to_analyze(100, 100) == 0
    assert target_label_frame_count(10_001, 33) in (302, 303)


def test_queue_length_matches_frames_to_analyze():
    n = 10_001
    target = 300
    gap = gap_from_frames_to_analyze(n, target)
    uniform = build_label_frame_queue(n, gap, target=target)
    assert len(uniform) == target
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, n, gap):
        fps[i] = _unit_vec(i // gap)
    diverse = build_diverse_label_frame_queue(n, gap, fps, target=target)
    assert len(diverse) == target


def test_target_label_frame_count():
    assert target_label_frame_count(300, 30) == 10
    assert target_label_frame_count(100, 0) == 100
    assert target_label_frame_count(50, 100) == 1


def test_build_label_frame_queue_gap():
    assert build_label_frame_queue(10, 0) == list(range(10))
    q = build_label_frame_queue(100, 10)
    assert len(q) == 10
    assert q[0] == 0


def test_farthest_point_picks_diverse_shapes():
    n = 90
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, 30):
        fps[i] = _unit_vec(0)
    for i in range(30, 60):
        fps[i] = _unit_vec(1)
    for i in range(60, 90):
        fps[i] = _unit_vec(2)

    selected = _phase1_farthest_shape_picks(fps, target=9, n=n)
    assert selected[0] == 0
    assert len(selected) >= 3
    # Shapes from three clusters should appear before diversity runs out.
    clusters = set()
    for s in selected:
        fp = fps[s]
        assert fp is not None
        if fp[0] > 0.5:
            clusters.add(0)
        elif fp[1] > 0.5:
            clusters.add(1)
        elif fp[2] > 0.5:
            clusters.add(2)
    assert len(clusters) >= 3


def test_phase2_fills_widest_gaps():
    n = 100
    fps = [_unit_vec(0)] * n
    selected = [0, 80]
    filled = _phase2_fill_gaps(selected, target=5, n=n, fingerprints=fps)
    assert len(filled) == 5
    assert filled[0] == 0
    assert 80 in filled
    # Midpoint of 0..80 gap should be included early.
    assert any(35 <= f <= 45 for f in filled)


def test_pick_widest_gap_frame_prefers_center_without_fingerprints():
    n = 100
    fps: list[np.ndarray | None] = [None] * n
    pick = _pick_widest_gap_frame([0, 80], n, fps)
    assert pick == 40


def test_pick_widest_gap_frame_spirals_from_center_for_sparse_fingerprints():
    n = 100
    fps: list[np.ndarray | None] = [None] * n
    fps[42] = _unit_vec(0)
    pick = _pick_widest_gap_frame([0, 80], n, fps)
    assert pick == 40


def test_build_diverse_queue_sparse_coarse_samples():
    n = 100
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, n, 10):
        fps[i] = _unit_vec(i // 10)
    queue = build_diverse_label_frame_queue(n, 10, fps, target=10)
    assert len(queue) == 10
    assert queue == sorted(queue)


def test_build_diverse_queue_target_size():
    n = 100
    fps: list[np.ndarray | None] = [None] * n
    for i in range(n):
        fps[i] = _unit_vec(i % 8)
    queue = build_diverse_label_frame_queue(n, 10, fps, target=10)
    assert len(queue) == 10
    assert queue[0] == 0
    assert queue == sorted(queue)


def test_reduce_queue_by_uniqueness():
    from core.pose.labeling.frame_sampler import reduce_queue_by_uniqueness

    n = 20
    fps: list[np.ndarray | None] = [None] * n
    for i in (0, 5, 10, 15):
        fps[i] = _unit_vec(i)
    out = reduce_queue_by_uniqueness(fps, [0, 5, 10, 15, 1, 2], 3)
    assert len(out) == 3
    assert out == sorted(out)
    assert set(out).issubset({0, 5, 10, 15, 1, 2})


def test_rank_queue_by_uniqueness_covers_full_queue():
    n = 90
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, 30):
        fps[i] = _unit_vec(0)
    for i in range(30, 60):
        fps[i] = _unit_vec(1)
    for i in range(60, 90):
        fps[i] = _unit_vec(2)
    queue = build_diverse_label_frame_queue(n, 10, fps, target=9)
    ranks = rank_queue_by_uniqueness(fps, queue)
    assert set(ranks.keys()) == set(queue)
    assert len(set(ranks.values())) == len(queue)
    reduced = reduce_queue_using_ranks(queue, ranks, 3, fingerprints=fps)
    assert len(reduced) == 3
    assert set(reduced).issubset(set(queue))


def test_build_diverse_queue_assigns_ranks_for_every_member():
    n = 100
    fps: list[np.ndarray | None] = [None] * n
    for i in range(0, n, 10):
        fps[i] = _unit_vec(i // 10)
    ranks: dict[int, int] = {}
    queue = build_diverse_label_frame_queue(n, 10, fps, target=10, ranks=ranks)
    assert len(queue) == 10
    assert set(ranks.keys()) == set(queue)
    assert len(set(ranks.values())) == len(queue)


def test_reduce_queue_using_ranks_prefers_high_rank():
    queue = [0, 10, 20, 30, 40]
    ranks = {0: 1, 10: 5, 20: 3, 30: 4, 40: 2}
    out = reduce_queue_using_ranks(queue, ranks, 3)
    assert out == [10, 20, 30]
    assert set(out) == {10, 30, 20}


def test_reduce_queue_using_ranks_fallback_for_missing():
    n = 20
    fps: list[np.ndarray | None] = [None] * n
    for i in (0, 5, 10, 15):
        fps[i] = _unit_vec(i)
    queue = [0, 5, 10, 15, 1, 2]
    ranks = {0: 10, 5: 9}
    out = reduce_queue_using_ranks(queue, ranks, 3, fingerprints=fps)
    assert len(out) == 3
    assert 0 in out and 5 in out
    assert out == sorted(out)


def test_shape_distance():
    a = _unit_vec(0)
    b = _unit_vec(1)
    assert shape_distance(a, b) > shape_distance(a, a)


def test_labels_roundtrip(tmp_path: Path):
    d = tmp_path / "human"
    ds = LabelDataset(schema=default_lab_schema(), gap=5)
    ds.set_point(0, "Head", 10.0, 20.0)
    save_labels(d, ds)
    loaded = load_labels(d)
    assert loaded.get_point(0, "Head") == (10.0, 20.0)
    assert len(loaded.bodyparts()) == 11


def test_labels_persist_frame_queue(tmp_path: Path):
    d = tmp_path / "human"
    ds = LabelDataset(
        schema=default_lab_schema(),
        frames_to_analyze=12,
        label_frame_queue=[0, 50, 100],
    )
    save_labels(d, ds)
    loaded = load_labels(d)
    assert loaded.label_frame_queue == [0, 50, 100]
    assert loaded.frames_to_analyze == 12


def test_export_dlc_csv(tmp_path: Path):
    ds = LabelDataset(schema=default_lab_schema())
    ds.set_point(0, "Head", 1.0, 2.0)
    out = tmp_path / "t.csv"
    export_dlc_csv(ds, 2, out)
    text = out.read_text(encoding="utf-8")
    assert "bodyparts" in text
    assert "Head" in text
