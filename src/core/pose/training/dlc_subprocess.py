"""Helpers for Pose Studio DLC subprocess (paths, JSON-line protocol)."""

from __future__ import annotations

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from app_platform.paths import project_root

RUN_DLC_SCRIPT = "scripts/run_dlc_step.py"
STOP_FLAG_NAME = "stop_after_epoch.flag"
SUBPROCESS_PID_NAME = "dlc_subprocess.pid"
SNAPSHOT_SAVE_EPOCHS = 5
_RMTREE_ATTEMPTS = 8
_RMTREE_DELAY_S = 0.4


def run_dlc_script_path() -> Path:
    return project_root() / RUN_DLC_SCRIPT


def stop_flag_path(work_dir: Path) -> Path:
    return work_dir / STOP_FLAG_NAME


def subprocess_pid_path(work_dir: Path) -> Path:
    return work_dir / SUBPROCESS_PID_NAME


def write_subprocess_pid(work_dir: Path, pid: int) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    subprocess_pid_path(work_dir).write_text(str(int(pid)), encoding="utf-8")


def clear_subprocess_pid(work_dir: Path) -> None:
    subprocess_pid_path(work_dir).unlink(missing_ok=True)


def read_subprocess_pid(work_dir: Path) -> int | None:
    path = subprocess_pid_path(work_dir)
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(
                handle, ctypes.byref(exit_code)
            ):
                return False
            return int(exit_code.value) == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def terminate_subprocess_pid(pid: int) -> None:
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
        return
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def find_run_dlc_step_pids(*, work_dir: Path | None = None) -> list[int]:
    """Return PIDs of ``python.exe`` processes running ``run_dlc_step.py``."""
    work_key = str(work_dir.resolve()).lower() if work_dir is not None else None
    script_key = "run_dlc_step.py"
    pids: list[int] = []

    if sys.platform == "win32":
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "ForEach-Object { $_.ProcessId.ToString() + '|' + ($_.CommandLine ?? '') }",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            return pids
        for line in proc.stdout.splitlines():
            if script_key not in line:
                continue
            if work_key is not None and work_key not in line.lower():
                continue
            head = line.split("|", 1)[0].strip()
            try:
                pids.append(int(head))
            except ValueError:
                continue
        return sorted(set(pids))

    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,args="],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return pids
    for line in proc.stdout.splitlines():
        if script_key not in line:
            continue
        if work_key is not None and work_key not in line.lower():
            continue
        parts = line.strip().split(None, 1)
        if not parts:
            continue
        try:
            pids.append(int(parts[0]))
        except ValueError:
            continue
    return sorted(set(pids))


def stop_dlc_subprocess(work_dir: Path, *, wait_s: float = 12.0) -> bool:
    """
    Stop Pose Studio DLC subprocesses for ``work_dir``, if still running.

    Uses ``dlc_subprocess.pid`` when present and also scans for orphaned
    ``run_dlc_step.py`` processes (e.g. after closing the train dialog).
    """
    pids: set[int] = set()
    recorded = read_subprocess_pid(work_dir)
    if recorded is not None:
        pids.add(recorded)
    pids.update(find_run_dlc_step_pids(work_dir=work_dir))

    for pid in sorted(pids):
        if _pid_is_running(pid):
            terminate_subprocess_pid(pid)

    deadline = time.monotonic() + max(0.0, wait_s)
    while time.monotonic() < deadline:
        live = [pid for pid in pids if _pid_is_running(pid)]
        if not live:
            break
        live.extend(find_run_dlc_step_pids(work_dir=work_dir))
        pids.update(live)
        for pid in live:
            terminate_subprocess_pid(pid)
        time.sleep(0.25)

    clear_subprocess_pid(work_dir)
    remaining = find_run_dlc_step_pids(work_dir=work_dir)
    return not any(_pid_is_running(pid) for pid in remaining)


def _rmtree_onerror(func, path, _exc_info) -> None:
    if not os.path.exists(path):
        return
    os.chmod(path, 0o666)
    func(path)


