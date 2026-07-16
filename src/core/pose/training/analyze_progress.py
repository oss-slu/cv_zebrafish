"""Frame totals and helpers for DLC analyze progress."""

from __future__ import annotations

from pathlib import Path

from app_platform.paths import pose_video_dir
from core.pose.video.video_registry import read_video_meta, resolve_video_source


def total_analyze_frames(job: dict) -> int:
    """Sum frame counts for all videos listed in a train/analyze job."""
    session_name = str(job["session_name"])
    project_id = str(job["project_id"])
    video_ids: list[str] = list(job.get("video_ids") or [])
    video_sources: list[str] = list(job.get("video_sources") or [])
    total = 0
    for index, video_id in enumerate(video_ids):
        source = video_sources[index] if index < len(video_sources) else None
        if source:
            path = Path(source)
            if path.is_file():
                try:
                    import cv2

                    cap = cv2.VideoCapture(str(path))
                    if cap.isOpened():
                        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        cap.release()
                        if n > 0:
                            total += n
                            continue
                except Exception:
                    pass
        meta = read_video_meta(pose_video_dir(session_name, project_id, video_id))
        if meta and meta.frame_count > 0:
            total += int(meta.frame_count)
    return total
