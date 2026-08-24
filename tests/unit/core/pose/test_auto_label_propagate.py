"""Tests for forward auto-label propagation."""

from __future__ import annotations

import numpy as np

from core.pose.inference.auto_label_propagate import AutoLabelParams, propagate_auto_label
from core.pose.inference.dlc_heatmap_predictor import SyntheticHeatmapPredictor
from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams
from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import PoseSchema


def _synthetic_video(path, n_frames: int = 3) -> None:
    import cv2

    for i in range(n_frames):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        x0 = 50 + i * 3
        frame[50:70, x0 : x0 + 20] = 220
        cv2.imwrite(str(path / f"f{i:03d}.png"), frame)


def test_nearest_complete_seed_frame():
    from core.pose.inference.auto_label_propagate import (
        first_complete_seed_frame,
        nearest_complete_seed_frame,
    )

    ds = LabelDataset(schema=PoseSchema(bodyparts=["A", "B"], edges=[(0, 1)]))
    ds.set_point(0, "A", 1.0, 1.0)
    ds.set_point(10, "A", 2.0, 2.0)
    ds.set_point(10, "B", 3.0, 3.0)
    assert first_complete_seed_frame(ds) == 10
    assert nearest_complete_seed_frame(ds, 0) == 10
    assert nearest_complete_seed_frame(ds, 10) == 10


def test_propagate_forward_and_backward_from_seed(tmp_path):
    import cv2

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _synthetic_video(frames_dir, 5)
    video_path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    for i in range(5):
        img = cv2.imread(str(frames_dir / f"f{i:03d}.png"))
        writer.write(img)
    writer.release()

    ds = LabelDataset(schema=PoseSchema(bodyparts=["Head", "Tail"], edges=[(0, 1)]))
    ds.set_point(2, "Head", 60.0, 60.0)
    ds.set_point(2, "Tail", 75.0, 60.0)

    predictor = SyntheticHeatmapPredictor(noise_px=0.5)
    params = AutoLabelParams(seed_frame=2, search_radius_px=30.0, min_likelihood=0.1)
    out, report = propagate_auto_label(
        video_path=video_path,
        frame_count=5,
        arena=ArenaConfig(),
        blob_params=BlobParams(brightness_min=100),
        human_labels=ds,
        predictor=predictor,
        params=params,
    )
    assert out.get_point(2, "Head") is not None
    assert out.get_point(3, "Head") is not None
    assert out.get_point(1, "Head") is not None
    assert out.get_point(0, "Head") is not None
    assert report.frames_processed >= 5


def test_propagate_from_seed_frame(tmp_path):
    import cv2

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _synthetic_video(frames_dir, 3)
    # Build a tiny video from images
    video_path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    for i in range(3):
        img = cv2.imread(str(frames_dir / f"f{i:03d}.png"))
        writer.write(img)
    writer.release()

    ds = LabelDataset(schema=PoseSchema(bodyparts=["Head", "Tail"], edges=[(0, 1)]))
    ds.set_point(0, "Head", 60.0, 60.0)
    ds.set_point(0, "Tail", 75.0, 60.0)

    predictor = SyntheticHeatmapPredictor(noise_px=0.5)
    params = AutoLabelParams(seed_frame=0, search_radius_px=30.0, min_likelihood=0.1)
    out, report = propagate_auto_label(
        video_path=video_path,
        frame_count=3,
        arena=ArenaConfig(),
        blob_params=BlobParams(brightness_min=100),
        human_labels=ds,
        predictor=predictor,
        params=params,
    )
    assert out.get_point(0, "Head") is not None
    assert out.get_point(1, "Head") is not None
    assert report.frames_processed == 3


