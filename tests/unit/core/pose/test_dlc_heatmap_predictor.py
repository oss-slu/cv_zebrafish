"""Tests for DLC heatmap predictor config resolution and pose parsing."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from core.pose.inference.dlc_heatmap_predictor import (
    DlcCropHeatmapPredictor,
    _find_pytorch_config,
    _heatmaps_are_usable,
    parse_runner_prediction,
    poses_array_to_coords,
)


def test_find_pytorch_config_prefers_snapshot_train_dir(tmp_path: Path) -> None:
    work_dir = tmp_path / "dlc_work"
    train_dir = (
        work_dir
        / "dlc-models-pytorch"
        / "iteration-0"
        / "model-shuffle1"
        / "train"
    )
    train_dir.mkdir(parents=True)
    cfg = train_dir / "pytorch_config.yaml"
    cfg.write_text("method: bottom_up\n", encoding="utf-8")
    snapshot = train_dir / "snapshot-best-030.pt"
    snapshot.write_bytes(b"fake")

    other_train = work_dir / "dlc-models-pytorch" / "iteration-0" / "old" / "train"
    other_train.mkdir(parents=True)
    (other_train / "pytorch_config.yaml").write_text("method: old\n", encoding="utf-8")

    found = _find_pytorch_config(work_dir, snapshot)
    assert found == cfg


def test_find_pytorch_config_falls_back_to_newest(tmp_path: Path) -> None:
    work_dir = tmp_path / "dlc_work"
    older = work_dir / "dlc-models-pytorch" / "iteration-0" / "a" / "train"
    newer = work_dir / "dlc-models-pytorch" / "iteration-0" / "b" / "train"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    old_cfg = older / "pytorch_config.yaml"
    new_cfg = newer / "pytorch_config.yaml"
    old_cfg.write_text("method: bottom_up\n", encoding="utf-8")
    new_cfg.write_text("method: bottom_up\n", encoding="utf-8")
    import os
    import time

    os.utime(old_cfg, (time.time() - 100, time.time() - 100))
    os.utime(new_cfg, None)

    found = _find_pytorch_config(work_dir, None)
    assert found == new_cfg


def test_poses_array_to_coords_animals_kpts() -> None:
    poses = np.array(
        [
            [
                [10.0, 20.0, 0.9],
                [30.0, 40.0, 0.1],
                [50.0, 60.0, 0.8],
            ]
        ]
    )
    coords = poses_array_to_coords(poses, ["Head", "BF", "T1"], min_likelihood=0.5)
    assert coords["Head"] == (10.0, 20.0)
    assert coords["BF"] is None
    assert coords["T1"] == (50.0, 60.0)


def test_parse_runner_prediction_nested_bodypart_poses() -> None:
    pred = {
        "bodypart": {
            "poses": np.array([[[1.0, 2.0, 0.95], [3.0, 4.0, 0.9]]]),
        }
    }
    coords = parse_runner_prediction(pred, ["Head", "BF"])
    assert coords["Head"] == (1.0, 2.0)
    assert coords["BF"] == (3.0, 4.0)


def test_parse_runner_prediction_legacy_name_keys() -> None:
    pred = {"Head": [5.0, 6.0], "BF": [7.0, 8.0]}
    coords = parse_runner_prediction(pred, ["Head", "BF"])
    assert coords["Head"] == (5.0, 6.0)
    assert coords["BF"] == (7.0, 8.0)


def test_predict_crop_prefers_parsed_coords_over_zero_scoremaps() -> None:
    pred = object.__new__(DlcCropHeatmapPredictor)
    pred._bodyparts = ["Head", "BF"]
    pred._runner = object()

    def _zero_maps(_crop):
        return {
            "Head": np.zeros((8, 8), dtype=np.float32),
            "BF": np.zeros((8, 8), dtype=np.float32),
        }

    def _coords(_crop, bodyparts):
        return {bp: (3.0, 4.0) for bp in bodyparts}

    pred._scoremaps_from_runner = _zero_maps  # type: ignore[method-assign]
    pred._coords_from_runner = _coords  # type: ignore[method-assign]

    crop = np.zeros((16, 16, 3), dtype=np.uint8)
    maps = pred.predict_crop(crop, ["Head", "BF"])
    assert _heatmaps_are_usable(maps)
    assert float(maps["Head"].max()) > 0.5


def test_predict_crop_returns_zeros_when_both_paths_fail() -> None:
    pred = object.__new__(DlcCropHeatmapPredictor)
    pred._bodyparts = ["Head"]
    pred._runner = object()
    pred._scoremaps_from_runner = lambda _c: None  # type: ignore[method-assign]
    pred._coords_from_runner = lambda _c, bps: {bp: None for bp in bps}  # type: ignore[method-assign]

    crop = np.zeros((8, 8, 3), dtype=np.uint8)
    maps = pred.predict_crop(crop, ["Head"])
    assert not _heatmaps_are_usable(maps)
