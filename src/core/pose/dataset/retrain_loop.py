"""Retrain loop: promote AI/final labels into human training set."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import human_labelled_dir
from core.pose.dataset.dataset_merge import load_dataset_from_source
from core.pose.labeling.labels_store import LabelDataset, load_labels, save_labels

RETRAIN_LOG_FILENAME = "retrain_log.json"


@dataclass
class ImportResult:
    video_id: str
    points_added: int
    frames_touched: int


def merge_source_into_human(
    human: LabelDataset,
    source: LabelDataset,
    *,
    manual_wins: bool = True,
    only_missing: bool = True,
) -> tuple[LabelDataset, int, int]:
    """
    Overlay ``source`` onto ``human``.

    When ``manual_wins`` and ``only_missing``, existing human points are kept;
    AI/final points fill gaps only.

    Returns ``(human, points_added, frames_touched)``.
    """
    points_added = 0
    frames_touched: set[int] = set()
    for fi, fl in source.frames.items():
        for bp, xy in fl.points.items():
            if xy is None:
                continue
            if bp not in human.bodyparts():
                continue
            existing = human.get_point(fi, bp)
            if manual_wins and existing is not None:
                continue
            if only_missing and existing is not None:
                continue
            human.set_point(fi, bp, xy[0], xy[1])
            points_added += 1
            frames_touched.add(fi)
    return human, points_added, len(frames_touched)


def import_source_into_human(
    session_name: str,
    project_id: str,
    video_id: str,
    source: str,
    *,
    only_missing: bool = True,
) -> ImportResult:
    """Copy AI or final labels into ``human_labelled`` (gaps only by default)."""
    if source not in {"ai", "final"}:
        raise ValueError(f"import source must be ai or final, not {source!r}")

    human_dir = human_labelled_dir(session_name, project_id, video_id)
    human = load_labels(human_dir)
    src_ds, _ = load_dataset_from_source(session_name, project_id, video_id, source)
    if not src_ds.frames:
        return ImportResult(video_id=video_id, points_added=0, frames_touched=0)

    human, added, touched = merge_source_into_human(
        human,
        src_ds,
        manual_wins=True,
        only_missing=only_missing,
    )
    if added > 0:
        save_labels(human_dir, human)
    return ImportResult(video_id=video_id, points_added=added, frames_touched=touched)


def import_project_sources_into_human(
    session_name: str,
    project_id: str,
    video_ids: list[str],
    source: str = "ai",
    *,
    only_missing: bool = True,
) -> list[ImportResult]:
    """Import gaps for every project video."""
    return [
        import_source_into_human(
            session_name,
            project_id,
            vid,
            source,
            only_missing=only_missing,
        )
        for vid in video_ids
    ]


def append_retrain_log(
    session_name: str,
    project_id: str,
    *,
    iteration: int,
    import_results: list[ImportResult],
    job_path: Path | None = None,
) -> Path:
    """Append one retrain iteration record under ``models/retrain_log.json``."""
    from app_platform.paths import pose_models_dir

    log_path = pose_models_dir(session_name, project_id) / RETRAIN_LOG_FILENAME
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    if log_path.is_file():
        try:
            entries = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except (OSError, json.JSONDecodeError):
            entries = []

    entries.append(
        {
            "iteration": iteration,
            "at": datetime.now(timezone.utc).isoformat(),
            "import_source": "ai",
            "imports": [
                {
                    "video_id": r.video_id,
                    "points_added": r.points_added,
                    "frames_touched": r.frames_touched,
                }
                for r in import_results
            ],
            "job_path": str(job_path) if job_path else None,
        }
    )
    log_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return log_path


def total_points_added(results: list[ImportResult]) -> int:
    return sum(r.points_added for r in results)