def test_propagate_aborts_early_on_all_zero_heatmaps(tmp_path):
    import cv2

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _synthetic_video(frames_dir, 5)
    video_path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    for i in range(5):
        img = cv2.imread(str(frames_dir / f"f{i:03d}.png"))
        writer.write(img)
    writer.release()

    class _ZeroPredictor:
        calls = 0

        def predict_crop(self, crop_bgr, bodyparts):
            self.calls += 1
            h, w = crop_bgr.shape[:2]
            return {bp: np.zeros((h, w), dtype=np.float64) for bp in bodyparts}

    ds = LabelDataset(schema=PoseSchema(bodyparts=["Head", "Tail"], edges=[(0, 1)]))
    ds.set_point(0, "Head", 60.0, 60.0)
    ds.set_point(0, "Tail", 75.0, 60.0)

    predictor = _ZeroPredictor()
    params = AutoLabelParams(seed_frame=0, search_radius_px=30.0, min_likelihood=0.1)
    import pytest

    with pytest.raises(RuntimeError, match="aborted at frame 0"):
        propagate_auto_label(
            video_path=video_path,
            frame_count=5,
            arena=ArenaConfig(),
            blob_params=BlobParams(brightness_min=100),
            human_labels=ds,
            predictor=predictor,
            params=params,
        )
    # First inference attempt is the human-complete seed frame (heatmap-only path).
    assert predictor.calls == 1


def test_human_complete_frames_save_heatmaps(tmp_path):
    import cv2

    from core.pose.inference.heatmap_store import heatmap_frame_path

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _synthetic_video(frames_dir, 3)
    video_path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    for i in range(3):
        img = cv2.imread(str(frames_dir / f"f{i:03d}.png"))
        writer.write(img)
    writer.release()

    ds = LabelDataset(schema=PoseSchema(bodyparts=["Head", "Tail"], edges=[(0, 1)]))
    ds.set_point(0, "Head", 60.0, 60.0)
    ds.set_point(0, "Tail", 75.0, 60.0)
    ds.set_point(2, "Head", 62.0, 60.0)
    ds.set_point(2, "Tail", 77.0, 60.0)

    hm_dir = tmp_path / "heatmaps"
    predictor = SyntheticHeatmapPredictor(noise_px=0.5)
    params = AutoLabelParams(seed_frame=0, search_radius_px=30.0, min_likelihood=0.1)
    out, report = propagate_auto_label(
        video_path=video_path,
        frame_count=3,
        arena=ArenaConfig(),
        blob_params=BlobParams(brightness_min=100),
        human_labels=ds,
        predictor=predictor,
        params=params,
        heatmap_out_dir=hm_dir,
    )
    assert out.get_point(0, "Head") == (60.0, 60.0)
    assert out.get_point(2, "Head") == (62.0, 60.0)
    assert heatmap_frame_path(hm_dir, 0).is_file()
    assert heatmap_frame_path(hm_dir, 1).is_file()
    assert heatmap_frame_path(hm_dir, 2).is_file()
    assert report.heatmaps_saved == 3


def test_finish_incomplete_archive_uses_saved_and_infers_missing(tmp_path):
    import cv2

    from core.pose.inference.heatmap_store import save_frame_heatmaps

    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    _synthetic_video(frames_dir, 3)
    video_path = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (160, 120),
    )
    for i in range(3):
        img = cv2.imread(str(frames_dir / f"f{i:03d}.png"))
        writer.write(img)
    writer.release()

    archive = tmp_path / "heatmaps"
    archive.mkdir()
    tiny = np.zeros((10, 10), dtype=np.float32)
    tiny[5, 5] = 1.0
    save_frame_heatmaps(archive, 0, {"Head": tiny, "Tail": tiny}, crop_h=10, crop_w=10)

    ds = LabelDataset(schema=PoseSchema(bodyparts=["Head", "Tail"], edges=[(0, 1)]))
    ds.set_point(0, "Head", 60.0, 60.0)
    ds.set_point(0, "Tail", 75.0, 60.0)

    predictor = SyntheticHeatmapPredictor(noise_px=0.5)
    params = AutoLabelParams(
        seed_frame=0,
        search_radius_px=30.0,
        min_likelihood=0.1,
        finish_incomplete_archive=True,
        heatmap_source_dir=str(archive),
    )
    out, report = propagate_auto_label(
        video_path=video_path,
        frame_count=3,
        arena=ArenaConfig(),
        blob_params=BlobParams(brightness_min=100),
        human_labels=ds,
        predictor=predictor,
        params=params,
        heatmap_out_dir=archive,
    )
    assert out.get_point(1, "Head") is not None
    assert out.get_point(2, "Head") is not None
    assert report.heatmaps_saved == 2
    assert (archive / "frame000001.npz").is_file()
    assert (archive / "frame000002.npz").is_file()
