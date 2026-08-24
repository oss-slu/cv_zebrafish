"""Tests for DLC heatmap predictor config resolution and pose parsing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.pose.inference.dlc_heatmap_predictor import (
    CropHeatmapResult,
    DlcCropHeatmapPredictor,
    RunnerScoremaps,
    _find_pytorch_config,
    _heatmaps_are_usable,
    _peak_locref_at_argmax,
    gaussian_heatmaps_from_coords,
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


def test_peak_locref_at_argmax_interleaved_channels() -> None:
    maps = np.zeros((2, 4, 4), dtype=np.float32)
    maps[0, 2, 2] = 0.9
    maps[1, 1, 1] = 0.8
    locref = np.zeros((4, 4, 4), dtype=np.float32)
    locref[0, 2, 2] = 0.25
    locref[1, 2, 2] = -0.5
    locref[2, 1, 1] = 1.0
    locref[3, 1, 1] = 2.0
    out = _peak_locref_at_argmax(maps, locref, ["Head", "BF"])
    assert out["Head"][0] == 0.25
    assert out["Head"][1] == -0.5
    assert out["BF"][0] == 1.0
    assert out["BF"][1] == 2.0


def test_predict_crop_prefers_raw_scoremaps_over_gaussians() -> None:
    pred = object.__new__(DlcCropHeatmapPredictor)
    pred._bodyparts = ["Head", "BF"]

    raw_head = np.zeros((8, 8), dtype=np.float32)
    raw_head[3, 4] = 0.42
    raw_bf = np.zeros((8, 8), dtype=np.float32)
    raw_bf[5, 2] = 0.37

    def _scoremaps(_crop):
        return RunnerScoremaps(
            scoremaps={"Head": raw_head, "BF": raw_bf},
            peak_locref={
                "Head": np.array([0.1, -0.2], dtype=np.float32),
                "BF": np.array([0.3, 0.4], dtype=np.float32),
            },
        )

    def _coords(_crop, bodyparts):
        return {bp: (3.0, 4.0) for bp in bodyparts}

    pred._scoremaps_from_runner = _scoremaps  # type: ignore[method-assign]
    pred._coords_from_runner = _coords  # type: ignore[method-assign]

    crop = np.zeros((16, 16, 3), dtype=np.uint8)
    result = pred.predict_crop(crop, ["Head", "BF"])
    assert isinstance(result, CropHeatmapResult)
    assert _heatmaps_are_usable(result.heatmaps)
    # Raw scoremap peak — not a tight σ=8 Gaussian (which would max near 1.0).
    assert float(result.heatmaps["Head"].max()) < 0.5
    assert float(result.heatmaps["Head"].max()) > 0.2
    gaussian_peak = float(
        gaussian_heatmaps_from_coords(16, 16, {"Head": (3.0, 4.0)})["Head"].max()
    )
    assert float(result.heatmaps["Head"].max()) < gaussian_peak
    assert result.peak_locref is not None
    assert result.peak_locref["Head"][0] == pytest.approx(0.1)


def test_predict_crop_falls_back_to_gaussians_when_scoremaps_zero() -> None:
    pred = object.__new__(DlcCropHeatmapPredictor)
    pred._bodyparts = ["Head", "BF"]

    def _zero_maps(_crop):
        return RunnerScoremaps(
            scoremaps={
                "Head": np.zeros((8, 8), dtype=np.float32),
                "BF": np.zeros((8, 8), dtype=np.float32),
            },
            peak_locref={},
        )

    def _coords(_crop, bodyparts):
        return {bp: (3.0, 4.0) for bp in bodyparts}

    pred._scoremaps_from_runner = _zero_maps  # type: ignore[method-assign]
    pred._coords_from_runner = _coords  # type: ignore[method-assign]

    crop = np.zeros((16, 16, 3), dtype=np.uint8)
    result = pred.predict_crop(crop, ["Head", "BF"])
    assert _heatmaps_are_usable(result.heatmaps)
    assert float(result.heatmaps["Head"].max()) > 0.5
    assert result.peak_locref is None
    gaussian_only = gaussian_heatmaps_from_coords(16, 16, {"Head": (3.0, 4.0), "BF": (3.0, 4.0)})
    assert float(result.heatmaps["Head"].max()) == pytest.approx(
        float(gaussian_only["Head"].max()), rel=1e-3
    )


def test_predict_crop_returns_zeros_when_both_paths_fail() -> None:
    pred = object.__new__(DlcCropHeatmapPredictor)
    pred._bodyparts = ["Head"]
    pred._scoremaps_from_runner = lambda _c: None  # type: ignore[method-assign]
    pred._coords_from_runner = lambda _c, bps: {bp: None for bp in bps}  # type: ignore[method-assign]

    crop = np.zeros((8, 8, 3), dtype=np.uint8)
    result = pred.predict_crop(crop, ["Head"])
    assert not _heatmaps_are_usable(result.heatmaps)
