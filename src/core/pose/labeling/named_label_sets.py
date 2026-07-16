"""User-named label datasets under custom_labelled/<video_id>/<slug>/."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import custom_labelled_dir, custom_labelled_root
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import (
    LabelDataset,
    load_labels,
    load_schema,
    save_labels,
)
from core.pose.labeling.schema import (
    PoseSchema,
    edges_for_bodyparts,
    transfer_schema_edges,
)

META_FILENAME = "dataset_meta.json"
PROVENANCE_FILENAME = "provenance.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_dataset_name(name: str) -> str:
    slug = re.sub(r"[^\w\-]+", "_", name.strip())
    slug = slug.strip("_")
    return (slug[:64] if slug else "unnamed")


def _read_meta(label_dir: Path) -> dict:
    path = label_dir / META_FILENAME
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def read_dataset_meta(label_dir: Path) -> dict:
    return _read_meta(label_dir)


def _write_meta(label_dir: Path, data: dict) -> None:
    label_dir.mkdir(parents=True, exist_ok=True)
    (label_dir / META_FILENAME).write_text(
        json.dumps(data, indent=2),
        encoding="utf-8",
    )


def list_custom_sets(session_name: str, project_id: str, video_id: str) -> list[tuple[str, str, Path]]:
    """Return ``(slug, display_name, dir_path)`` for each custom set."""
    root = custom_labelled_root(session_name, project_id, video_id)
    if not root.is_dir():
        return []
    out: list[tuple[str, str, Path]] = []
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        meta = _read_meta(sub)
        display = str(meta.get("display_name") or sub.name)
        out.append((sub.name, display, sub))
    return out


def apply_edges_to_dataset(
    dataset: LabelDataset,
    *,
    preferred: PoseSchema | None = None,
) -> LabelDataset:
    """
    Ensure ``dataset.schema.edges`` is populated.

    Preference order: existing edges → ``preferred`` schema (remapped by name) →
    default ``edges_for_bodyparts``.
    """
    names = dataset.bodyparts()
    if not names:
        return dataset
    if dataset.schema.edges:
        return dataset
    if preferred is not None and preferred.edges:
        remapped = transfer_schema_edges(
            preferred.bodyparts,
            preferred.edges,
            names,
        )
        if remapped:
            dataset.schema.edges = remapped
            return dataset
    dataset.schema.edges = edges_for_bodyparts(names)
    return dataset


def load_dataset_from_dir(label_dir: Path) -> LabelDataset:
    """
    Load labels from a dataset directory.

    Prefer ``tracking.csv`` when present (AI / analyze / auto-label output).
    Fall back to ``labels.json`` for human-style folders.
    Sidecar ``schema.json`` supplies Label-tab bones for CSV-only folders.
    """
    labels_json = label_dir / "labels.json"
    tracking = label_dir / "tracking.csv"
    if tracking.is_file():
        ds, _, _ = import_dlc_csv(tracking)
        return apply_edges_to_dataset(ds, preferred=load_schema(label_dir))
    if labels_json.is_file():
        return load_labels(label_dir)
    raise FileNotFoundError(f"No labels in {label_dir}")


def save_named_set(
    session_name: str,
    project_id: str,
    video_id: str,
    display_name: str,
    dataset: LabelDataset,
    *,
    frame_count: int,
    loaded_from: str | None = None,
    slug: str | None = None,
) -> Path:
    """Write labels.json + tracking.csv + metadata to a named custom set."""
    target_slug = slug or slugify_dataset_name(display_name)
    dest = custom_labelled_dir(session_name, project_id, video_id, target_slug)
    meta = _read_meta(dest)
    if not meta:
        meta = {
            "display_name": display_name,
            "slug": target_slug,
            "created": _utc_now(),
        }
    meta["display_name"] = display_name
    meta["slug"] = target_slug
    meta["updated"] = _utc_now()
    if loaded_from:
        meta["loaded_from"] = loaded_from
    save_labels(dest, deepcopy(dataset))
    _write_meta(dest, meta)
    if frame_count > 0:
        export_dlc_csv(dataset, frame_count, dest / "tracking.csv")
    prov = {
        "display_name": display_name,
        "updated": meta["updated"],
    }
    if loaded_from:
        prov["loaded_from"] = loaded_from
    (dest / PROVENANCE_FILENAME).write_text(
        json.dumps(prov, indent=2),
        encoding="utf-8",
    )
    return dest
