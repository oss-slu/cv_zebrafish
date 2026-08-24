"""Smoke tests for Pose Studio label-set dropdown wiring."""

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


def test_label_scene_set_label_sets(qapp):
    from ui.pose_studio.scenes.label_scene import LabelScene

    scene = LabelScene()
    scene.set_label_sets(
        [
            ("human", "Human — 0/300 frames"),
            ("trial_a", "Trial A — 5/300 frames"),
        ]
    )
    assert scene.label_set_combo.count() == 2
    scene.set_active_label_set("trial_a")
    assert scene.label_set_combo.currentData() == "trial_a"
    scene.close()


def test_label_scene_hover_close_custom_only(qapp):
    from ui.pose_studio.scenes.label_scene import LabelScene

    scene = LabelScene()
    scene.set_label_sets(
        [
            ("human", "Human — 0/300 frames"),
            ("trial_a", "Trial A — 5/300 frames"),
        ]
    )
    scene.set_active_label_set("human")
    scene._on_label_set_row_hovered(True)
    assert scene.label_set_close_btn.isHidden()

    scene.set_active_label_set("trial_a")
    scene._on_label_set_row_hovered(True)
    assert not scene.label_set_close_btn.isHidden()

    removed: list[str] = []
    scene.label_set_remove_requested.connect(removed.append)
    scene.label_set_close_btn.click()
    assert removed == ["trial_a"]
    scene.close()


def test_label_scene_mount_helpers(qapp):
    from ui.main_panels.pose_label_widget import PoseLabelWidget
    from ui.pose_studio.scenes.label_scene import LabelScene

    scene = LabelScene()
    widget = PoseLabelWidget()
    widget.attach_label_chrome(scene)

    assert widget.bodypart_list.parent() is scene.side_schema_host
    assert widget.frame_strip.parent() is scene.timeline_host
    assert widget._canvas.parent() is widget
    widget.close()
    scene.close()


def test_pose_label_widget_labels_changed_on_save(qapp, tmp_path):
    from core.pose.labeling.labels_store import LabelDataset, save_labels
    from core.pose.labeling.schema import default_lab_schema
    from ui.main_panels.pose_label_widget import PoseLabelWidget

    label_dir = tmp_path / "human"
    ds = LabelDataset(schema=default_lab_schema())
    save_labels(label_dir, ds)

    widget = PoseLabelWidget()
    widget.set_frame_reader(lambda _i: None, 10)
    widget.set_label_directory(
        label_dir,
        label_set_id="human",
        display_name="Human",
    )
    hits: list[int] = []
    widget.labels_changed.connect(lambda: hits.append(1))
    widget._controller.enter_add_point_mode()
    widget._on_point_placed(10.0, 20.0)
    assert len(hits) == 1
    widget.close()


def test_pose_label_widget_label_directory_switch(qapp, tmp_path):
    from core.pose.labeling.labels_store import save_labels
    from core.pose.labeling.schema import default_lab_schema
    from ui.main_panels.pose_label_widget import PoseLabelWidget

    human_dir = tmp_path / "human"
    custom_dir = tmp_path / "custom"
    ds = default_lab_schema()
    from core.pose.labeling.labels_store import LabelDataset

    empty = LabelDataset(schema=ds)
    save_labels(human_dir, empty)

    widget = PoseLabelWidget()
    widget.set_frame_reader(lambda _i: None, 100)
    widget.load_video_context(
        session_name="sess",
        project_id="default",
        video_id="vid1",
        arena=__import__("core.pose.detection.arena", fromlist=["ArenaConfig"]).ArenaConfig(),
        blob_params=__import__(
            "core.pose.detection.blob", fromlist=["BlobParams"]
        ).BlobParams(),
        frame_count=100,
        video_path=None,
        video_dir=tmp_path,
    )
    widget.set_label_directory(
        human_dir,
        label_set_id="human",
        display_name="Human",
    )
    assert widget.active_label_set_id == "human"
    assert widget.labeled_counts()["total_frames"] == 100

    widget.set_label_directory(
        custom_dir,
        label_set_id="custom_slug",
        display_name="Custom",
    )
    assert widget.active_label_set_id == "custom_slug"
    assert widget.active_label_set_display == "Custom"
    widget.close()


def test_pose_label_widget_frames_ui_max_caps_to_video_length(qapp):
    from ui.main_panels.pose_label_widget import PoseLabelWidget

    widget = PoseLabelWidget()
    widget.set_frame_reader(lambda _i: None, 106)
    assert widget._frames_ui_max() == 106
    assert widget._frames_spin.maximum() == 106
    assert widget._frames_max_lbl.text() == "/ 106"
    widget.set_frame_reader(lambda _i: None, 500)
    assert widget._frames_ui_max() == 300
    widget.close()


def test_pose_label_widget_orphan_label_detection_and_prune(qapp):
    from core.pose.labeling.labels_store import FrameLabels, LabelDataset
    from core.pose.labeling.schema import canonical_lab_schema
    from ui.main_panels.pose_label_widget import PoseLabelWidget

    widget = PoseLabelWidget()
    ds = LabelDataset(schema=canonical_lab_schema())
    ds.frames[5] = FrameLabels(points={"Head": (10.0, 20.0)})
    ds.frames[9] = FrameLabels(points={"Head": None})
    widget._controller.load_dataset(ds, [1, 2, 3])

    assert widget._labeled_frame_indices_outside_queue([1, 2, 3]) == [5]
    widget._prune_labels_outside_queue([1, 2, 3])
    assert 5 not in widget._controller.dataset.frames
    assert 9 not in widget._controller.dataset.frames
    widget.close()
