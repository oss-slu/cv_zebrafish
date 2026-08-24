"""Tests for saved DLC model runs."""

import json
from pathlib import Path

from core.pose.training.model_registry import (
    ModelRun,
    archive_completed_training,
    create_branch_from_checkpoint,
    import_external_model_run,
    install_bundled_model_if_empty,
    is_checkpoint_at_training_tip,
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


def test_stage_snapshot_for_analyze_skips_when_already_best(tmp_path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "m" / "train"
    train_dir.mkdir(parents=True)
    best = train_dir / "snapshot-best.pt"
    best.write_bytes(b"already-best")
    dest = stage_snapshot_for_analyze(work_dir, best)
    assert dest == best
    assert dest.read_bytes() == b"already-best"


def test_create_branch_from_checkpoint(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "m" / "train"
    train_dir.mkdir(parents=True)
    ckpt = train_dir / "snapshot-5.pt"
    ckpt.write_bytes(b"ckpt")
    (work_dir / "config.yaml").write_text("project_path: .\n", encoding="utf-8")
    job = {
        "session_name": session,
        "project_id": project,
        "work_dir": str(work_dir),
        "config_path": str(work_dir / "config.yaml"),
    }
    (work_dir / "train_job.json").write_text(json.dumps(job), encoding="utf-8")

    monkeypatch.setattr(
        "core.pose.training.model_registry.pose_models_dir",
        lambda s, p: tmp_path / "models",
    )

    new_work, new_job = create_branch_from_checkpoint(
        session_name=session,
        project_id=project,
        source_work_dir=work_dir,
        checkpoint_path=ckpt,
        job=job,
        parent_checkpoint_key=str(ckpt.resolve()),
    )
    assert new_work.is_dir()
    assert new_job.is_file()
    assert (new_work / "config.yaml").is_file()
    seeded = list(new_work.glob("**/train/snapshot*.pt"))
    assert seeded
    assert not (work_dir / "dlc-models-pytorch").exists() or (
        work_dir / "dlc-models-pytorch"
    ).exists()


def test_is_checkpoint_at_training_tip(tmp_path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "m" / "train"
    train_dir.mkdir(parents=True)
    snap5 = train_dir / "snapshot-5.pt"
    snap10 = train_dir / "snapshot-10.pt"
    snap5.write_bytes(b"5")
    snap10.write_bytes(b"10")
    assert not is_checkpoint_at_training_tip(work_dir, str(snap5.resolve()))
    assert is_checkpoint_at_training_tip(work_dir, str(snap10.resolve()))


def test_import_external_model_run(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    src = tmp_path / "external"
    src.mkdir()
    (src / "weights.pt").write_bytes(b"w")

    monkeypatch.setattr(
        "core.pose.training.model_registry.pose_models_dir",
        lambda s, p: tmp_path / "models",
    )

    record = import_external_model_run(session, project, src, label="Test import")
    assert record.imported
    assert Path(record.snapshot_path).is_file()
    runs = list_model_runs(session, project)
    assert len(runs) == 1
    assert runs[0].label == "Test import"


def test_install_bundled_model_if_empty(tmp_path, monkeypatch):
    session = "sess"
    project = "default"
    models_dir = tmp_path / "models"
    bundled = tmp_path / "bundled"
    drop = bundled / "seed-model"
    drop.mkdir(parents=True)
    (drop / "weights.pt").write_bytes(b"seed")

    monkeypatch.setattr(
        "core.pose.training.model_registry.pose_models_dir",
        lambda s, p: models_dir,
    )
    monkeypatch.setattr(
        "core.pose.training.model_registry.bundled_models_dir",
        lambda: bundled,
    )

    record = install_bundled_model_if_empty(session, project)
    assert record is not None
    assert list_model_runs(session, project)
    assert install_bundled_model_if_empty(session, project) is None

