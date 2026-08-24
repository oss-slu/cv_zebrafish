"""Persist human labels and schema under human_labelled/<video_id>/."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.pose.labeling.schema import (
    PoseSchema,
    apply_canonical_schema,
    canonical_lab_schema,
    default_lab_schema,
)

LABELS_FILENAME = "labels.json"
SCHEMA_FILENAME = "schema.json"
MANIFEST_FILENAME = "labels_manifest.json"


@dataclass
class FrameLabels:
    """Per-frame bodypart coordinates in full-frame pixel space."""

    points: dict[str, tuple[float, float] | None] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, xy in self.points.items():
            if xy is None:
                out[name] = None
            else:
                out[name] = {"x": xy[0], "y": xy[1]}
        return out

    @classmethod
    def from_dict(cls, raw: dict | None) -> "FrameLabels":
        pts: dict[str, tuple[float, float] | None] = {}
        for name, val in (raw or {}).items():
            if val is None:
                pts[name] = None
            elif isinstance(val, dict) and "x" in val and "y" in val:
                pts[name] = (float(val["x"]), float(val["y"]))
        return cls(points=pts)


@dataclass
class LabelDataset:
    schema: PoseSchema = field(default_factory=default_lab_schema)
    frames: dict[int, FrameLabels] = field(default_factory=dict)
    gap: int = 15
    frames_to_analyze: int = 300
    label_frame_queue: list[int] = field(default_factory=list)

    def bodyparts(self) -> list[str]:
        return list(self.schema.bodyparts)

    def set_point(self, frame_index: int, bodypart: str, x: float, y: float) -> None:
        fl = self.frames.setdefault(frame_index, FrameLabels())
        fl.points[bodypart] = (x, y)

    def skip_point(self, frame_index: int, bodypart: str) -> None:
        fl = self.frames.setdefault(frame_index, FrameLabels())
        fl.points[bodypart] = None

    def clear_point(self, frame_index: int, bodypart: str) -> None:
        fl = self.frames.get(frame_index)
        if fl and bodypart in fl.points:
            del fl.points[bodypart]

    def get_point(self, frame_index: int, bodypart: str) -> tuple[float, float] | None:
        fl = self.frames.get(frame_index)
        if not fl:
            return None
        return fl.points.get(bodypart)

    def count_for_bodypart(self, bodypart: str) -> int:
        n = 0
        for fl in self.frames.values():
            if bodypart in fl.points and fl.points[bodypart] is not None:
                n += 1
        return n

    def count_frames_with_any_point(self) -> int:
        """Frames that have at least one non-null bodypart coordinate."""
        n = 0
        for fl in self.frames.values():
            if any(xy is not None for xy in fl.points.values()):
                n += 1
        return n

    def to_dict(self) -> dict:
        return {
            "gap": self.gap,
            "frames_to_analyze": self.frames_to_analyze,
            "label_frame_queue": list(self.label_frame_queue),
            "schema": self.schema.to_dict(),
            "frames": {str(k): v.to_dict() for k, v in sorted(self.frames.items())},
        }

    @classmethod
    def from_dict(cls, raw: dict | None) -> "LabelDataset":
        if not raw:
            return cls()
        schema = PoseSchema.from_dict(raw.get("schema"))
        frames: dict[int, FrameLabels] = {}
        for k, v in (raw.get("frames") or {}).items():
            frames[int(k)] = FrameLabels.from_dict(v)
        gap = int(raw.get("gap", 15))
        frames_raw = raw.get("frames_to_analyze")
        frames_to_analyze = int(frames_raw) if frames_raw is not None else 0
        queue_raw = raw.get("label_frame_queue") or []
        label_frame_queue = [int(x) for x in queue_raw]
        return cls(
            schema=schema,
            frames=frames,
            gap=gap,
            frames_to_analyze=frames_to_analyze,
            label_frame_queue=label_frame_queue,
        )


def labels_path(label_dir: Path) -> Path:
    return label_dir / LABELS_FILENAME


def schema_path(label_dir: Path) -> Path:
    return label_dir / SCHEMA_FILENAME


def load_schema(label_dir: Path) -> PoseSchema | None:
    """Load sidecar ``schema.json`` if present (used beside tracking.csv)."""
    path = schema_path(label_dir)
    if not path.is_file():
        return None
    try:
        return PoseSchema.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def save_schema(label_dir: Path, schema: PoseSchema) -> None:
    """Persist bodyparts + bone edges beside a tracking CSV dataset."""
    label_dir.mkdir(parents=True, exist_ok=True)
    schema_path(label_dir).write_text(
        json.dumps(schema.to_dict(), indent=2),
        encoding="utf-8",
    )


def load_labels(label_dir: Path) -> LabelDataset:
    p = labels_path(label_dir)
    if not p.is_file():
        ds = LabelDataset(schema=canonical_lab_schema())
        save_labels(label_dir, ds)
        return ds
    ds = LabelDataset.from_dict(json.loads(p.read_text(encoding="utf-8")))
    return apply_canonical_schema(ds)


def save_labels(label_dir: Path, dataset: LabelDataset) -> None:
    label_dir.mkdir(parents=True, exist_ok=True)
    labels_path(label_dir).write_text(
        json.dumps(dataset.to_dict(), indent=2),
        encoding="utf-8",
    )
    save_schema(label_dir, dataset.schema)
    manifest = {
        "bodyparts": dataset.bodyparts(),
        "labeled_frame_count": len(dataset.frames),
        "per_bodypart": {bp: dataset.count_for_bodypart(bp) for bp in dataset.bodyparts()},
    }
    (label_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
