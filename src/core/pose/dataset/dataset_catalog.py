"""Discover pose tracking datasets under a session project."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app_platform.paths import (
    ai_labelled_dir,
    custom_labelled_root,
    external_labelled_dir,
    final_labelled_dir,
    human_labelled_dir,
    pose_project_dir,
    pose_video_dir,
)
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import MANIFEST_FILENAME, load_labels
from core.pose.labeling.named_label_sets import read_dataset_meta


@dataclass
class PoseDatasetEntry:
    video_id: str
    source: str  # human | ai | final | external | custom
    dir_path: Path
    tracking_csv: Path | None
    labels_json: Path | None
    labeled_frames: int
    bodyparts: list[str]
    frame_count: int
    display_name: str
    custom_slug: str | None = None
    custom_display: str | None = None

    def source_key(self) -> str:
        """Stable merge/catalog key (``human``, ``ai``, ``custom:<slug>``, …)."""
        if self.source == "custom" and self.custom_slug:
            return f"custom:{self.custom_slug}"
        return self.source

    def source_label(self) -> str:
        """Short label for UI lists (dataset type / custom name)."""
        if self.custom_display:
            return self.custom_display
        if self.source == "custom" and self.custom_slug:
            return self.custom_slug
        return self.source

    def summary(self) -> str:
        bp = ", ".join(self.bodyparts[:4])
        if len(self.bodyparts) > 4:
            bp += "…"
        src = self.source_label()
        if self.source == "custom" and self.custom_display:
            src = f"custom: {self.custom_display}"
        return (
            f"{self.display_name} — {src} — "
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
    """Return (frames_with_any_point, bodyparts). Prefer live data over stale manifest counts."""
    manifest = label_dir / MANIFEST_FILENAME
    labels_json = label_dir / "labels.json"
    if labels_json.is_file():
        ds = load_labels(label_dir)
        return ds.count_frames_with_any_point(), ds.bodyparts()
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            per = data.get("per_bodypart") or {}
            if per:
                return int(max(per.values())), list(data.get("bodyparts") or [])
            return int(data.get("labeled_frame_count", 0)), list(data.get("bodyparts") or [])
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return 0, []


def _entry_from_dir(
    video_id: str,
    source: str,
    label_dir: Path,
    frame_count: int,
    display_name: str,
    *,
    custom_slug: str | None = None,
    custom_display: str | None = None,
) -> PoseDatasetEntry | None:
    labels_json = label_dir / "labels.json"
    tracking = label_dir / "tracking.csv"
    has_labels = labels_json.is_file()
    has_csv = tracking.is_file()
    if not has_labels and not has_csv:
        return None

    labeled_frames = 0
    bodyparts: list[str] = []
    # Prefer tracking.csv stats when present (matches load_dataset_from_dir).
    if has_csv:
        try:
            _ds, fc, bodyparts = import_dlc_csv(tracking)
            labeled_frames = _ds.count_frames_with_any_point()
            if frame_count <= 0:
                frame_count = fc
        except (OSError, ValueError):
            return None
    elif has_labels:
        labeled_frames, bodyparts = _manifest_stats(label_dir)

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
        custom_slug=custom_slug,
        custom_display=custom_display,
    )


def list_datasets_for_video(
    session_name: str,
    project_id: str,
    video_id: str,
    video_display_name: str | None = None,
) -> list[PoseDatasetEntry]:
    """All label datasets for one video (built-in sources + custom named sets)."""
    vdir = pose_video_dir(session_name, project_id, video_id)
    frame_count = _read_frame_count(vdir)
    display = video_display_name or video_id
    entries: list[PoseDatasetEntry] = []

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

    custom_root = custom_labelled_root(session_name, project_id, video_id)
    if custom_root.is_dir():
        for sub in sorted(custom_root.iterdir()):
            if not sub.is_dir():
                continue
            meta = read_dataset_meta(sub)
            slug = sub.name
            cdisplay = str(meta.get("display_name") or slug)
            ent = _entry_from_dir(
                video_id,
                "custom",
                sub,
                frame_count,
                display,
                custom_slug=slug,
                custom_display=cdisplay,
            )
            if ent is not None:
                entries.append(ent)
    return entries


def list_pose_datasets(
    session_name: str,
    project_id: str,
    video_meta: dict[str, str] | None = None,
) -> list[PoseDatasetEntry]:
    """Return all label datasets (built-in + custom) for every video in a pose project."""
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
        entries.extend(
            list_datasets_for_video(session_name, project_id, video_id, display)
        )
    return entries
