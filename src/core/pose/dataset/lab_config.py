"""Build kinematics JSON config from Pose Studio schema."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from app_platform.paths import default_sample_config, pose_analysis_settings_dir, pose_project_dir
from core.pose.labeling.labels_store import load_labels
from core.pose.labeling.schema import PoseSchema, default_lab_schema

ANALYSIS_SETTINGS_DIRNAME = "analysis/settings"


def schema_to_config_points(schema: PoseSchema) -> dict:
    """
    Map active bodypart list to the app's ``points`` config block.

    Supports the 11-point lab preset and shorter tails (e.g. T1–T3 only) from the active schema.
    """
    names = list(schema.bodyparts)
    name_set = set(names)

    def ordered(*keys: str) -> list[str]:
        return [k for k in keys if k in name_set]

    left_fin = ordered("LF1", "LF2")
    right_fin = ordered("RF1", "RF2")
    tail = ordered(
        "T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10", "ET",
    )
    spine = ordered("Head", "BF", "SB", *tail)
    if not spine:
        spine = list(names)

    head_pt1 = "Head" if "Head" in name_set else (names[0] if names else "Head")
    if "BF" in name_set:
        head_pt2 = "BF"
    elif "SB" in name_set:
        head_pt2 = "SB"
    elif len(names) > 1:
        head_pt2 = names[1]
    else:
        head_pt2 = "BF"

    if not tail:
        tail = [n for n in names if n.startswith("T")]

    return {
        "right_fin": right_fin,
        "left_fin": left_fin,
        "head": {"pt1": head_pt1, "pt2": head_pt2},
        "spine": spine,
        "tail": tail if tail else spine,
    }


def build_pose_kinematics_config(
    schema: PoseSchema,
    *,
    csv_path: str | None = None,
    base_config_path: Path | None = None,
) -> dict:
    """Return a full config dict with ``points`` from the pose schema."""
    base_path = base_config_path or default_sample_config()
    if base_path.is_file():
        config = json.loads(base_path.read_text(encoding="utf-8"))
    else:
        config = {}
    config = copy.deepcopy(config)
    config["points"] = schema_to_config_points(schema)
    if csv_path:
        config.setdefault("file_inputs", {})["data"] = csv_path
    return config


def write_pose_kinematics_config(
    session_name: str,
    project_id: str,
    video_id: str,
    schema: PoseSchema,
    *,
    csv_path: str | None = None,
    config_name: str | None = None,
) -> Path:
    """Write ``analysis/settings/<name>.json`` for a pose video."""
    out_dir = pose_analysis_settings_dir(session_name, project_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = config_name or f"{video_id}_config.json"
    if not fname.lower().endswith(".json"):
        fname += ".json"
    out_path = out_dir / fname
    config = build_pose_kinematics_config(schema, csv_path=csv_path)
    out_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return out_path


def config_from_human_labels(
    session_name: str,
    project_id: str,
    video_id: str,
    *,
    csv_path: str | None = None,
) -> tuple[Path, PoseSchema]:
    """Build config from ``human_labelled`` schema (or lab default if empty)."""
    from app_platform.paths import human_labelled_dir

    ds = load_labels(human_labelled_dir(session_name, project_id, video_id))
    schema = ds.schema if ds.bodyparts() else default_lab_schema()
    path = write_pose_kinematics_config(
        session_name,
        project_id,
        video_id,
        schema,
        csv_path=csv_path,
    )
    return path, schema
