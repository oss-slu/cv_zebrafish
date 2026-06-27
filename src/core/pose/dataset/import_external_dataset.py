"""Import external DLC CSV into pose project external_labelled/."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app_platform.paths import external_labelled_dir, pose_video_dir
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv

IMPORT_META_FILENAME = "import_meta.json"


def _video_frame_count(session_name: str, project_id: str, video_id: str) -> int:
    meta = pose_video_dir(session_name, project_id, video_id) / "meta.json"
    if not meta.is_file():
        return 0
    try:
        return int(json.loads(meta.read_text(encoding="utf-8")).get("frame_count", 0))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return 0


def import_external_dlc_csv(
    session_name: str,
    project_id: str,
    video_id: str,
    source_csv: Path,
    *,
    scorer: str = "external",
) -> Path:
    """
    Copy a DLC-shaped CSV into ``external_labelled/<video_id>/tracking.csv``.

    Re-exports through the app's DLC parser so column layout is normalized.
    Returns the destination CSV path.
    """
    source_csv = Path(source_csv)
    if not source_csv.is_file():
        raise FileNotFoundError(f"CSV not found: {source_csv}")

    ds, csv_frame_count, bodyparts = import_dlc_csv(source_csv)
    frame_count = max(csv_frame_count, _video_frame_count(session_name, project_id, video_id))

    out_dir = external_labelled_dir(session_name, project_id, video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "tracking.csv"
    export_dlc_csv(ds, frame_count, dest, scorer=scorer)

    meta = {
        "video_id": video_id,
        "source_path": str(source_csv.resolve()),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "bodyparts": bodyparts,
        "labeled_frames": len(ds.frames),
        "frame_count": frame_count,
        "output_csv": str(dest),
    }
    (out_dir / IMPORT_META_FILENAME).write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )

    # Keep a copy of the original filename for traceability.
    sidecar = out_dir / f"original_{source_csv.name}"
    if not sidecar.exists():
        shutil.copy2(source_csv, sidecar)

    return dest
