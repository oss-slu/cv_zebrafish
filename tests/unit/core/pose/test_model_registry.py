"""Tests for saved DLC model runs."""

from pathlib import Path

from core.pose.training.model_registry import (
    ModelRun,
    archive_completed_training,
    list_analyze_checkpoints,
    list_model_runs,
    pick_default_checkpoint,
    stage_snapshot_for_analyze,
)


def test_archive_completed_training(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "model-trainset95shuffle1" / "train"
    train_dir.mkdir(parents=True)
    snapshot = train_dir / "snapshot-3.pt"
    snapshot.write_bytes(b"fake-weights")

    def fake_runs_root(s, p):
        return tmp_path / "models" / "runs"

    monkeypatch.setattr("core.pose.training.model_registry.runs_root", fake_runs_root)
    monkeypatch.setattr(
        "core.pose.training.model_registry.pose_models_dir",
        lambda s, p: tmp_path / "models",
    )

    job = {
        "session_name": session,
        "project_id": project,
        "work_dir": str(work_dir),
        "config_path": str(work_dir / "config.yaml"),
        "labeled_frame_count": 100,
    }
    record = archive_completed_training(job, epochs=10)
    assert record is not None
    assert Path(record.snapshot_path).is_file()
    runs = list_model_runs(session, project)
    assert len(runs) == 1
    assert runs[0].epochs == 10


def test_list_analyze_checkpoints(tmp_path: Path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "m" / "train"
    train_dir.mkdir(parents=True)
    (train_dir / "snapshot-best.pt").write_bytes(b"b")
    (train_dir / "snapshot-5.pt").write_bytes(b"5")
    (train_dir / "snapshot-10.pt").write_bytes(b"10")
    options = list_analyze_checkpoints(
        work_dir,
        loss_by_epoch={5: 0.05, 10: 0.02},
    )
    assert len(options) == 3
    assert options[0].is_best
    assert options[1].epoch == 5
    assert "0.0500" in options[1].label
    assert options[2].epoch == 10


def test_pick_default_checkpoint_prefers_best(tmp_path: Path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "m" / "train"
    train_dir.mkdir(parents=True)
    (train_dir / "snapshot-best.pt").write_bytes(b"b")
    (train_dir / "snapshot-5.pt").write_bytes(b"5")
    options = list_analyze_checkpoints(work_dir)
    default = pick_default_checkpoint(options)
    assert default is not None
    assert default.is_best


def test_stage_snapshot_for_analyze(tmp_path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "m" / "train"
    train_dir.mkdir(parents=True)
    src = tmp_path / "weights.pt"
    src.write_bytes(b"w")
    dest = stage_snapshot_for_analyze(work_dir, src)
    assert dest.name == "snapshot-best.pt"
    assert dest.is_file()
