"""Tests for DLC subprocess JSON-line protocol."""

import json
import subprocess
import sys
from pathlib import Path

from app_platform.paths import project_root
from core.pose.training.dlc_subprocess import parse_progress_line, run_dlc_script_path


def test_parse_progress_line():
    assert parse_progress_line('{"type": "epoch", "epoch": 1}') == {"type": "epoch", "epoch": 1}
    assert parse_progress_line("") is None
    assert parse_progress_line("not json") is None


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
