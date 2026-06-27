"""Register videos into a pose project (copy or reference)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import cv2

from app_platform.paths import pose_video_dir

LARGE_FILE_WARNING_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


@dataclass
class VideoMeta:
    fps: float
    frame_count: int
    width: int
    height: int
    source_policy: str

    def to_dict(self) -> dict:
        return {
            "fps": self.fps,
            "frame_count": self.frame_count,
            "width": self.width,
            "height": self.height,
            "source_policy": self.source_policy,
        }


def slugify_video_id(stem: str, existing: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", stem).strip("_").lower() or "video"
    if base not in existing:
        return base
    n = 2
    while f"{base}_{n}" in existing:
        n += 1
    return f"{base}_{n}"


@contextlib.contextmanager
def _suppress_ffmpeg_stderr():
    """FFmpeg logs MJPEG decode issues directly to fd 2 during OpenCV probes."""
    try:
        stderr_fd = os.dup(2)
    except OSError:
        yield
        return
    try:
        with open(os.devnull, "w", encoding="utf-8") as devnull:
            os.dup2(devnull.fileno(), 2)
            try:
                yield
            finally:
                os.dup2(stderr_fd, 2)
    finally:
        os.close(stderr_fd)


def _open_video_capture(path: Path) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    if not cap.isOpened():
        cap = cv2.VideoCapture(str(path))
    return cap


def _probe_frame_count(cap: cv2.VideoCapture) -> int:
    """Best-effort frame count without scanning the whole file on MJPEG/AVI."""
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    return n if n > 0 else 1


def probe_video(path: Path) -> VideoMeta:
    with _suppress_ffmpeg_stderr():
        old_log = cv2.getLogLevel()
        cv2.setLogLevel(0)
        cap = _open_video_capture(path)
        if not cap.isOpened():
            cv2.setLogLevel(old_log)
            raise ValueError(f"Could not open video: {path}")
        try:
            ok, frame = cap.read()
            if not ok or frame is None:
                raise ValueError(
                    f"Could not decode video (first frame failed). "
                    f"The file may use an unsupported codec (e.g. MJPEG in AVI): {path}"
                )
            height, width = frame.shape[:2]
            prop_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            prop_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if prop_w > 0:
                width = prop_w
            if prop_h > 0:
                height = prop_h
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = _probe_frame_count(cap)
        finally:
            cap.release()
            cv2.setLogLevel(old_log)
    return VideoMeta(
        fps=fps,
        frame_count=frame_count,
        width=width,
        height=height,
        source_policy="",
    )


def resolve_video_source(video_dir: Path) -> Path | None:
    """Return readable video path for a registered video folder."""
    preferred = video_dir / "source.mp4"
    if preferred.is_file():
        return preferred
    for p in sorted(video_dir.glob("source.*")):
        if p.suffix.lower() in {".json"}:
            continue
        if p.is_file():
            return p
    ref = video_dir / "source.ref.json"
    if ref.is_file():
        data = json.loads(ref.read_text(encoding="utf-8"))
        orig = Path(data.get("path", ""))
        if orig.is_file():
            return orig
    return None


def register_video(
    session_name: str,
    project_id: str,
    source_path: Path,
    *,
    policy: str,
    existing_video_ids: set[str],
    progress: Callable[[str, int, int], None] | None = None,
) -> tuple[str, VideoMeta]:
    """
    Register one video under pose_projects/<project_id>/videos/<video_id>/.

    policy: ``copy`` | ``reference``
    """
    source_path = source_path.resolve()
    if not source_path.is_file():
        raise ValueError(f"Video file not found: {source_path}")

    video_id = slugify_video_id(source_path.stem, existing_video_ids)
    vdir = pose_video_dir(session_name, project_id, video_id)
    vdir.mkdir(parents=True, exist_ok=True)

    if policy == "copy":
        staging = vdir / f"source_upload{source_path.suffix.lower()}"
        if staging.resolve() != source_path:
            if progress:
                progress(f"Copying {source_path.name}…", -1, -1)
            shutil.copy2(source_path, staging)
            if staging.stat().st_size != source_path.stat().st_size:
                raise ValueError(
                    f"Copy incomplete for {source_path.name} "
                    f"({staging.stat().st_size} bytes vs {source_path.stat().st_size} expected)."
                )
            ingest_src = staging
        else:
            ingest_src = source_path
        from core.pose.video.video_transcode import normalize_playback_path

        playback = normalize_playback_path(ingest_src, vdir, progress=progress)
        if ingest_src != playback and ingest_src != source_path:
            try:
                ingest_src.unlink()
            except OSError:
                pass
        meta_policy = "copy"
    elif policy == "reference":
        ref = {
            "path": str(source_path),
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        (vdir / "source.ref.json").write_text(json.dumps(ref, indent=2), encoding="utf-8")
        from core.pose.video.video_transcode import normalize_playback_path

        playback = normalize_playback_path(source_path, vdir, progress=progress)
        meta_policy = "reference"
    else:
        raise ValueError(f"Unknown video policy: {policy}")

    meta = probe_video(playback)
    meta.source_policy = meta_policy
    (vdir / "meta.json").write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
    return video_id, meta


def read_video_meta(video_dir: Path) -> VideoMeta | None:
    p = video_dir / "meta.json"
    if not p.is_file():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    return VideoMeta(
        fps=float(d.get("fps", 0)),
        frame_count=int(d.get("frame_count", 0)),
        width=int(d.get("width", 0)),
        height=int(d.get("height", 0)),
        source_policy=str(d.get("source_policy", "")),
    )
