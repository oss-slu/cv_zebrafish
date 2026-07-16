"""Tests for DLC analyze → ai_labelled import."""

from pathlib import Path

from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import default_lab_schema
from core.pose.training.dlc_analyze_import import (
    find_dlc_prediction_csv,
    import_dlc_analyze_outputs_to_ai_labelled,
)


def _write_dlc_csv(path: Path, points: dict[int, tuple[float, float]]) -> None:
    ds = LabelDataset(schema=default_lab_schema())
    for fi, (x, y) in points.items():
        ds.set_point(fi, "Head", x, y)
    export_dlc_csv(ds, max(points) + 1, path)


def test_find_dlc_prediction_csv(tmp_path: Path):
    video = tmp_path / "source.mp4"
    video.write_bytes(b"")
    pred = tmp_path / "sourceDLC_resnet50_shuffle1.csv"
    _write_dlc_csv(pred, {0: (10.0, 20.0)})
    assert find_dlc_prediction_csv(video) == pred


def test_import_dlc_analyze_outputs_to_ai_labelled(tmp_path: Path, monkeypatch):
    session = "Session2_3"
    project = "default"
    video_id = "1_mp4"

    video_dir = tmp_path / "videos" / video_id
    video_dir.mkdir(parents=True)
    video = video_dir / "source.mp4"
    video.write_bytes(b"")
    (video_dir / "meta.json").write_text('{"frame_count": 5}', encoding="utf-8")
    pred = video_dir / "sourceDLC_test.csv"
    _write_dlc_csv(pred, {0: (1.0, 2.0), 2: (3.0, 4.0)})

    def fake_pose_video_dir(s, p, v):
        return tmp_path / "videos" / v

    def fake_ai_dir(s, p, v):
        return tmp_path / "ai_labelled" / v

    monkeypatch.setattr(
        "core.pose.training.dlc_analyze_import.pose_video_dir",
        fake_pose_video_dir,
    )
    monkeypatch.setattr(
        "core.pose.training.dlc_analyze_import.ai_labelled_dir",
        fake_ai_dir,
    )

    job = {
        "session_name": session,
        "project_id": project,
        "scorer": "pose_studio",
        "video_ids": [video_id],
        "video_sources": [str(video)],
    }
    written = import_dlc_analyze_outputs_to_ai_labelled(job)
    assert len(written) == 1
    assert written[0].name == "tracking.csv"
    assert written[0].is_file()
