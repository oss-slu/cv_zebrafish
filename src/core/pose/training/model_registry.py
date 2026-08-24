"""Saved pose model runs (DLC snapshots) per session project."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import bundled_models_dir, pose_models_dir

RUNS_DIRNAME = "runs"
BRANCHES_DIRNAME = "branches"
MANIFEST_FILENAME = "manifest.json"
BRANCH_MANIFEST_FILENAME = "branch_manifest.json"
WEIGHTS_FILENAME = "weights.pt"
TRAIN_JOB_FILENAME = "train_job.json"
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
    parent_run_id: str | None = None
    parent_checkpoint_key: str | None = None
    imported: bool = False

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
            parent_run_id=str(raw["parent_run_id"]) if raw.get("parent_run_id") else None,
            parent_checkpoint_key=(
                str(raw["parent_checkpoint_key"]) if raw.get("parent_checkpoint_key") else None
            ),
            imported=bool(raw.get("imported")),
        )

    def display_label(self) -> str:
        ep = f", {self.epochs} ep" if self.epochs else ""
        name = self.snapshot_name or Path(self.snapshot_path).name
        return f"{self.label} — {name}{ep}"


def runs_root(session_name: str, project_id: str) -> Path:
    return pose_models_dir(session_name, project_id) / RUNS_DIRNAME


def branches_root(session_name: str, project_id: str) -> Path:
    return pose_models_dir(session_name, project_id) / BRANCHES_DIRNAME


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


def latest_checkpoint_key(work_dir: Path) -> str | None:
    """Resolved path of the newest interval snapshot in ``work_dir`` (excludes best-only)."""
    paths = list_snapshot_paths(work_dir)
    if not paths:
        return None
    best_epoch = -1
    best_path: Path | None = None
    for path in paths:
        epoch, is_best = parse_snapshot_epoch(path)
        if is_best:
            continue
        if epoch is not None and epoch >= best_epoch:
            best_epoch = epoch
            best_path = path
    if best_path is not None:
        return str(best_path.resolve())
    return str(paths[-1].resolve())


def is_checkpoint_at_training_tip(work_dir: Path, checkpoint_key: str) -> bool:
    """True when ``checkpoint_key`` is the latest epoch snapshot in ``work_dir``."""
    if not work_dir.is_dir():
        return False
    key = str(Path(checkpoint_key).resolve())
    tip = latest_checkpoint_key(work_dir)
    if tip is None:
        return False
    return key == tip


def _copy_tree_item(src: Path, dest: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    elif src.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)


def create_branch_from_checkpoint(
    *,
    session_name: str,
    project_id: str,
    source_work_dir: Path,
    checkpoint_path: Path,
    job: dict,
    parent_run_id: str | None = None,
    parent_checkpoint_key: str | None = None,
) -> tuple[Path, Path]:
    """
    Fork training into a new branch work dir from a checkpoint.

    Copies bundle artifacts and seeds the new train folder with the chosen snapshot
    so the parent ``dlc_work`` (or archived run) is left intact.
    """
    source_work_dir = Path(source_work_dir)
    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.is_file():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    branch_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    new_work = branches_root(session_name, project_id) / branch_id
    new_work.mkdir(parents=True, exist_ok=True)

    for name in ("config.yaml", "labeled-data", "training-datasets"):
        src = source_work_dir / name
        if src.exists():
            _copy_tree_item(src, new_work / name)

    train_dirs = sorted(
        source_work_dir.glob("dlc-models-pytorch/**/train"),
        key=lambda p: p.stat().st_mtime,
    )
    if train_dirs:
        rel = train_dirs[-1].relative_to(source_work_dir)
        new_train = new_work / rel
        new_train.mkdir(parents=True, exist_ok=True)
        model_dir = train_dirs[-1].parent
        for fname in ("pytorch_config.yaml", "learning_stats.csv"):
            cfg = model_dir / fname
            if cfg.is_file():
                _copy_tree_item(cfg, new_train.parent / fname)
        dest_snap = new_train / checkpoint_path.name
        if "best" in checkpoint_path.stem.lower():
            dest_snap = new_train / "snapshot-best.pt"
        shutil.copy2(checkpoint_path, dest_snap)

    new_job = dict(job)
    new_job["work_dir"] = str(new_work.resolve())
    new_job["config_path"] = str((new_work / "config.yaml").resolve())
    new_job["branch_id"] = branch_id
    if parent_run_id:
        new_job["branch_parent_run_id"] = parent_run_id
    if parent_checkpoint_key:
        new_job["branch_parent_checkpoint"] = parent_checkpoint_key
    new_job_path = new_work / TRAIN_JOB_FILENAME
    new_job_path.write_text(json.dumps(new_job, indent=2), encoding="utf-8")

    branch_manifest = {
        "branch_id": branch_id,
        "parent_run_id": parent_run_id,
        "parent_checkpoint_key": parent_checkpoint_key,
        "checkpoint_path": str(checkpoint_path.resolve()),
        "work_dir": str(new_work.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (new_work / BRANCH_MANIFEST_FILENAME).write_text(
        json.dumps(branch_manifest, indent=2),
        encoding="utf-8",
    )
    return new_work, new_job_path


def _find_weights_in_folder(folder: Path) -> tuple[Path, str, str]:
    """Return ``(weights_path, snapshot_name, dlc_train_dir)`` from an import folder."""
    folder = Path(folder)
    weights = folder / WEIGHTS_FILENAME
    if weights.is_file():
        manifest = folder / MANIFEST_FILENAME
        dlc_train = ""
        if manifest.is_file():
            try:
                raw = json.loads(manifest.read_text(encoding="utf-8"))
                dlc_train = str(raw.get("dlc_train_dir") or "")
            except (OSError, json.JSONDecodeError):
                pass
        return weights, WEIGHTS_FILENAME, dlc_train

    snaps = sorted(
        list(folder.glob("**/train/snapshot*.pt")) + list(folder.glob("snapshot*.pt")),
        key=lambda p: p.stat().st_mtime,
    )
    if not snaps:
        raise FileNotFoundError(
            f"No weights.pt or snapshot-*.pt found under {folder}"
        )
    best = snaps[-1]
    for path in reversed(snaps):
        if "best" in path.stem.lower():
            best = path
            break
    train_dir = best.parent if best.parent.name == "train" else ""
    return best, best.name, str(train_dir.resolve()) if train_dir else ""


def import_external_model_run(
    session_name: str,
    project_id: str,
    source_folder: Path,
    *,
    label: str | None = None,
) -> ModelRun:
    """
    Import an external DLC model folder into ``models/runs/<run_id>/``.

    Accepts a folder with ``weights.pt`` (+ optional ``manifest.json``) or a DLC
    train directory containing ``snapshot-*.pt`` files.
    """
    source_folder = Path(source_folder)
    if not source_folder.is_dir():
        raise FileNotFoundError(f"Import folder not found: {source_folder}")

    weights_src, snapshot_name, dlc_train_dir = _find_weights_in_folder(source_folder)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = runs_root(session_name, project_id) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    weights_dest = run_dir / WEIGHTS_FILENAME
    shutil.copy2(weights_src, weights_dest)

    epochs: int | None = None
    epoch, _ = parse_snapshot_epoch(weights_src)
    if epoch is not None:
        epochs = epoch
    elif (source_folder / MANIFEST_FILENAME).is_file():
        try:
            raw = json.loads((source_folder / MANIFEST_FILENAME).read_text(encoding="utf-8"))
            if raw.get("epochs") is not None:
                epochs = int(raw["epochs"])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass

    display = label or f"Imported {source_folder.name}"
    record = ModelRun(
        run_id=run_id,
        label=display,
        created_at=datetime.now(timezone.utc).isoformat(),
        snapshot_path=str(weights_dest.resolve()),
        dlc_train_dir=dlc_train_dir,
        work_dir=str(source_folder.resolve()),
        config_path="",
        epochs=epochs,
        snapshot_name=snapshot_name,
        imported=True,
    )
    (run_dir / MANIFEST_FILENAME).write_text(
        json.dumps(record.to_dict(), indent=2),
        encoding="utf-8",
    )
    return record


def install_bundled_model_if_empty(session_name: str, project_id: str) -> ModelRun | None:
    """
    Copy a drop-in run from ``assets/models/`` when the project has no saved runs.

    Returns the imported :class:`ModelRun` or ``None`` when skipped.
    """
    if list_model_runs(session_name, project_id):
        return None
    models_dir = pose_models_dir(session_name, project_id)
    from core.pose.training.dlc_bundle import DLC_WORK_DIRNAME

    work_dir = models_dir / DLC_WORK_DIRNAME
    if work_dir.is_dir() and list_snapshot_paths(work_dir):
        return None

    bundled = bundled_models_dir()
    if not bundled.is_dir():
        return None
    for sub in sorted(bundled.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if sub.name.lower() == "readme.md":
            continue
        label = f"Bundled {sub.name}"
        meta_path = sub / MANIFEST_FILENAME
        if meta_path.is_file():
            try:
                raw = json.loads(meta_path.read_text(encoding="utf-8"))
                if raw.get("label"):
                    label = str(raw["label"])
            except (OSError, json.JSONDecodeError):
                pass
        try:
            return import_external_model_run(
                session_name,
                project_id,
                sub,
                label=label,
            )
        except (OSError, FileNotFoundError):
            continue
    return None


def list_active_branch_work_dirs(session_name: str, project_id: str) -> list[Path]:
    """Return branch work dirs (newest first) under ``models/branches/``."""
    root = branches_root(session_name, project_id)
    if not root.is_dir():
        return []
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return sorted(dirs, key=lambda p: p.name, reverse=True)


def runs_by_parent(runs: list[ModelRun]) -> dict[str | None, list[ModelRun]]:
    """Group runs by ``parent_run_id`` for tree building."""
    grouped: dict[str | None, list[ModelRun]] = {}
    for run in runs:
        key = run.parent_run_id or None
        grouped.setdefault(key, []).append(run)
    return grouped


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

    parent_run_id = job.get("branch_parent_run_id")
    parent_checkpoint = job.get("branch_parent_checkpoint")
    branch_manifest = work_dir / BRANCH_MANIFEST_FILENAME
    if branch_manifest.is_file():
        try:
            branch_raw = json.loads(branch_manifest.read_text(encoding="utf-8"))
            parent_run_id = parent_run_id or branch_raw.get("parent_run_id")
            parent_checkpoint = parent_checkpoint or branch_raw.get("parent_checkpoint_key")
        except (OSError, json.JSONDecodeError):
            pass

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
        parent_run_id=str(parent_run_id) if parent_run_id else None,
        parent_checkpoint_key=str(parent_checkpoint) if parent_checkpoint else None,
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
    if snapshot_path.resolve() != dest.resolve():
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
