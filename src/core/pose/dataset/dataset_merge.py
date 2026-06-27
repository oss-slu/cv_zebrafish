"""Merge pose label datasets (manual wins over AI)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import (
    ai_labelled_dir,
    external_labelled_dir,
    final_labelled_dir,
    human_labelled_dir,
    pose_video_dir,
)
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import LabelDataset, load_labels

PROVENANCE_FILENAME = "provenance.json"


def _video_frame_count(session_name: str, project_id: str, video_id: str) -> int:
    meta = pose_video_dir(session_name, project_id, video_id) / "meta.json"
    if not meta.is_file():
        return 0
    try:
        return int(json.loads(meta.read_text(encoding="utf-8")).get("frame_count", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def load_dataset_from_source(
    session_name: str,
    project_id: str,
    video_id: str,
    source: str,
) -> tuple[LabelDataset, int]:
    """Load human labels.json or tracking.csv for a source bucket."""
    if source == "human":
        root = human_labelled_dir(session_name, project_id, video_id)
    elif source == "ai":
        root = ai_labelled_dir(session_name, project_id, video_id)
    elif source == "final":
        root = final_labelled_dir(session_name, project_id, video_id)
    elif source == "external":
        root = external_labelled_dir(session_name, project_id, video_id)
    else:
        raise ValueError(f"Unknown source: {source}")

    frame_count = _video_frame_count(session_name, project_id, video_id)
    csv_path = root / "tracking.csv"
    if csv_path.is_file():
        ds, fc, _ = import_dlc_csv(csv_path)
        if frame_count <= 0:
            frame_count = fc
        return ds, frame_count

    labels_path = root / "labels.json"
    if labels_path.is_file():
        return load_labels(root), frame_count

    return LabelDataset(), frame_count


def merge_label_datasets(*layers: LabelDataset) -> LabelDataset:
    """
    Combine datasets in order; later layers override earlier on the same frame + bodypart.

    Typical priority (low → high): external, AI, human.
    """
    active = [ds for ds in layers if ds.frames]
    if not active:
        return LabelDataset()
    if len(active) == 1:
        return deepcopy(active[0])

    bodyparts: list[str] = []
    for ds in active:
        for bp in ds.bodyparts():
            if bp not in bodyparts:
                bodyparts.append(bp)

    merged = LabelDataset(schema=deepcopy(active[-1].schema))
    merged.schema.bodyparts = bodyparts

    for ds in active:
        for fi, fl in ds.frames.items():
            for bp, xy in fl.points.items():
                if bp not in bodyparts:
                    continue
                if xy is None:
                    merged.skip_point(fi, bp)
                else:
                    merged.set_point(fi, bp, xy[0], xy[1])
    return merged


def merge_manual_over_ai(
    manual: LabelDataset,
    ai: LabelDataset,
    *,
    frame_count: int = 0,
) -> LabelDataset:
    """Combine AI then manual; manual coordinates win on conflicts."""
    _ = frame_count
    return merge_label_datasets(ai, manual)


def combine_video_datasets(
    session_name: str,
    project_id: str,
    video_id: str,
    *,
    use_human: bool = True,
    use_ai: bool = True,
    use_external: bool = False,
    scorer: str = "pose_studio",
) -> tuple[Path, Path]:
    """
    Write ``final_labelled/<video_id>/tracking.csv`` and ``provenance.json``.

    Merge priority (low → high): external, AI, human.

    Returns ``(csv_path, provenance_path)``.
    """
    base_fc = _video_frame_count(session_name, project_id, video_id)
    human_ds, human_fc = (
        load_dataset_from_source(session_name, project_id, video_id, "human")
        if use_human
        else (LabelDataset(), base_fc)
    )
    ai_ds, ai_fc = (
        load_dataset_from_source(session_name, project_id, video_id, "ai")
        if use_ai
        else (LabelDataset(), 0)
    )
    external_ds, external_fc = (
        load_dataset_from_source(session_name, project_id, video_id, "external")
        if use_external
        else (LabelDataset(), 0)
    )
    frame_count = max(base_fc, human_fc, ai_fc, external_fc)

    layers: list[LabelDataset] = []
    if use_external and external_ds.frames:
        layers.append(external_ds)
    if use_ai and ai_ds.frames:
        layers.append(ai_ds)
    if use_human and human_ds.frames:
        layers.append(human_ds)

    if not layers:
        raise ValueError("No label data available to combine for this video.")

    merged = merge_label_datasets(*layers)
    if len(layers) == 1:
        if use_external and external_ds.frames and not use_ai and not use_human:
            rule = "external_only"
        elif use_ai and ai_ds.frames and not use_human and not use_external:
            rule = "ai_only"
        elif use_human and human_ds.frames and not use_ai and not use_external:
            rule = "human_only"
        else:
            rule = "single_source"
    elif use_human and use_ai and not use_external:
        rule = "manual_over_ai"
    else:
        rule = "layered_merge"

    out_dir = final_labelled_dir(session_name, project_id, video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "tracking.csv"
    export_dlc_csv(merged, frame_count, csv_path, scorer=scorer)

    prov = {
        "video_id": video_id,
        "rule": rule,
        "sources": {
            "human": use_human,
            "ai": use_ai,
            "external": use_external,
        },
        "frame_count": frame_count,
        "labeled_frames": len(merged.frames),
        "bodyparts": merged.bodyparts(),
        "output_csv": str(csv_path),
        "merged_at": datetime.now(timezone.utc).isoformat(),
    }
    prov_path = out_dir / PROVENANCE_FILENAME
    prov_path.write_text(json.dumps(prov, indent=2), encoding="utf-8")
    return csv_path, prov_path
