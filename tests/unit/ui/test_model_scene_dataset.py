"""Smoke tests for Model scene training-dataset picker."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_model_scene_training_sources(qapp):
    from PyQt5.QtCore import Qt
    from ui.pose_studio.scenes.model_scene import ModelScene

    scene = ModelScene()
    scene.set_training_sources(
        [("v1", "vid1 — 10 labeled"), ("v2", "vid2 — 0 labeled")],
        selected_ids=["v1"],
    )
    assert scene.selected_training_source_ids() == ["v1"]
    assert scene.dataset_list.item(0).checkState() == Qt.Checked
    assert scene.dataset_list.item(1).checkState() == Qt.Unchecked
    scene.select_all_training_sources()
    assert set(scene.selected_training_source_ids()) == {"v1", "v2"}
    scene.set_train_button_text("Train")
    assert scene.train_btn.text() == "Train"
    scene.close()
