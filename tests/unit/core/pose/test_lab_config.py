"""Tests for lab kinematics config generation."""

from core.pose.dataset.lab_config import schema_to_config_points
from core.pose.labeling.schema import default_lab_schema


def test_schema_to_config_points_eleven_point():
    schema = default_lab_schema()
    pts = schema_to_config_points(schema)
    assert pts["head"]["pt1"] == "Head"
    assert pts["head"]["pt2"] == "BF"
    assert pts["left_fin"] == ["LF1", "LF2"]
    assert pts["right_fin"] == ["RF1", "RF2"]
    assert pts["tail"] == ["T1", "T2", "T3", "T4", "T5"]
    assert "T5" in pts["spine"]
    assert "Head" in pts["spine"]
