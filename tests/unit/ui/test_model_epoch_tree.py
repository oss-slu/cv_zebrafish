"""Smoke tests for Model/Epoch tree picker."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtWidgets import QApplication

from core.pose.training.model_registry import AnalyzeCheckpoint, ModelRun
from ui.components.pose.model_epoch_tree import (
    ModelEpochTree,
    build_model_tree_nodes,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_model_epoch_tree_selection(qapp, tmp_path: Path):
    weights = tmp_path / "weights.pt"
    weights.write_bytes(b"w")
    run = ModelRun(
        run_id="20260716-120000",
        label="Train 50 frames",
        created_at="2026-07-16T12:00:00+00:00",
        snapshot_path=str(weights),
        dlc_train_dir=str(tmp_path),
        work_dir=str(tmp_path),
        config_path="",
        epochs=10,
        labeled_frames=50,
        snapshot_name="weights.pt",
    )
    ckpts = [
        AnalyzeCheckpoint(
            key=str(tmp_path / "snapshot-best.pt"),
            label="Best (validation mAP)",
            path=tmp_path / "snapshot-best.pt",
            epoch=None,
            is_best=True,
        ),
        AnalyzeCheckpoint(
            key=str(tmp_path / "snapshot-5.pt"),
            label="Epoch 5",
            path=tmp_path / "snapshot-5.pt",
            epoch=5,
            is_best=False,
        ),
    ]
    nodes = build_model_tree_nodes(
        runs=[run],
        current_label="Current training",
        current_checkpoints=ckpts,
        current_work_dir=str(tmp_path),
        branch_checkpoints={},
    )
    tree = ModelEpochTree()
    tree.set_tree(nodes=nodes)
    assert tree.tree.topLevelItemCount() == 2
    sel = tree.selection()
    assert sel.is_best or sel.checkpoint_key
    tree.clear_selection(label="(new model)")
    assert tree.selected_label() == "(new model)"
    tree.close()


def test_build_model_tree_nested_branch(qapp, tmp_path: Path):
    parent_weights = tmp_path / "parent.pt"
    parent_weights.write_bytes(b"p")
    child_weights = tmp_path / "child.pt"
    child_weights.write_bytes(b"c")
    parent = ModelRun(
        run_id="parent",
        label="Parent run",
        created_at="2026-07-16T12:00:00+00:00",
        snapshot_path=str(parent_weights),
        dlc_train_dir=str(tmp_path),
        work_dir=str(tmp_path),
        config_path="",
        epochs=10,
        snapshot_name="parent.pt",
    )
    child = ModelRun(
        run_id="child",
        label="Child branch",
        created_at="2026-07-16T13:00:00+00:00",
        snapshot_path=str(child_weights),
        dlc_train_dir=str(tmp_path),
        work_dir=str(tmp_path / "branch"),
        config_path="",
        epochs=5,
        snapshot_name="child.pt",
        parent_run_id="parent",
        parent_checkpoint_key=str(parent_weights.resolve()),
    )
    nodes = build_model_tree_nodes(
        runs=[parent, child],
        current_label="Current training",
        current_checkpoints=[],
        current_work_dir=None,
        branch_checkpoints={},
    )
    assert len(nodes) == 1
    assert any(c.run_id == "child" for c in nodes[0].children[0].children)
