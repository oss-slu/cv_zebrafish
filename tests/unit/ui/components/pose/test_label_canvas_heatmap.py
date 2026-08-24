"""Tests for Review-tab heatmap overlay on the label canvas."""

from __future__ import annotations

import sys

import numpy as np
import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_heatmap_to_rgba_shape_and_range():
    from ui.components.pose.label_canvas import heatmap_to_rgba

    hm = np.zeros((8, 10), dtype=np.float32)
    hm[3, 4] = 1.0
    rgba = heatmap_to_rgba(hm)
    assert rgba.shape == (8, 10, 4)
    assert rgba.dtype == np.uint8
    assert rgba[3, 4, 3] == 255
    assert rgba[0, 0, 3] == 0


def test_label_canvas_heatmap_value_at(qapp):
    from ui.components.pose.label_canvas import LabelCanvas

    canvas = LabelCanvas()
    hm = np.full((20, 30), 0.25, dtype=np.float32)
    hm[10, 15] = 0.9
    canvas.set_heatmap_overlay(hm, visible=True)
    assert canvas.heatmap_value_at(15.2, 10.4) == pytest.approx(0.9)
    assert canvas.heatmap_value_at(-1.0, 0.0) is None
    canvas.set_heatmap_overlay(None, visible=False)
    assert canvas.heatmap_value_at(5.0, 5.0) is None
    canvas.close()


def test_label_scene_heatmap_controls(qapp):
    from ui.pose_studio.scenes.label_scene import LabelScene

    scene = LabelScene()
    scene.set_review_mode(True)
    scene.show()
    qapp.processEvents()
    scene.set_heatmap_archives(
        [
            ("arch-a", "heatmaps — 100 frames"),
            ("arch-b", "heatmaps_epoch15 — 106 frames"),
        ]
    )
    assert scene.view_heatmap_cb.isEnabled()
    assert scene.heatmap_archive_combo.isVisible()
    assert scene.heatmap_archive_combo.count() == 2
    assert not scene.photo_opacity_slider.isEnabled()

    toggles: list[bool] = []
    scene.heatmap_view_changed.connect(toggles.append)
    scene.view_heatmap_cb.setChecked(True)
    assert toggles == [True]
    assert scene.photo_opacity_slider.isEnabled()

    archives: list[str] = []
    scene.heatmap_archive_changed.connect(archives.append)
    scene.heatmap_archive_combo.setCurrentIndex(1)
    assert archives == ["arch-b"]

    scene.set_heatmap_archives([])
    assert not scene.view_heatmap_cb.isChecked()
    assert not scene.photo_opacity_slider.isEnabled()
    scene.close()
