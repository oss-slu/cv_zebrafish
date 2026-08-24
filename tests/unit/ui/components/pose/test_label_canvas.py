"""Tests for LabelCanvas helpers."""

from ui.components.pose.label_canvas import scene_padding_for_image, scene_radius_for_view


def test_scene_padding_for_image_uses_minimum():
    assert scene_padding_for_image(80, 60) == 200.0


def test_scene_padding_for_image_scales_with_large_crop():
    assert scene_padding_for_image(512, 400) == 512.0
    assert scene_padding_for_image(2336, 1728) == 2336.0


def test_scene_radius_for_view_keeps_screen_size_when_zoomed_out():
    # At half view scale, scene radius doubles so on-screen size stays ~base.
    assert scene_radius_for_view(6.0, 0.5) == 12.0


def test_scene_radius_for_view_caps_at_max_scene_radius():
    assert scene_radius_for_view(6.0, 0.05) == 48.0
