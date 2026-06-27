"""Tests for preview coordinate mapping and scroll resize."""

from core.pose.preview.preview_coords import DisplayMapping, wheel_arena_size_delta


def test_display_mapping_roundtrip():
    m = DisplayMapping.from_sizes(160, 120, 320, 240)
    fx, fy = m.widget_to_frame(m.draw_x + 10, m.draw_y + 10)
    assert fx is not None and fy is not None
    wx, wy = m.frame_to_widget(fx, fy)
    assert abs(wx - (m.draw_x + 10)) < 2
    assert abs(wy - (m.draw_y + 10)) < 2


def test_wheel_delta_sign():
    assert wheel_arena_size_delta(120) > 0
    assert wheel_arena_size_delta(-120) < 0
    assert abs(wheel_arena_size_delta(480)) > abs(wheel_arena_size_delta(120))
