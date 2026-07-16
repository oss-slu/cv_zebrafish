"""Saved pose model runs (DLC snapshots) per session project."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import pose_models_dir

RUNS_DIRNAME = "runs"
MANIFEST_FILENAME = "manifest.json"
WEIGHTS_FILENAME = "weights.pt"
_SNAPSHOT_EPOCH_RE = re.compile(r"^snapshot-(\d+)$", re.IGNORECASE)


@dataclass(frozen=True)
class AnalyzeCheckpoint:
    """A DLC weight file that can be staged for video analysis."""

    key: str
    label: str
    path: Path
    epoch: int | None = None
    is_best: bool = False

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "path": str(self.path),
            "epoch": self.epoch,
            "is_best": self.is_best,
        }


@dataclass
class ModelRun:
    run_id: str
    label: str
    created_at: str
    snapshot_path: str
    dlc_train_dir: str
    work_dir: str
    config_path: str
    epochs: int | None = None
    labeled_frames: int | None = None
    snapshot_name: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> ModelRun:
        return cls(
            run_id=str(raw["run_id"]),
            label=str(raw.get("label") or raw["run_id"]),
            created_at=str(raw.get("created_at") or ""),
            snapshot_path=str(raw["snapshot_path"]),
            dlc_train_dir=str(raw.get("dlc_train_dir") or ""),
            work_dir=str(raw.get("work_dir") or ""),
            config_path=str(raw.get("config_path") or ""),
            epochs=int(raw["epochs"]) if raw.get("epochs") is not None else None,
            labeled_frames=(
                int(raw["labeled_frames"]) if raw.get("labeled_frames") is not None else None
            ),
            snapshot_name=str(raw.get("snapshot_name") or ""),
        )

    def display_label(self) -> str:
        ep = f", {self.epochs} ep" if self.epochs else ""
        name = self.snapshot_name or Path(self.snapshot_path).name
        return f"{self.label} — {name}{ep}"


def runs_root(session_name: str, project_id: str) -> Path:
    return pose_models_dir(session_name, project_id) / RUNS_DIRNAME


def list_snapshot_paths(work_dir: Path) -> list[Path]:
    paths = sorted(
        work_dir.glob("dlc-models-pytorch/**/train/snapshot*.pt"),
        key=lambda p: p.stat().st_mtime,
    )
    return paths


def parse_snapshot_epoch(path: Path) -> tuple[int | None, bool]:
    """Return ``(epoch, is_best)`` from a DLC ``snapshot*.pt`` filename."""
    stem = path.stem
    if "best" in stem.lower():
        return None, True
    match = _SNAPSHOT_EPOCH_RE.match(stem)
    if match:
        return int(match.group(1)), False
    return None, False


def list_analyze_checkpoints(
    work_dir: Path,
    *,
    loss_by_epoch: dict[int, float] | None = None,
    fallback_run: ModelRun | None = None,
) -> list[AnalyzeCheckpoint]:
    """
    List weight checkpoints available for Analyze (every-5th epoch + best).

    When ``dlc_work`` has no snapshots yet, falls back to a saved run's ``weights.pt``.
    """
    options: list[AnalyzeCheckpoint] = []
    losses = loss_by_epoch or {}
    for path in list_snapshot_paths(work_dir):
        if not path.is_file():
            continue
        epoch, is_best = parse_snapshot_epoch(path)
        if is_best:
            label = "Best (validation mAP)"
        elif epoch is not None:
            label = f"Epoch {epoch}"
            if epoch in losses:
                label += f" — total loss {losses[epoch]:.4f}"
        else:
            label = path.name
        resolved = path.resolve()
        options.append(
            AnalyzeCheckpoint(
                key=str(resolved),
                label=label,
                path=resolved,
                epoch=epoch,
                is_best=is_best,
            )
        )

    if not options and fallback_run is not None:
        snap = Path(fallback_run.snapshot_path)
        if snap.is_file():
            epoch, is_best = parse_snapshot_epoch(snap)
            if epoch is None and not is_best:
                epoch = fallback_run.epochs
            label = fallback_run.display_label()
            options.append(
                AnalyzeCheckpoint(
                    key=str(snap.resolve()),
                    label=label,
                    path=snap.resolve(),
                    epoch=epoch,
                    is_best=is_best,
                )
            )

    def _sort_key(opt: AnalyzeCheckpoint) -> tuple[int, int]:
        if opt.is_best:
            return (0, -1)
        return (1, opt.epoch or 0)

    return sorted(options, key=_sort_key)


def pick_default_checkpoint(
    options: list[AnalyzeCheckpoint],
    *,
    preferred_path: str | None = None,
) -> AnalyzeCheckpoint | None:
    if not options:
        return None
    if preferred_path:
        key = str(Path(preferred_path).resolve())
        for opt in options:
            if opt.key == key:
                return opt
    for opt in options:
        if opt.is_best:
            return opt
    return options[-1]


def _pick_best_snapshot(work_dir: Path) -> Path | None:
    paths = list_snapshot_paths(work_dir)
    if not paths:
        return None
    for path in reversed(paths):
        if "best" in path.stem.lower():
            return path
    return paths[-1]


def archive_completed_training(job: dict, *, epochs: int | None = None) -> ModelRun | None:
    """Copy the latest DLC snapshot into ``models/runs/<run_id>/`` and return metadata."""
    work_dir = Path(job["work_dir"])
    snapshot_src = _pick_best_snapshot(work_dir)
    if snapshot_src is None:
        return None

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    session_name = str(job["session_name"])
    project_id = str(job["project_id"])
    run_dir = runs_root(session_name, project_id) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    weights_dest = run_dir / WEIGHTS_FILENAME
    shutil.copy2(snapshot_src, weights_dest)

    labeled = job.get("labeled_frame_count")
    label = f"Train {run_id}"
    if labeled is not None:
        label = f"Train {labeled} frames ({run_id})"

    record = ModelRun(
        run_id=run_id,
        label=label,
        created_at=datetime.now(timezone.utc).isoformat(),
        snapshot_path=str(weights_dest.resolve()),
        dlc_train_dir=str(snapshot_src.parent.resolve()),
        work_dir=str(work_dir.resolve()),
        config_path=str(job.get("config_path") or ""),
        epochs=epochs,
        labeled_frames=int(labeled) if labeled is not None else None,
        snapshot_name=snapshot_src.name,
    )
    (run_dir / MANIFEST_FILENAME).write_text(
        json.dumps(record.to_dict(), indent=2),
        encoding="utf-8",
    )
    return record


def list_model_runs(session_name: str, project_id: str) -> list[ModelRun]:
    root = runs_root(session_name, project_id)
    if not root.is_dir():
        return []
    runs: list[ModelRun] = []
    for sub in sorted(root.iterdir(), reverse=True):
        if not sub.is_dir():
            continue
        manifest = sub / MANIFEST_FILENAME
        if not manifest.is_file():
            continue
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            runs.append(ModelRun.from_dict(raw))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return runs


def get_model_run(session_name: str, project_id: str, run_id: str) -> ModelRun | None:
    manifest = runs_root(session_name, project_id) / run_id / MANIFEST_FILENAME
    if not manifest.is_file():
        return None
    try:
        return ModelRun.from_dict(json.loads(manifest.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def stage_snapshot_for_analyze(work_dir: Path, snapshot_path: Path) -> Path:
    """
    Copy the chosen weights into the active DLC train folder as ``snapshot-best.pt``
    so ``analyze_videos(..., snapshot_index='best')`` uses the selected run.
    """
    snapshot_path = Path(snapshot_path)
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"Model weights not found: {snapshot_path}")

    train_dirs = sorted(
        work_dir.glob("dlc-models-pytorch/**/train"),
        key=lambda p: p.stat().st_mtime,
    )
    if not train_dirs:
        raise FileNotFoundError(
            "No DLC train folder found. Prepare the training bundle and train a model first."
        )
    train_dir = train_dirs[-1]
    dest = train_dir / "snapshot-best.pt"
    shutil.copy2(snapshot_path, dest)
    return dest


def copy_model_run(
    session_name: str,
    project_id: str,
    run: ModelRun,
    dest_dir: Path,
) -> Path:
    """Copy a saved run folder to ``dest_dir/<run_id>/``."""
    src = runs_root(session_name, project_id) / run.run_id
    if not src.is_dir():
        raise FileNotFoundError(f"Saved model run not found: {src}")
    dest = Path(dest_dir) / run.run_id
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def delete_model_run(session_name: str, project_id: str, run_id: str) -> None:
    """Remove a saved model run directory under ``models/runs/<run_id>/``."""
    run_dir = runs_root(session_name, project_id) / run_id
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Saved model run not found: {run_dir}")
    shutil.rmtree(run_dir)
