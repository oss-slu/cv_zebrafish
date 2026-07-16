"""Tests for DLC training bundle preparation."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from core.pose.detection.arena import ArenaConfig, save_arena
from core.pose.detection.blob import BlobParams, save_blob_params
from core.pose.training.dlc_bundle import (
    MIN_LABELED_FRAMES,
    collected_data_filename,
    gather_project_label_stats,
    prepare_training_bundle,
)
from core.pose.labeling.labels_store import LabelDataset, save_labels
from core.pose.labeling.schema import default_lab_schema


def _write_synthetic_video(path: Path, n_frames: int = 5) -> None:
    h, w = 120, 160
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, 10.0, (w, h))
    for i in range(n_frames):
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        cv2.circle(frame, (80 + i, 60), 12, (220, 220, 220), -1)
        writer.write(frame)
    writer.release()


def _seed_video_bundle(
    base: Path, session: str, project: str, vid: str, n_labels: int, *, n_frames: int | None = None
) -> None:
    from app_platform.paths import human_labelled_dir, pose_video_dir

    frame_count = max(n_labels, n_frames or 5)
    vdir = pose_video_dir(session, project, vid)
    vdir.mkdir(parents=True, exist_ok=True)
    video_path = vdir / "source.mp4"
    _write_synthetic_video(video_path, n_frames=frame_count)
    save_arena(vdir / "arena.json", ArenaConfig(shape="circle", size=0.8))
    save_blob_params(vdir / "blob_params.json", BlobParams(brightness_min=10, brightness_max=255))
    meta = {
        "fps": 10.0,
        "frame_count": frame_count,
        "width": 160,
        "height": 120,
        "source_policy": "copy",
    }
    (vdir / "meta.json").write_text(__import__("json").dumps(meta), encoding="utf-8")

    label_dir = human_labelled_dir(session, project, vid)
    ds = LabelDataset(schema=default_lab_schema())
    for i in range(n_labels):
        ds.set_point(i, "Head", 80.0 + (i % 10), 60.0)
    save_labels(label_dir, ds)


def test_gather_project_label_stats(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.pose.training.dlc_bundle.human_labelled_dir",
        lambda s, p, v: tmp_path / "human" / v,
    )
    for i in range(3):
        d = tmp_path / "human" / f"v{i}"
        ds = LabelDataset(schema=default_lab_schema())
        ds.set_point(0, "Head", 1.0, 2.0)
        save_labels(d, ds)
    stats = gather_project_label_stats("sess", "default", ["v0", "v1", "v2"])
    assert stats.total_labeled_frames == 3
    assert stats.bodyparts == default_lab_schema().bodyparts


def test_prepare_training_bundle_requires_minimum(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app_platform.paths.sessions_dir", lambda: tmp_path / "data" / "sessions")
    _seed_video_bundle(tmp_path, "sess", "default", "v0", 2)
    with pytest.raises(ValueError, match=str(MIN_LABELED_FRAMES)):
        prepare_training_bundle("sess", "default", ["v0"])


def test_prepare_training_bundle_writes_job(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("app_platform.paths.sessions_dir", lambda: tmp_path / "data" / "sessions")
    n = MIN_LABELED_FRAMES
    _seed_video_bundle(tmp_path, "sess", "default", "v0", n)
    job_path, stats = prepare_training_bundle("sess", "default", ["v0"])
    assert job_path.is_file()
    assert stats.total_labeled_frames == n
    work = job_path.parent
    assert (work / "config.yaml").is_file()
    assert (work / "labeled-data" / "source" / collected_data_filename()).is_file()


def test_training_bundle_is_stale_detects_label_changes(tmp_path: Path, monkeypatch):
    from core.pose.training.dlc_bundle import training_bundle_is_stale

    monkeypatch.setattr("app_platform.paths.sessions_dir", lambda: tmp_path / "data" / "sessions")
    n = MIN_LABELED_FRAMES
    _seed_video_bundle(tmp_path, "sess", "default", "v0", n)
    job_path, stats = prepare_training_bundle("sess", "default", ["v0"])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert not training_bundle_is_stale("sess", "default", ["v0"], job)

    from app_platform.paths import human_labelled_dir
    from core.pose.labeling.labels_store import LabelDataset, save_labels

    ds = LabelDataset(schema=default_lab_schema())
    ds.set_point(0, "Head", 1.0, 2.0)
    save_labels(human_labelled_dir("sess", "default", "v0"), ds)
    assert training_bundle_is_stale("sess", "default", ["v0"], job)


def test_find_train_job_path(tmp_path: Path, monkeypatch):
    from core.pose.training.dlc_bundle import find_train_job_path

    monkeypatch.setattr("app_platform.paths.sessions_dir", lambda: tmp_path / "data" / "sessions")
    assert find_train_job_path("sess", "default") is None
    _seed_video_bundle(tmp_path, "sess", "default", "v0", MIN_LABELED_FRAMES)
    prepare_training_bundle("sess", "default", ["v0"])
    assert find_train_job_path("sess", "default") is not None


def test_write_config_yaml_includes_iteration(tmp_path: Path, monkeypatch):
    from core.pose.training.dlc_bundle import CONFIG_FILENAME, _write_config_yaml

    monkeypatch.setattr("app_platform.paths.sessions_dir", lambda: tmp_path / "data" / "sessions")
    work = tmp_path / "work"
    work.mkdir()
    _write_config_yaml(
        work / CONFIG_FILENAME,
        project_path=work,
        bodyparts=["Head"],
        video_paths=["C:/videos/source.mp4"],
        scorer="pose_studio",
    )
    text = (work / CONFIG_FILENAME).read_text(encoding="utf-8")
    assert "iteration: 0" in text
    assert "TrainingFraction: [0.95]" in text
    assert "engine: pytorch" in text


def test_training_bundle_uses_square_crop_when_origin_off_frame():
    """Naive frame[y0:y1, x0:x1] is empty when square origin is negative."""
    from core.pose.detection.blob import BlobResult
    from core.pose.detection.crop import extract_square_crop

    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    frame[0:20, 0:20] = 200
    blob = BlobResult(
        mask=np.zeros((120, 160), dtype=bool),
        center_x=10.0,
        center_y=10.0,
        side=80,
        x0=-30,
        y0=-30,
        x1=50,
        y1=50,
        found=True,
    )
    naive = frame[blob.y0 : blob.y1, blob.x0 : blob.x1]
    assert naive.size == 0
    crop = extract_square_crop(frame, blob)
    assert crop.shape == (80, 80, 3)
    assert crop.size > 0
