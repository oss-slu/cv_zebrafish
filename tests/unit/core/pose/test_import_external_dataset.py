"""Tests for external DLC import and layered merge."""

from pathlib import Path

from core.pose.dataset.dataset_catalog import list_pose_datasets
from core.pose.dataset.dataset_merge import combine_video_datasets, merge_label_datasets
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_external_dataset import IMPORT_META_FILENAME, import_external_dlc_csv
from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import default_lab_schema


def _write_video_meta(video_dir: Path, frame_count: int = 10) -> None:
    video_dir.mkdir(parents=True, exist_ok=True)
    (video_dir / "meta.json").write_text(
        f'{{"frame_count": {frame_count}}}',
        encoding="utf-8",
    )


def _write_dlc_csv(path: Path, points: dict[int, tuple[float, float]]) -> None:
    ds = LabelDataset(schema=default_lab_schema())
    for fi, (x, y) in points.items():
        ds.set_point(fi, "Head", x, y)
    export_dlc_csv(ds, max(points) + 1, path)


def test_import_external_dlc_csv(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    video = "vid1"

    def fake_pose_video_dir(s, p, v):
        return tmp_path / "videos" / v

    def fake_external_dir(s, p, v):
        return tmp_path / "external_labelled" / v

    monkeypatch.setattr(
        "core.pose.dataset.import_external_dataset.pose_video_dir",
        fake_pose_video_dir,
    )
    monkeypatch.setattr(
        "core.pose.dataset.import_external_dataset.external_labelled_dir",
        fake_external_dir,
    )

    _write_video_meta(tmp_path / "videos" / video)
    src = tmp_path / "outside.csv"
    _write_dlc_csv(src, {0: (1.0, 2.0), 2: (3.0, 4.0)})

    dest = import_external_dlc_csv(session, project, video, src)
    assert dest.is_file()
    meta = tmp_path / "external_labelled" / video / IMPORT_META_FILENAME
    assert meta.is_file()
    assert (tmp_path / "external_labelled" / video / "original_outside.csv").is_file()


def test_merge_three_layers_human_wins():
    external = LabelDataset(schema=default_lab_schema())
    external.set_point(0, "Head", 9.0, 9.0)
    external.set_point(1, "Head", 8.0, 8.0)

    ai = LabelDataset(schema=default_lab_schema())
    ai.set_point(0, "Head", 5.0, 5.0)
    ai.set_point(1, "Head", 6.0, 6.0)

    human = LabelDataset(schema=default_lab_schema())
    human.set_point(0, "Head", 1.0, 2.0)

    merged = merge_label_datasets(external, ai, human)
    assert merged.get_point(0, "Head") == (1.0, 2.0)
    assert merged.get_point(1, "Head") == (6.0, 6.0)


def test_combine_with_external_only(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    video = "vid1"

    def fake_pose_video_dir(s, p, v):
        return tmp_path / "videos" / v

    def fake_external_dir(s, p, v):
        return tmp_path / "external_labelled" / v

    def fake_final_dir(s, p, v):
        return tmp_path / "final_labelled" / v

    def fake_human_dir(s, p, v):
        return tmp_path / "human_labelled" / v

    def fake_ai_dir(s, p, v):
        return tmp_path / "ai_labelled" / v

    monkeypatch.setattr("core.pose.dataset.dataset_merge.pose_video_dir", fake_pose_video_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_merge.external_labelled_dir", fake_external_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_merge.final_labelled_dir", fake_final_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_merge.human_labelled_dir", fake_human_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_merge.ai_labelled_dir", fake_ai_dir)

    _write_video_meta(tmp_path / "videos" / video)
    ext_dir = tmp_path / "external_labelled" / video
    ext_dir.mkdir(parents=True)
    _write_dlc_csv(ext_dir / "tracking.csv", {0: (1.0, 2.0)})

    csv_path, prov_path = combine_video_datasets(
        session,
        project,
        video,
        use_human=False,
        use_ai=False,
        use_external=True,
    )
    assert csv_path.is_file()
    assert prov_path.is_file()


def test_catalog_lists_external(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    video = "vid1"

    def fake_pose_project_dir(s, p):
        return tmp_path / "project"

    def fake_pose_video_dir(s, p, v):
        return tmp_path / "project" / "videos" / v

    def fake_human_dir(s, p, v):
        return tmp_path / "project" / "human_labelled" / v

    def fake_ai_dir(s, p, v):
        return tmp_path / "project" / "ai_labelled" / v

    def fake_external_dir(s, p, v):
        return tmp_path / "project" / "external_labelled" / v

    def fake_final_dir(s, p, v):
        return tmp_path / "project" / "final_labelled" / v

    monkeypatch.setattr("core.pose.dataset.dataset_catalog.pose_project_dir", fake_pose_project_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_catalog.pose_video_dir", fake_pose_video_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_catalog.human_labelled_dir", fake_human_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_catalog.ai_labelled_dir", fake_ai_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_catalog.external_labelled_dir", fake_external_dir)
    monkeypatch.setattr("core.pose.dataset.dataset_catalog.final_labelled_dir", fake_final_dir)

    vdir = tmp_path / "project" / "videos" / video
    _write_video_meta(vdir)
    ext_dir = tmp_path / "project" / "external_labelled" / video
    ext_dir.mkdir(parents=True)
    _write_dlc_csv(ext_dir / "tracking.csv", {0: (1.0, 2.0)})

    entries = list_pose_datasets(session, project, {video: "Fish A"})
    sources = {e.source for e in entries}
    assert "external" in sources
