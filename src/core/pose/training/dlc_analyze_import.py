"""Import DLC ``analyze_videos`` outputs into Pose Studio ``ai_labelled/``."""

from __future__ import annotations

from pathlib import Path

from app_platform.paths import ai_labelled_dir, human_labelled_dir, pose_video_dir
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import labels_path, load_labels, save_schema
from core.pose.labeling.named_label_sets import apply_edges_to_dataset
from core.pose.video.video_registry import read_video_meta, resolve_video_source


def find_dlc_prediction_csv(video_path: Path) -> Path | None:
    """Return the newest DLC-shaped prediction CSV next to ``video_path``."""
    parent = video_path.parent
    stem = video_path.stem
    candidates = sorted(
        parent.glob(f"{stem}*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.name == "tracking.csv":
            continue
        try:
            import_dlc_csv(path)
            return path
        except (OSError, ValueError):
            continue
    return None


def find_dlc_prediction_h5(video_path: Path) -> Path | None:
    parent = video_path.parent
    h5s = sorted(
        parent.glob(f"{video_path.stem}*.h5"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return h5s[0] if h5s else None


def _h5_to_csv(h5_path: Path, csv_path: Path) -> Path:
    import pandas as pd

    df = pd.read_hdf(h5_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path)
    return csv_path


def _resolve_video_path(session_name: str, project_id: str, video_id: str, source: str | None) -> Path | None:
    if source:
        path = Path(source)
        if path.is_file():
            return path
    vdir = pose_video_dir(session_name, project_id, video_id)
    resolved = resolve_video_source(vdir)
    return resolved if resolved is not None and resolved.is_file() else None


def import_dlc_analyze_outputs_to_ai_labelled(job: dict) -> list[Path]:
    """
    Copy DLC video-analysis outputs into ``ai_labelled/<video_id>/tracking.csv``.

    DLC writes ``<video_stem><scorer>.csv`` (and ``.h5``) beside the source video.
    """
    session_name = str(job["session_name"])
    project_id = str(job["project_id"])
    scorer = str(job.get("scorer") or "pose_studio")
    video_ids: list[str] = list(job.get("video_ids") or [])
    video_sources: list[str] = list(job.get("video_sources") or [])

    written: list[Path] = []
    for index, video_id in enumerate(video_ids):
        source = video_sources[index] if index < len(video_sources) else None
        video_path = _resolve_video_path(session_name, project_id, video_id, source)
        if video_path is None:
            continue

        pred_csv = find_dlc_prediction_csv(video_path)
        if pred_csv is None:
            h5_path = find_dlc_prediction_h5(video_path)
            if h5_path is not None:
                pred_csv = _h5_to_csv(h5_path, video_path.parent / f"{video_path.stem}_dlc_import.csv")
        if pred_csv is None:
            continue

        vdir = pose_video_dir(session_name, project_id, video_id)
        meta = read_video_meta(vdir)
        frame_count = meta.frame_count if meta else 0
        dataset, csv_frames, _ = import_dlc_csv(pred_csv)
        if frame_count <= 0:
            frame_count = csv_frames

        out_dir = ai_labelled_dir(session_name, project_id, video_id)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / "tracking.csv"
        human_dir = human_labelled_dir(session_name, project_id, video_id)
        human = None
        if labels_path(human_dir).is_file():
            try:
                human = load_labels(human_dir)
            except (OSError, ValueError, FileNotFoundError):
                human = None
        if human is not None and human.schema.edges:
            apply_edges_to_dataset(dataset, preferred=human.schema)
        else:
            apply_edges_to_dataset(dataset)
        export_dlc_csv(dataset, frame_count, out_csv, scorer=scorer)
        save_schema(out_dir, dataset.schema)
        written.append(out_csv)

    return written
