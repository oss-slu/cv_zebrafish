"""Tests for retrain loop label import."""

from core.pose.labeling.labels_store import LabelDataset
from core.pose.dataset.retrain_loop import merge_source_into_human
from core.pose.labeling.schema import default_lab_schema


def test_merge_source_fills_gaps_only():
    human = LabelDataset(schema=default_lab_schema())
    human.set_point(0, "Head", 1.0, 2.0)

    ai = LabelDataset(schema=default_lab_schema())
    ai.set_point(0, "Head", 9.0, 9.0)
    ai.set_point(1, "Head", 3.0, 4.0)
    ai.set_point(0, "BF", 5.0, 6.0)

    merged, added, touched = merge_source_into_human(human, ai, only_missing=True)
    assert merged.get_point(0, "Head") == (1.0, 2.0)
    assert merged.get_point(1, "Head") == (3.0, 4.0)
    assert merged.get_point(0, "BF") == (5.0, 6.0)
    assert added == 2
    assert touched == 2


def test_merge_source_overwrites_when_not_only_missing():
    human = LabelDataset(schema=default_lab_schema())
    human.set_point(0, "Head", 1.0, 2.0)

    ai = LabelDataset(schema=default_lab_schema())
    ai.set_point(0, "Head", 9.0, 9.0)

    merged, added, _ = merge_source_into_human(
        human, ai, manual_wins=False, only_missing=False
    )
    assert merged.get_point(0, "Head") == (9.0, 9.0)
    assert added == 1
