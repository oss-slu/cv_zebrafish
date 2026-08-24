"""Tests for schema edge helpers."""

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import (
    PoseSchema,
    apply_canonical_schema,
    canonical_lab_schema,
    edges_after_bodypart_removed,
    edges_after_bodypart_reorder,
    edges_for_bodyparts,
    normalize_edge,
    transfer_schema_edges,
)


def test_normalize_edge():
    assert normalize_edge(3, 1) == (1, 3)


def test_edges_after_bodypart_removed():
    edges = [(0, 1), (1, 2), (0, 3)]
    assert edges_after_bodypart_removed(edges, 1) == [(0, 2)]


def test_edges_after_bodypart_reorder():
    edges = [(0, 2)]
    names_before = ["A", "B", "C"]
    names_after = ["C", "A", "B"]
    assert edges_after_bodypart_reorder(edges, names_before, names_after) == [(0, 1)]


def test_edges_for_bodyparts_fins_attach_at_bf():
    names = ["Head", "BF", "LF1", "LF2", "RF1", "RF2", "T1"]
    edges = edges_for_bodyparts(names)
    named = {(names[a], names[b]) for a, b in edges}
    assert ("BF", "LF1") in named or ("LF1", "BF") in named
    assert ("BF", "RF1") in named or ("RF1", "BF") in named
    assert ("Head", "LF1") not in named
    assert ("Head", "RF1") not in named


def test_transfer_schema_edges_preserves_label_tab_bones():
    src_names = ["Head", "BF", "LF1", "RF1"]
    src_edges = [(1, 2), (1, 3)]  # BF—LF1, BF—RF1
    dst_names = ["Head", "BF", "LF1", "LF2", "RF1", "RF2"]
    out = transfer_schema_edges(src_names, src_edges, dst_names)
    named = {(dst_names[a], dst_names[b]) for a, b in out}
    assert named == {("BF", "LF1"), ("BF", "RF1")}


def test_apply_canonical_schema_replaces_custom_points_and_bones():
    ds = LabelDataset(
        schema=PoseSchema(
            bodyparts=["Head", "BF", "P1"],
            edges=[(0, 1)],
        )
    )
    ds.set_point(0, "Head", 1.0, 2.0)
    ds.set_point(0, "P1", 9.0, 9.0)
    apply_canonical_schema(ds)
    assert ds.bodyparts() == canonical_lab_schema().bodyparts
    assert ds.schema.edges == canonical_lab_schema().edges
    assert ds.get_point(0, "Head") == (1.0, 2.0)
    assert "P1" not in ds.frames[0].points
