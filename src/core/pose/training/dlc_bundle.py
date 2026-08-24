"""Prepare DLC training bundle from Pose Studio human labels."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import cv2
import pandas as pd

from app_platform.paths import human_labelled_dir, pose_models_dir, pose_video_dir
from core.pose.detection.arena import ArenaConfig, load_arena
from core.pose.detection.blob import BlobParams, detect_blob_square_crop, load_blob_params
from core.pose.detection.crop import extract_square_crop, full_frame_to_crop
from core.pose.labeling.labels_store import LabelDataset, load_labels
from core.pose.video.video_registry import resolve_video_source

MIN_LABELED_FRAMES = 50
RECOMMENDED_LABELED_FRAMES = 100

DLC_WORK_DIRNAME = "dlc_work"
TRAIN_JOB_FILENAME = "train_job.json"
CONFIG_FILENAME = "config.yaml"
DEFAULT_SCORER = "pose_studio"


def collected_data_filename(scorer: str = DEFAULT_SCORER) -> str:
    return f"CollectedData_{scorer}.csv"


def dlc_label_set_stem(video_id: str, video_source: Path | None = None) -> str:
    """
    Unique ``labeled-data/<stem>/`` name for a project video.

    Project videos are stored as ``source.mp4`` in every folder, so the file stem
    alone collides when training on multiple videos. Prefer the project ``video_id``.
    """
    raw = (video_id or "").strip() or (video_source.stem if video_source else "video")
    safe = re.sub(r"[^\w\-]+", "_", raw).strip("_")
    return safe or "video"


def _label_set_folder_name(video_source: Path, *, video_id: str | None = None) -> str:
    """DLC expects ``labeled-data/<video_stem>/`` matching the video_sets path stem."""
    return dlc_label_set_stem(video_id or "", video_source)


def _ensure_unique_video_path(work_dir: Path, video_id: str, src: Path) -> Path:
    """
    Point DLC ``video_sets`` at ``work_dir/videos/<unique_stem>.mp4``.

    Prefer symlink, then hardlink, then a tiny stub file (training uses crop images
    under labeled-data; the path stem only needs to be unique for DLC).
    """
    stem = dlc_label_set_stem(video_id, src)
    videos_dir = work_dir / "videos"
    videos_dir.mkdir(parents=True, exist_ok=True)
    dest = videos_dir / f"{stem}.mp4"
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    src_res = src.resolve()
    try:
        dest.symlink_to(src_res)
        return dest
    except OSError:
        pass
    try:
        os.link(src_res, dest)
        return dest
    except OSError:
        pass
    # Last resort: empty placeholder so the unique stem exists for DLC matching.
    dest.write_bytes(b"")
    return dest


@dataclass
class ProjectLabelStats:
    total_labeled_frames: int = 0
    per_video: dict[str, int] = field(default_factory=dict)
    per_bodypart: dict[str, int] = field(default_factory=dict)
    bodyparts: list[str] = field(default_factory=list)

    def meets_minimum(self) -> bool:
        return self.total_labeled_frames >= MIN_LABELED_FRAMES


def train_job_path(session_name: str, project_id: str) -> Path:
    """Path to ``train_job.json`` under ``models/dlc_work/``."""
    return pose_models_dir(session_name, project_id) / DLC_WORK_DIRNAME / TRAIN_JOB_FILENAME


def find_train_job_path(session_name: str, project_id: str) -> Path | None:
    """Return existing ``train_job.json`` when the prepared bundle is on disk."""
    path = train_job_path(session_name, project_id)
    return path if path.is_file() else None


def load_train_job_if_present(session_name: str, project_id: str) -> dict | None:
    path = find_train_job_path(session_name, project_id)
    if path is None:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def training_bundle_is_stale(
    session_name: str,
    project_id: str,
    video_ids: list[str],
    job: dict,
) -> bool:
    """True when human labels changed since the bundle in ``job`` was prepared."""
    stats = gather_project_label_stats(session_name, project_id, video_ids)
    if stats.total_labeled_frames != int(job.get("labeled_frame_count") or 0):
        return True
    if list(video_ids) != list(job.get("video_ids") or []):
        return True
    if stats.bodyparts != list(job.get("bodyparts") or []):
        return True
    # Legacy bundles pointed video_sets at raw ``…/source.mp4`` paths — DLC then
    # collapsed every video into labeled-data/source and produced empty shuffles.
    sources = [str(p) for p in (job.get("video_sources") or [])]
    if len(sources) >= 2:
        stems = {Path(p).stem.lower() for p in sources}
        if stems == {"source"} or len(stems) < len(sources):
            return True
    work = str(job.get("work_dir") or "")
    if work:
        labeled = Path(work) / "labeled-data"
        if labeled.is_dir():
            expected = {
                dlc_label_set_stem(vid)
                for vid in video_ids
                if stats.per_video.get(vid, 0) > 0
            }
            present = {p.name for p in labeled.iterdir() if p.is_dir()}
            if expected and not expected.issubset(present):
                return True
    return False


def gather_project_label_stats(
    session_name: str,
    project_id: str,
    video_ids: list[str],
) -> ProjectLabelStats:
    """Count labeled frames across all project videos."""
    stats = ProjectLabelStats()
    bodyparts: list[str] | None = None
    for vid in video_ids:
        label_dir = human_labelled_dir(session_name, project_id, vid)
        ds = load_labels(label_dir)
        if bodyparts is None and ds.bodyparts():
            bodyparts = ds.bodyparts()
        n = len(ds.frames)
        stats.per_video[vid] = n
        stats.total_labeled_frames += n
        for bp in ds.bodyparts():
            stats.per_bodypart[bp] = stats.per_bodypart.get(bp, 0) + ds.count_for_bodypart(bp)
    stats.bodyparts = bodyparts or []
    return stats


def _write_config_yaml(
    path: Path,
    *,
    project_path: Path,
    bodyparts: list[str],
    video_paths: list[str],
    scorer: str,
) -> None:
    """DLC 3–compatible config with required training keys."""
    task = "zebrafish_pose"
    date = datetime.now().strftime("%b%d")
    lines = [
        "# Project definitions (do not edit)",
        f"Task: {task}",
        f"scorer: {scorer}",
        f"date: {date}",
        "multianimalproject: false",
        "identity:",
        "",
        f"project_path: {project_path}",
        "",
        "engine: pytorch",
        "",
        "video_sets:",
    ]
    for vp in video_paths:
        lines.append(f"  {vp}:")
        lines.append("    crop: 0, 0, 0, 0")
    lines.extend(
        [
            "bodyparts:",
            *[f"- {bp}" for bp in bodyparts],
            "uniquebodyparts:",
            *[f"- {bp}" for bp in bodyparts],
            "",
            "start:",
            "stop:",
            "numframes2pick:",
            "",
            "skeleton: []",
            "skeleton_color: black",
            "pcutoff: 0.6",
            "dotsize: 12",
            "alphavalue: 0.7",
            "colormap: rainbow",
            "",
            "TrainingFraction: [0.8]",
            "iteration: 0",
            "default_net_type: resnet_50",
            "default_augmenter: albumentations",
            "snapshotindex: -1",
            "detector_snapshotindex: -1",
            "batch_size: 8",
            "detector_batch_size: 1",
            "",
            "cropping: false",
            "x1: 0",
            "x2: 640",
            "y1: 277",
            "y2: 624",
            "",
            "corner2move2:",
            "move2corner:",
            "",
            "SuperAnimalConversionTables:",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _export_collected_data_csv(
    path: Path,
    rows: list[tuple[str, dict[str, tuple[float, float] | None]]],
    bodyparts: list[str],
    scorer: str,
) -> None:
    """Write DLC CollectedData CSV (image path index + x,y,likelihood columns)."""
    header0 = ["scorer"] + [scorer] * (len(bodyparts) * 3)
    header1 = ["bodyparts"] + [bp for bp in bodyparts for _ in range(3)]
    header2 = ["coords"] + sum([["x", "y", "likelihood"] for _ in bodyparts], [])
    out_rows = [header0, header1, header2]
    for image_key, points in rows:
        row = [image_key]
        for bp in bodyparts:
            xy = points.get(bp)
            if xy is None:
                row.extend(["", "", ""])
            else:
                row.extend([xy[0], xy[1], 1.0])
        out_rows.append(row)
    df = pd.DataFrame(out_rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, header=False)


def prepare_training_bundle(
    session_name: str,
    project_id: str,
    video_ids: list[str],
    *,
    scorer: str = "pose_studio",
    augment_rotation: bool = True,
    augment_brightness: bool = True,
    augment_flip: bool = False,
) -> tuple[Path, ProjectLabelStats]:
    """
    Build ``models/dlc_work/`` with crop images, CollectedData CSV, config, and train_job.json.

    Returns ``(train_job_path, label_stats)``.
    """
    stats = gather_project_label_stats(session_name, project_id, video_ids)
    if not stats.bodyparts:
        raise ValueError("No bodyparts defined in project labels.")
    if not stats.meets_minimum():
        raise ValueError(
            f"Need at least {MIN_LABELED_FRAMES} labeled frames for training "
            f"(have {stats.total_labeled_frames})."
        )

    work_dir = pose_models_dir(session_name, project_id) / DLC_WORK_DIRNAME
    labeled_dir = work_dir / "labeled-data"
    # Rebuild labeled-data cleanly so old ``source`` collisions cannot linger.
    if labeled_dir.is_dir():
        shutil.rmtree(labeled_dir, ignore_errors=True)
    labeled_dir.mkdir(parents=True, exist_ok=True)

    collected_rows: list[tuple[str, dict[str, tuple[float, float] | None]]] = []
    collected_paths: list[str] = []
    video_sources: list[str] = []
    crop_image_count = 0

    for vid in video_ids:
        if stats.per_video.get(vid, 0) == 0:
            continue
        vdir = pose_video_dir(session_name, project_id, vid)
        src = resolve_video_source(vdir)
        if src is None:
            continue
        src = src.resolve()
        unique_src = _ensure_unique_video_path(work_dir, vid, src)
        video_sources.append(str(unique_src.resolve()))
        label_set = _label_set_folder_name(src, video_id=vid)
        arena = load_arena(vdir / "arena.json")
        blob_params = load_blob_params(vdir / "blob_params.json")
        ds = load_labels(human_labelled_dir(session_name, project_id, vid))

        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            raise ValueError(f"Could not open video for training crops: {src}")
        video_rows: list[tuple[str, dict[str, tuple[float, float] | None]]] = []
        try:
            vid_crop_dir = labeled_dir / label_set
            vid_crop_dir.mkdir(parents=True, exist_ok=True)
            for frame_index in sorted(ds.frames.keys()):
                cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                blob = detect_blob_square_crop(frame, arena, blob_params)
                if not blob.found:
                    continue
                crop = extract_square_crop(frame, blob)
                if crop is None or crop.size == 0:
                    continue
                img_name = f"img{frame_index:06d}.png"
                img_path = vid_crop_dir / img_name
                cv2.imwrite(str(img_path), crop)
                image_key = f"labeled-data/{label_set}/{img_name}"
                points_crop: dict[str, tuple[float, float] | None] = {}
                fl = ds.frames[frame_index]
                for bp, xy in fl.points.items():
                    if xy is None:
                        points_crop[bp] = None
                    else:
                        cx, cy = full_frame_to_crop(xy[0], xy[1], blob)
                        points_crop[bp] = (cx, cy)
                video_rows.append((image_key, points_crop))
                crop_image_count += 1
        finally:
            cap.release()

        if not video_rows:
            continue
        csv_path = vid_crop_dir / collected_data_filename(scorer)
        _export_collected_data_csv(csv_path, video_rows, stats.bodyparts, scorer)
        collected_paths.append(str(csv_path.resolve()))
        collected_rows.extend(video_rows)

    if not collected_rows:
        raise ValueError("No training crop images could be extracted from labeled frames.")

    config_path = work_dir / CONFIG_FILENAME
    _write_config_yaml(
        config_path,
        project_path=work_dir.resolve(),
        bodyparts=stats.bodyparts,
        video_paths=video_sources,
        scorer=scorer,
    )

    # Stale empty shuffle metadata must not block a fresh create_training_dataset.
    td = work_dir / "training-datasets"
    if td.is_dir():
        shutil.rmtree(td, ignore_errors=True)

    job = {
        "version": 1,
        "session_name": session_name,
        "project_id": project_id,
        "scorer": scorer,
        "work_dir": str(work_dir.resolve()),
        "config_path": str(config_path.resolve()),
        "collected_data_paths": collected_paths,
        "video_ids": video_ids,
        "video_sources": video_sources,
        "bodyparts": stats.bodyparts,
        "labeled_frame_count": stats.total_labeled_frames,
        "crop_image_count": crop_image_count,
        "augment": {
            "rotation": augment_rotation,
            "brightness": augment_brightness,
            "flip": augment_flip,
        },
        "backend": "deeplabcut",
        "attribute": "DLC 3 PyTorch",
        "prepared_at": datetime.now(timezone.utc).isoformat(),
    }
    job_path = work_dir / TRAIN_JOB_FILENAME
    job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    return job_path, stats
