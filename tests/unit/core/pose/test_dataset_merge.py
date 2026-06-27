"""Tests for DLC CSV import and dataset merge."""

from pathlib import Path

from core.pose.dataset.dataset_merge import merge_manual_over_ai
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import default_lab_schema


def test_import_export_roundtrip(tmp_path: Path):
    ds = LabelDataset(schema=default_lab_schema())
    ds.set_point(0, "Head", 10.0, 20.0)
    ds.set_point(1, "Head", 11.0, 21.0)
    ds.set_point(0, "BF", 5.0, 6.0)
    out = tmp_path / "t.csv"
    export_dlc_csv(ds, 3, out)
    loaded, fc, parts = import_dlc_csv(out)
    assert fc == 3
    assert "Head" in parts
    assert loaded.get_point(0, "Head") == (10.0, 20.0)
    assert loaded.get_point(1, "Head") == (11.0, 21.0)
    assert loaded.get_point(0, "BF") == (5.0, 6.0)


def test_merge_manual_wins_over_ai():
    manual = LabelDataset(schema=default_lab_schema())
    manual.set_point(0, "Head", 1.0, 2.0)

    ai = LabelDataset(schema=default_lab_schema())
    ai.set_point(0, "Head", 9.0, 9.0)
    ai.set_point(1, "Head", 3.0, 4.0)

    merged = merge_manual_over_ai(manual, ai)
    assert merged.get_point(0, "Head") == (1.0, 2.0)
    assert merged.get_point(1, "Head") == (3.0, 4.0)
