"""Merge pose label datasets (manual wins over AI)."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import (
    ai_labelled_dir,
    custom_labelled_dir,
    external_labelled_dir,
    final_labelled_dir,
    human_labelled_dir,
    pose_video_dir,
)
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import LabelDataset, load_labels

PROVENANCE_FILENAME = "provenance.json"

# Default merge stack when callers pass boolean flags (low → high).
_DEFAULT_FLAG_ORDER = ("external", "ai", "human")


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
    """Load labels.json or tracking.csv for a source key (``human``, ``ai``, ``custom:slug``, …)."""
    if source == "human":
        root = human_labelled_dir(session_name, project_id, video_id)
    elif source == "ai":
        root = ai_labelled_dir(session_name, project_id, video_id)
    elif source == "final":
        root = final_labelled_dir(session_name, project_id, video_id)
    elif source == "external":
        root = external_labelled_dir(session_name, project_id, video_id)
    elif source.startswith("custom:"):
        slug = source.split(":", 1)[1].strip()
        if not slug:
            raise ValueError("Custom source requires a slug (custom:<slug>).")
        root = custom_labelled_dir(session_name, project_id, video_id, slug)
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


def _sources_from_flags(
    *,
    use_human: bool,
    use_ai: bool,
    use_external: bool,
) -> list[str]:
    selected = {
        "human": use_human,
        "ai": use_ai,
        "external": use_external,
    }
    return [key for key in _DEFAULT_FLAG_ORDER if selected.get(key)]


def combine_video_datasets(
    session_name: str,
    project_id: str,
    video_id: str,
    *,
    use_human: bool = True,
    use_ai: bool = True,
    use_external: bool = False,
    sources_low_to_high: list[str] | None = None,
    scorer: str = "pose_studio",
) -> tuple[Path, Path]:
    """
    Write ``final_labelled/<video_id>/tracking.csv`` and ``provenance.json``.

    Merge priority is **low → high** in ``sources_low_to_high`` (later overwrites earlier).
    When ``sources_low_to_high`` is omitted, boolean flags use external → AI → human.

    Returns ``(csv_path, provenance_path)``.
    """
    if sources_low_to_high is None:
        source_keys = _sources_from_flags(
            use_human=use_human,
            use_ai=use_ai,
            use_external=use_external,
        )
    else:
        source_keys = [str(s).strip() for s in sources_low_to_high if str(s).strip()]

    if not source_keys:
        raise ValueError("Select at least one dataset source to merge.")

    base_fc = _video_frame_count(session_name, project_id, video_id)
    layers: list[LabelDataset] = []
    used_keys: list[str] = []
    frame_count = base_fc

    for key in source_keys:
        ds, fc = load_dataset_from_source(session_name, project_id, video_id, key)
        frame_count = max(frame_count, fc)
        if ds.frames:
            layers.append(ds)
            used_keys.append(key)

    if not layers:
        raise ValueError("No label data available to combine for this video.")

    merged = merge_label_datasets(*layers)
    if len(used_keys) == 1:
        rule = f"{used_keys[0]}_only"
    elif used_keys == ["ai", "human"]:
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
        "sources_low_to_high": used_keys,
        "sources": {
            "human": "human" in used_keys,
            "ai": "ai" in used_keys,
            "external": "external" in used_keys,
            "final": "final" in used_keys,
            "custom": [k for k in used_keys if k.startswith("custom:")],
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