def remove_tree_resilient(path: Path) -> None:
    """Delete a directory tree, retrying when Windows still has files open."""
    if not path.exists():
        return
    last_exc: OSError | None = None
    for attempt in range(_RMTREE_ATTEMPTS):
        try:
            shutil.rmtree(path, onerror=_rmtree_onerror)
            return
        except OSError as exc:
            last_exc = exc
            locked = getattr(exc, "winerror", None) in (32, 33) or exc.errno in (13, 16)
            if not locked or attempt + 1 >= _RMTREE_ATTEMPTS:
                raise
            time.sleep(_RMTREE_DELAY_S * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def clear_stop_flag(work_dir: Path) -> None:
    p = stop_flag_path(work_dir)
    if p.is_file():
        p.unlink(missing_ok=True)


def request_stop_after_epoch(work_dir: Path) -> None:
    stop_flag_path(work_dir).write_text("1", encoding="utf-8")


def stop_requested(work_dir: Path) -> bool:
    return stop_flag_path(work_dir).is_file()


def find_learning_stats_path(work_dir: Path) -> Path | None:
    pytorch = sorted(
        work_dir.glob("dlc-models-pytorch/**/learning_stats.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if pytorch:
        return pytorch[-1]
    legacy = work_dir / "dlc-models" / "iteration-0" / "learning_stats.csv"
    if legacy.is_file():
        return legacy
    return None


@dataclass(frozen=True)
class LearningStatsRow:
    epoch: int
    total_loss: float
    heatmap_loss: float | None = None
    locref_loss: float | None = None


def _learning_stats_loss_column(fieldnames: list[str] | None) -> str | None:
    if not fieldnames:
        return None
    names = list(fieldnames)
    for preferred in (
        "losses/train.total_loss",
        "losses/train.bodypart_total_loss",
    ):
        if preferred in names:
            return preferred
    for name in names:
        lower = name.lower()
        if name == "step":
            continue
        if "total_loss" in lower and "train" in lower:
            return name
    for name in names:
        lower = name.lower()
        if name == "step":
            continue
        metric = lower.rsplit("/", 1)[-1]
        if "train" in metric and "loss" in metric:
            return name
    for name in names:
        if name != "step" and "loss" in name.lower():
            return name
    if len(names) > 1:
        return names[1]
    return None


def _learning_stats_column(fieldnames: list[str], needle: str) -> str | None:
    for name in fieldnames:
        if needle in name.lower():
            return name
    return None


def _optional_metric(row: dict[str, str], column: str | None) -> float | None:
    if not column:
        return None
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def load_learning_stats_breakdown(path: Path) -> list[LearningStatsRow]:
    """Return per-epoch total, heatmap, and locref train loss from ``learning_stats.csv``."""
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames
            if not fieldnames or "step" not in fieldnames:
                return []
            names = list(fieldnames)
            total_col = _learning_stats_loss_column(names)
            heatmap_col = _learning_stats_column(names, "bodypart_heatmap")
            locref_col = _learning_stats_column(names, "bodypart_locref")
            rows: list[LearningStatsRow] = []
            for row in reader:
                raw_step = (row.get("step") or "").strip()
                raw_total = (row.get(total_col or "", "") or "").strip()
                if not raw_step or not raw_total:
                    continue
                step = int(float(raw_step))
                if step <= 0:
                    continue
                rows.append(
                    LearningStatsRow(
                        epoch=step,
                        total_loss=float(raw_total),
                        heatmap_loss=_optional_metric(row, heatmap_col),
                        locref_loss=_optional_metric(row, locref_col),
                    )
                )
            return rows
    except (OSError, ValueError, TypeError):
        return []


def load_learning_stats_history(path: Path) -> list[tuple[int, float]]:
    """Return all ``(epoch, total_loss)`` rows from a DLC ``learning_stats.csv``."""
    return [(row.epoch, row.total_loss) for row in load_learning_stats_breakdown(path)]


def parse_latest_learning_stats_row(path: Path) -> LearningStatsRow | None:
    rows = load_learning_stats_breakdown(path)
    if not rows:
        return None
    return rows[-1]


def load_training_loss_breakdown(work_dir: Path) -> list[LearningStatsRow]:
    path = find_learning_stats_path(work_dir)
    if path is None:
        return []
    return load_learning_stats_breakdown(path)


def load_training_loss_history(work_dir: Path) -> list[tuple[int, float]]:
    """Load persisted epoch loss history from ``dlc_work``, if any."""
    path = find_learning_stats_path(work_dir)
    if path is None:
        return []
    return load_learning_stats_history(path)


def snapshot_keep_count(total_epochs: int, *, save_every_n: int | None = None) -> int:
    """How many interval snapshots DLC should retain (every ``save_every_n`` epochs)."""
    interval = max(1, int(save_every_n if save_every_n is not None else SNAPSHOT_SAVE_EPOCHS))
    epochs = max(1, int(total_epochs))
    return max(1, (epochs + interval - 1) // interval)


def read_config_training_fraction(work_dir: Path) -> float | None:
    """Return ``TrainingFraction`` from ``config.yaml``, if present."""
    config_path = Path(work_dir) / "config.yaml"
    if not config_path.is_file():
        return None
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"TrainingFraction:\s*\[\s*([0-9]*\.?[0-9]+)\s*\]", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def has_shuffle_for_fraction(work_dir: Path, fraction: float, *, tol: float = 1e-4) -> bool:
    """True when metadata or a model folder exists for ``fraction`` (e.g. 0.8 → trainset80)."""
    pct = int(round(float(fraction) * 100))
    pattern = f"dlc-models-pytorch/**/*trainset{pct}shuffle*/train/pytorch_config.yaml"
    if list(Path(work_dir).glob(pattern)):
        return True
    for meta_path in Path(work_dir).glob("training-datasets/**/metadata.yaml"):
        try:
            text = meta_path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text) or {}
            shuffles = data.get("shuffles") or {}
            if isinstance(shuffles, dict):
                for entry in shuffles.values():
                    if not isinstance(entry, dict):
                        continue
                    frac = entry.get("train_fraction")
                    if frac is None:
                        continue
                    if abs(float(frac) - float(fraction)) <= tol:
                        return True
        except Exception:
            for match in re.finditer(
                r"train_fraction:\s*([0-9]*\.?[0-9]+)", text
            ):
                try:
                    if abs(float(match.group(1)) - float(fraction)) <= tol:
                        return True
                except ValueError:
                    continue
    return False


def has_training_dataset(work_dir: Path) -> bool:
    """True when DLC training artifacts exist under ``dlc_work``."""
    if list(work_dir.glob("dlc-models-pytorch/**/train/pytorch_config.yaml")):
        return True
    for meta_path in work_dir.glob("training-datasets/**/metadata.yaml"):
        try:
            text = meta_path.read_text(encoding="utf-8")
        except OSError:
            continue
        compact = "".join(text.split())
        if "shuffles:" in compact and "shuffles:{}" not in compact:
            return True
    return False


def should_skip_create_training_dataset(work_dir: Path) -> bool:
    """
    Skip ``create_training_dataset`` when resuming mid-training.

    Re-running label conversion before every train caused long hangs on re-run
    (e.g. stuck at the last logged epoch while DLC rebuilt the dataset).

    Never skip when ``config.yaml`` asks for a train fraction that has no shuffle
    yet (e.g. after changing 95/5 → 80/20).
    """
    if not has_training_dataset(work_dir):
        return False
    frac = read_config_training_fraction(work_dir)
    if frac is not None and not has_shuffle_for_fraction(work_dir, frac):
        return False
    prior = read_training_progress(work_dir)
    return prior is not None and prior[0] > 0


def clear_training_datasets(work_dir: Path) -> None:
    """Remove ``training-datasets/`` so DLC can rebuild shuffles for the current fraction."""
    target = Path(work_dir) / "training-datasets"
    if target.is_dir():
        remove_tree_resilient(target)


def read_training_progress(work_dir: Path) -> tuple[int, float] | None:
    """Return ``(epoch_step, loss)`` from the latest row of on-disk training stats."""
    history = load_training_loss_history(work_dir)
    if not history:
        return None
    return history[-1]


def parse_learning_stats_csv(path: Path) -> tuple[int, float] | None:
    """Return ``(epoch_step, loss)`` from the latest row of a DLC ``learning_stats.csv``."""
    history = load_learning_stats_history(path)
    if not history:
        return None
    return history[-1]


def reset_training_progress(work_dir: Path) -> int:
    """
    Delete DLC checkpoints and loss logs so the next train starts at epoch 0.

    Returns the last completed epoch that was cleared (0 if none).
    """
    last_epoch = 0
    prior = read_training_progress(work_dir)
    if prior is not None:
        last_epoch = prior[0]

    if not stop_dlc_subprocess(work_dir):
        raise OSError(
            "A DLC training subprocess is still running and could not be stopped. "
            "Wait for training to finish or close the Train Model dialog, then try again."
        )

    clear_stop_flag(work_dir)
    for dirname in ("dlc-models-pytorch", "dlc-models"):
        target = work_dir / dirname
        if target.is_dir():
            remove_tree_resilient(target)
    return last_epoch


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
