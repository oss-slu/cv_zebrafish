"""Tests for LabelCanvas helpers."""

from ui.components.pose.label_canvas import scene_padding_for_image


def test_scene_padding_for_image_uses_minimum():
    assert scene_padding_for_image(80, 60) == 200.0


def test_scene_padding_for_image_scales_with_large_crop():
    assert scene_padding_for_image(512, 400) == 512.0
    assert scene_padding_for_image(2336, 1728) == 2336.0
