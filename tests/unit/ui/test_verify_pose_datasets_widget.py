"""Smoke tests for Verify Pose Studio datasets tree + priority list."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QTreeWidgetItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def _seed_entries(tmp_path: Path, monkeypatch) -> None:
    from core.pose.dataset.dataset_catalog import PoseDatasetEntry

    entries = [
        PoseDatasetEntry(
            video_id="vid_a",
            source="human",
            dir_path=tmp_path / "a_human",
            tracking_csv=None,
            labels_json=tmp_path / "a_human" / "labels.json",
            labeled_frames=3,
            bodyparts=["Head"],
            frame_count=10,
            display_name="Fish A",
        ),
        PoseDatasetEntry(
            video_id="vid_a",
            source="ai",
            dir_path=tmp_path / "a_ai",
            tracking_csv=tmp_path / "a_ai" / "tracking.csv",
            labels_json=None,
            labeled_frames=8,
            bodyparts=["Head"],
            frame_count=10,
            display_name="Fish A",
        ),
        PoseDatasetEntry(
            video_id="vid_b",
            source="human",
            dir_path=tmp_path / "b_human",
            tracking_csv=None,
            labels_json=tmp_path / "b_human" / "labels.json",
            labeled_frames=2,
            bodyparts=["Head"],
            frame_count=10,
            display_name="Fish B",
        ),
        PoseDatasetEntry(
            video_id="vid_b",
            source="external",
            dir_path=tmp_path / "b_ext",
            tracking_csv=tmp_path / "b_ext" / "tracking.csv",
            labels_json=None,
            labeled_frames=4,
            bodyparts=["Head"],
            frame_count=10,
            display_name="Fish B",
        ),
    ]

    monkeypatch.setattr(
        "ui.components.pose.verify_pose_datasets_widget.list_pose_datasets",
        lambda *a, **k: entries,
    )


class _FakeSession:
    def __init__(self) -> None:
        self.pose_projects = {
            "default": {
                "videos": {
                    "vid_a": {"display_name": "Fish A"},
                    "vid_b": {"display_name": "Fish B"},
                }
            }
        }

    def getName(self) -> str:
        return "sess"

    def get_pose_video_ids(self) -> list[str]:
        return ["vid_a", "vid_b"]


def _child_for(parent: QTreeWidgetItem, source_key: str) -> QTreeWidgetItem:
    for i in range(parent.childCount()):
        child = parent.child(i)
        if child.data(0, Qt.UserRole + 1) == source_key:
            return child
    raise AssertionError(f"missing child {source_key}")


def test_verify_datasets_same_video_multi_select(qapp, tmp_path, monkeypatch):
    from ui.components.pose.verify_pose_datasets_widget import VerifyPoseDatasetsWidget

    _seed_entries(tmp_path, monkeypatch)
    w = VerifyPoseDatasetsWidget()
    w.load_session(_FakeSession(), "default")
    assert w.isVisible()
    assert w._tree.topLevelItemCount() == 2

    parent_a = w._tree.topLevelItem(0)
    parent_b = w._tree.topLevelItem(1)
    human_a = _child_for(parent_a, "human")
    ai_a = _child_for(parent_a, "ai")
    human_b = _child_for(parent_b, "human")

    human_a.setCheckState(0, Qt.Checked)
    ai_a.setCheckState(0, Qt.Checked)
    assert w._active_video_id == "vid_a"
    assert w._priority_source_keys() == ["human", "ai"]

    # Selecting another video clears the first.
    human_b.setCheckState(0, Qt.Checked)
    assert w._active_video_id == "vid_b"
    assert human_a.checkState(0) == Qt.Unchecked
    assert ai_a.checkState(0) == Qt.Unchecked
    assert w._priority_source_keys() == ["human"]

    w.close()
