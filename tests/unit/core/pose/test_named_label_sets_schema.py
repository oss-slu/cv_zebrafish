"""Load CSV datasets with Label-tab schema sidecar."""

from __future__ import annotations

from pathlib import Path

from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.labeling.labels_store import LabelDataset, save_schema
from core.pose.labeling.named_label_sets import apply_edges_to_dataset, load_dataset_from_dir
from core.pose.labeling.schema import PoseSchema


def test_load_dataset_from_dir_uses_schema_sidecar(tmp_path: Path) -> None:
    ds = LabelDataset(
        schema=PoseSchema(
            bodyparts=["Head", "BF", "LF1", "RF1"],
            edges=[],
        )
    )
    ds.set_point(0, "Head", 1.0, 2.0)
    ds.set_point(0, "BF", 3.0, 4.0)
    ds.set_point(0, "LF1", 5.0, 6.0)
    ds.set_point(0, "RF1", 7.0, 8.0)
    export_dlc_csv(ds, 1, tmp_path / "tracking.csv")
    save_schema(
        tmp_path,
        PoseSchema(
            bodyparts=["Head", "BF", "LF1", "RF1"],
            edges=[(1, 2), (1, 3)],
        ),
    )
    loaded = load_dataset_from_dir(tmp_path)
    names = loaded.bodyparts()
    named = {(names[a], names[b]) for a, b in loaded.schema.edges}
    assert ("BF", "LF1") in named
    assert ("BF", "RF1") in named


def test_apply_edges_prefers_human_schema() -> None:
    ds = LabelDataset(schema=PoseSchema(bodyparts=["Head", "BF", "LF1"], edges=[]))
    human = PoseSchema(bodyparts=["Head", "BF", "LF1"], edges=[(1, 2)])
    apply_edges_to_dataset(ds, preferred=human)
    assert ds.schema.edges == [(1, 2)]
