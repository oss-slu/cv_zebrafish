"""Discover pose tracking datasets under a session project."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app_platform.paths import (
    ai_labelled_dir,
    external_labelled_dir,
    final_labelled_dir,
    human_labelled_dir,
    pose_project_dir,
    pose_video_dir,
)
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import MANIFEST_FILENAME, load_labels


@dataclass
class PoseDatasetEntry:
    video_id: str
    source: str  # human | ai | final | external
    dir_path: Path
    tracking_csv: Path | None
    labels_json: Path | None
    labeled_frames: int
    bodyparts: list[str]
    frame_count: int
    display_name: str

    def summary(self) -> str:
        bp = ", ".join(self.bodyparts[:4])
        if len(self.bodyparts) > 4:
            bp += "…"
        return (
            f"{self.display_name} — {self.source} — "
            f"{self.labeled_frames} labeled / {self.frame_count} frames — {bp}"
        )


def _read_frame_count(video_dir: Path) -> int:
    meta = video_dir / "meta.json"
    if not meta.is_file():
        return 0
    try:
        return int(json.loads(meta.read_text(encoding="utf-8")).get("frame_count", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def _manifest_stats(label_dir: Path) -> tuple[int, list[str]]:
    manifest = label_dir / MANIFEST_FILENAME
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            return int(data.get("labeled_frame_count", 0)), list(data.get("bodyparts") or [])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    ds = load_labels(label_dir)
    return len(ds.frames), ds.bodyparts()


def _entry_from_dir(
    video_id: str,
    source: str,
    label_dir: Path,
    frame_count: int,
    display_name: str,
) -> PoseDatasetEntry | None:
    labels_json = label_dir / "labels.json"
    tracking = label_dir / "tracking.csv"
    has_labels = labels_json.is_file()
    has_csv = tracking.is_file()
    if not has_labels and not has_csv:
        return None

    labeled_frames = 0
    bodyparts: list[str] = []
    if has_labels:
        labeled_frames, bodyparts = _manifest_stats(label_dir)
    elif has_csv:
        try:
            _ds, fc, bodyparts = import_dlc_csv(tracking)
            labeled_frames = len(_ds.frames)
            if frame_count <= 0:
                frame_count = fc
        except (OSError, ValueError):
            return None

    return PoseDatasetEntry(
        video_id=video_id,
        source=source,
        dir_path=label_dir,
        tracking_csv=tracking if has_csv else None,
        labels_json=labels_json if has_labels else None,
        labeled_frames=labeled_frames,
        bodyparts=bodyparts,
        frame_count=frame_count,
        display_name=display_name,
    )


def list_pose_datasets(
    session_name: str,
    project_id: str,
    video_meta: dict[str, str] | None = None,
) -> list[PoseDatasetEntry]:
    """Return human / AI / final dataset entries for all videos in a pose project."""
    proj = pose_project_dir(session_name, project_id)
    if not proj.is_dir():
        return []

    entries: list[PoseDatasetEntry] = []
    videos_dir = proj / "videos"
    if not videos_dir.is_dir():
        return entries

    video_meta = video_meta or {}
    for vdir in sorted(videos_dir.iterdir()):
        if not vdir.is_dir():
            continue
        video_id = vdir.name
        display = video_meta.get(video_id, video_id)
        frame_count = _read_frame_count(vdir)

        for source, resolver in (
            ("human", lambda: human_labelled_dir(session_name, project_id, video_id)),
            ("ai", lambda: ai_labelled_dir(session_name, project_id, video_id)),
            ("external", lambda: external_labelled_dir(session_name, project_id, video_id)),
            ("final", lambda: final_labelled_dir(session_name, project_id, video_id)),
        ):
            label_dir = resolver()
            ent = _entry_from_dir(video_id, source, label_dir, frame_count, display)
            if ent is not None:
                entries.append(ent)
    return entries
