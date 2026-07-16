"""Tests for pose outlier heuristics."""

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.pose_outliers import detect_pose_outlier_frames
from core.pose.labeling.schema import PoseSchema


def _two_point_dataset() -> LabelDataset:
    ds = LabelDataset(schema=PoseSchema(bodyparts=["A", "B"], edges=[(0, 1)]))
    ds.set_point(0, "A", 10.0, 10.0)
    ds.set_point(0, "B", 20.0, 10.0)
    ds.set_point(1, "A", 12.0, 10.0)
    ds.set_point(1, "B", 22.0, 10.0)
    return ds


def test_detect_jump_outlier():
    ds = _two_point_dataset()
    ds.set_point(2, "A", 200.0, 10.0)
    ds.set_point(2, "B", 210.0, 10.0)
    result = detect_pose_outlier_frames(ds, 3, jump_px=50.0)
    assert 2 in result.frames
    assert any("Jump" in r for r in result.reasons[2])
    assert "A" in result.bodyparts[2]
    assert ("A", "B") in result.bones[2]


def test_no_outliers_on_smooth_motion():
    ds = _two_point_dataset()
    result = detect_pose_outlier_frames(ds, 2, jump_px=50.0)
    assert not result.frames
