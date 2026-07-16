"""Tests for DLC subprocess JSON-line protocol."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from app_platform.paths import project_root
from core.pose.training.dlc_subprocess import (
    has_training_dataset,
    load_learning_stats_breakdown,
    load_learning_stats_history,
    parse_learning_stats_csv,
    parse_progress_line,
    read_training_progress,
    run_dlc_script_path,
    should_skip_create_training_dataset,
    snapshot_keep_count,
    SNAPSHOT_SAVE_EPOCHS,
)


def test_parse_progress_line():
    assert parse_progress_line('{"type": "epoch", "epoch": 1}') == {"type": "epoch", "epoch": 1}
    assert parse_progress_line("") is None
    assert parse_progress_line("not json") is None


def test_parse_learning_stats_csv_pytorch_format(tmp_path: Path):
    stats = tmp_path / "learning_stats.csv"
    stats.write_text(
        "step,losses/eval.total_loss,losses/train.total_loss,mAP\n"
        "0,,,\n"
        "1,0.12,0.45,72.3\n",
        encoding="utf-8",
    )
    parsed = parse_learning_stats_csv(stats)
    assert parsed == (1, 0.45)


def test_parse_learning_stats_csv_dlc3_pytorch_bodypart_columns(tmp_path: Path):
    """Regression: plot total train loss, not heatmap-only."""
    stats = tmp_path / "learning_stats.csv"
    stats.write_text(
        "step,losses/train.bodypart_heatmap,losses/train.bodypart_locref,"
        "losses/train.bodypart_total_loss,losses/train.total_loss\n"
        "1,0.0019977991469204426,0.563495397567749,0.015086282975971699,0.015086282975971699\n"
        "6,0.0006328304880298674,0.17938989400863647,0.004801162984222174,0.004801162984222174\n",
        encoding="utf-8",
    )
    assert parse_learning_stats_csv(stats) == (6, 0.004801162984222174)
    assert load_learning_stats_history(stats) == [
        (1, 0.015086282975971699),
        (6, 0.004801162984222174),
    ]
    breakdown = load_learning_stats_breakdown(stats)
    assert breakdown[-1].epoch == 6
    assert breakdown[-1].total_loss == 0.004801162984222174
    assert breakdown[-1].heatmap_loss == 0.0006328304880298674
    assert breakdown[-1].locref_loss == 0.17938989400863647


def test_load_learning_stats_history(tmp_path: Path):
    stats = tmp_path / "learning_stats.csv"
    stats.write_text(
        "step,losses/eval.total_loss,losses/train.total_loss,mAP\n"
        "0,,,\n"
        "1,0.12,0.45,72.3\n"
        "2,0.10,0.30,75.0\n"
        "3,0.08,0.22,78.1\n",
        encoding="utf-8",
    )
    from core.pose.training.dlc_subprocess import (
        load_learning_stats_history,
        load_training_loss_history,
        reset_training_progress,
    )

    assert load_learning_stats_history(stats) == [(1, 0.45), (2, 0.30), (3, 0.22)]

    work_dir = tmp_path / "dlc_work"
    models = work_dir / "dlc-models-pytorch" / "iteration-0" / "model"
    models.mkdir(parents=True)
    shutil.copy2(stats, models / "learning_stats.csv")
    (models / "train").mkdir()
    (models / "train" / "snapshot-5.pt").write_text("x", encoding="utf-8")

    assert reset_training_progress(work_dir) == 3
    assert not (work_dir / "dlc-models-pytorch").exists()
    assert load_training_loss_history(work_dir) == []


def test_snapshot_keep_count():
    assert SNAPSHOT_SAVE_EPOCHS == 5
    assert snapshot_keep_count(50) == 10
    assert snapshot_keep_count(47) == 10
    assert snapshot_keep_count(5) == 1
    assert snapshot_keep_count(1) == 1


def test_should_skip_create_training_dataset_when_resuming(tmp_path: Path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "dlc-models-pytorch" / "iteration-0" / "model" / "train"
    train_dir.mkdir(parents=True)
    (train_dir / "pytorch_config.yaml").write_text("engine: pytorch\n", encoding="utf-8")
    stats = train_dir.parent / "learning_stats.csv"
    stats.write_text(
        "step,losses/train.total_loss\n"
        "1,0.45\n"
        "10,0.12\n",
        encoding="utf-8",
    )
    assert has_training_dataset(work_dir)
    assert should_skip_create_training_dataset(work_dir)
    assert read_training_progress(work_dir) == (10, 0.12)


def test_should_not_skip_create_training_dataset_without_progress(tmp_path: Path):
    work_dir = tmp_path / "dlc_work"
    train_dir = work_dir / "training-datasets" / "iteration-0"
    train_dir.mkdir(parents=True)
    assert has_training_dataset(work_dir)
    assert not should_skip_create_training_dataset(work_dir)


def test_stop_dlc_subprocess_clears_stale_pid(tmp_path: Path):
    from core.pose.training.dlc_subprocess import (
        read_subprocess_pid,
        stop_dlc_subprocess,
        write_subprocess_pid,
    )

    work_dir = tmp_path / "dlc_work"
    work_dir.mkdir()
    write_subprocess_pid(work_dir, 999999)
    assert stop_dlc_subprocess(work_dir) is True
    assert read_subprocess_pid(work_dir) is None


def test_stop_dlc_subprocess_terminates_scanned_orphan(monkeypatch, tmp_path: Path):
    from core.pose.training import dlc_subprocess as mod

    work_dir = tmp_path / "dlc_work"
    work_dir.mkdir()
    killed: list[int] = []
    live = {4242}

    monkeypatch.setattr(mod, "find_run_dlc_step_pids", lambda *, work_dir=None: sorted(live))
    monkeypatch.setattr(mod, "_pid_is_running", lambda pid: pid in live)
    monkeypatch.setattr(
        mod,
        "terminate_subprocess_pid",
        lambda pid: (killed.append(pid), live.discard(pid)),
    )

    assert mod.stop_dlc_subprocess(work_dir) is True
    assert killed == [4242]


def test_remove_tree_resilient_deletes_nested(tmp_path: Path):
    from core.pose.training.dlc_subprocess import remove_tree_resilient

    root = tmp_path / "dlc-models-pytorch" / "iteration-0" / "model" / "train"
    root.mkdir(parents=True)
    (root / "train.txt").write_text("log", encoding="utf-8")
    remove_tree_resilient(tmp_path / "dlc-models-pytorch")
    assert not (tmp_path / "dlc-models-pytorch").exists()


def test_run_dlc_step_dry_run(tmp_path: Path):
    job = {
        "session_name": "test",
        "project_id": "default",
        "scorer": "pose_studio",
        "work_dir": str(tmp_path),
        "config_path": str(tmp_path / "config.yaml"),
        "video_ids": [],
        "video_sources": [],
    }
    job_path = tmp_path / "train_job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    script = run_dlc_script_path()
    assert script.is_file()
    proc = subprocess.run(
        [sys.executable, str(script), "--job", str(job_path), "--step", "dry_run", "--epochs", "3"],
        cwd=str(project_root()),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [json.loads(ln) for ln in proc.stdout.splitlines() if ln.strip()]
    types = [o.get("type") for o in lines]
    assert "epoch" in types
    assert "done" in types
