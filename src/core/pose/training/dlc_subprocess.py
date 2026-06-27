"""Helpers for Pose Studio DLC subprocess (paths, JSON-line protocol)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from app_platform.paths import project_root

RUN_DLC_SCRIPT = "scripts/run_dlc_step.py"
STOP_FLAG_NAME = "stop_after_epoch.flag"


def run_dlc_script_path() -> Path:
    return project_root() / RUN_DLC_SCRIPT


def stop_flag_path(work_dir: Path) -> Path:
    return work_dir / STOP_FLAG_NAME


def clear_stop_flag(work_dir: Path) -> None:
    p = stop_flag_path(work_dir)
    if p.is_file():
        p.unlink(missing_ok=True)


def request_stop_after_epoch(work_dir: Path) -> None:
    stop_flag_path(work_dir).write_text("1", encoding="utf-8")


def stop_requested(work_dir: Path) -> bool:
    return stop_flag_path(work_dir).is_file()


def parse_progress_line(line: str) -> dict[str, Any] | None:
    """Parse one JSON-lines progress object from subprocess stdout."""
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def iter_progress_lines(stream) -> Iterator[dict[str, Any]]:
    for line in stream:
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        obj = parse_progress_line(line)
        if obj is not None:
            yield obj


def load_train_job(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
