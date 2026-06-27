"""Normalize session videos to H.264 MP4 for reliable seeking and playback."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import cv2

from core.pose.video.video_registry import _open_video_capture, _suppress_ffmpeg_stderr, probe_video

ProgressFn = Callable[[str, int, int], None] | None
# message, current (-1 if unknown), total (-1 if unknown)

# Containers/codecs that are slow or unreliable with OpenCV random access.
_TRANSCODE_EXTENSIONS = {".avi", ".mov", ".mkv", ".mjpeg", ".mjpg"}
_PREFERRED_SUFFIX = ".mp4"


def _emit_progress(
    progress: ProgressFn,
    msg: str,
    current: int = -1,
    total: int = -1,
) -> None:
    if progress is not None:
        progress(msg, current, total)


def find_ffmpeg_exe() -> Path | None:
    """Return an ffmpeg binary from PATH or optional imageio-ffmpeg bundle."""
    found = shutil.which("ffmpeg")
    if found:
        return Path(found)
    try:
        import imageio_ffmpeg  # type: ignore[import-untyped]

        return Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return None


def find_ffprobe_exe() -> Path | None:
    """Return ffprobe from PATH or beside the imageio-ffmpeg bundle."""
    found = shutil.which("ffprobe")
    if found:
        return Path(found)
    ffmpeg = find_ffmpeg_exe()
    if ffmpeg is None:
        return None
    sibling = ffmpeg.parent / f"ffprobe{ffmpeg.suffix}"
    return sibling if sibling.is_file() else None


def probe_frame_count_fast(path: Path) -> int:
    """Read frame count from container metadata without decoding the whole file."""
    ffprobe = find_ffprobe_exe()
    if ffprobe is None:
        return 0
    path = path.resolve()
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_frames,duration,r_frame_rate",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(proc.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return 0
        stream = streams[0]
        nb = int(stream.get("nb_frames") or 0)
        if nb > 0:
            return nb
        duration = float(stream.get("duration") or 0.0)
        rate = str(stream.get("r_frame_rate") or "0/1")
        if "/" in rate:
            num, den = rate.split("/", 1)
            fps = float(num) / float(den) if float(den) else 0.0
        else:
            fps = float(rate)
        if duration > 0 and fps > 0:
            return max(1, int(round(duration * fps)))
    except Exception:
        return 0
    return 0


def probe_video_codec_fast(path: Path) -> str:
    """Return video codec name from ffprobe without opening OpenCV."""
    ffprobe = find_ffprobe_exe()
    if ffprobe is None:
        return ""
    cmd = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return (proc.stdout or "").strip().lower()
    except Exception:
        return ""


def _fourcc_name(cap: cv2.VideoCapture) -> str:
    v = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00").lower()


def needs_transcode(path: Path) -> bool:
    """True when the file should be converted to H.264 MP4 for in-app playback."""
    path = path.resolve()
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext in _TRANSCODE_EXTENSIONS:
        return True
    if ext != ".mp4":
        return True
    codec = probe_video_codec_fast(path)
    if codec:
        if codec in {"h264", "avc1", "x264"}:
            return False
        return codec in {"mjpeg", "mjpg", "mpeg4", "mp4v", "xvid", "divx"}
    with _suppress_ffmpeg_stderr():
        cap = _open_video_capture(path)
        if not cap.isOpened():
            return False
        try:
            codec = _fourcc_name(cap)
        finally:
            cap.release()
    # OpenCV fourcc tags vary: avc1, h264, x264 are fine; mjpeg, mp4v less ideal for seek.
    if codec in {"", "h264", "avc1", "x264"}:
        return False
    return codec in {"mjpg", "mjpeg", "mp4v", "xvid", "divx", "fvfw"}


def transcode_to_h264_mp4(
    src: Path,
    dest: Path,
    *,
    progress: ProgressFn = None,
) -> None:
    """Write an H.264 MP4 (yuv420p, faststart). Raises if conversion fails."""
    src = src.resolve()
    dest = dest.resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest == src:
        return

    ffmpeg = find_ffmpeg_exe()
    if ffmpeg is not None:
        _transcode_with_ffmpeg(ffmpeg, src, dest, progress=progress)
        return

    _emit_progress(
        progress,
        "ffmpeg not found — re-encoding with OpenCV (install ffmpeg for faster H.264)…",
    )
    _transcode_with_opencv(src, dest, progress=progress)


def _transcode_with_ffmpeg(
    ffmpeg: Path,
    src: Path,
    dest: Path,
    *,
    progress: ProgressFn,
) -> None:
    total_frames = probe_frame_count_fast(src)
    if total_frames <= 0:
        try:
            total_frames = max(1, probe_video(src).frame_count)
        except Exception:
            total_frames = 0

    _emit_progress(
        progress,
        f"Re-encoding {src.name} to H.264 MP4…",
        0,
        total_frames if total_frames > 0 else -1,
    )
    cmd = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-nostats",
        "-i",
        str(src),
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(dest),
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    frame_idx = 0
    assert proc.stdout is not None
    while True:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        line = line.strip()
        if not line.startswith("frame="):
            continue
        try:
            frame_idx = int(line.split("=", 1)[1])
        except ValueError:
            continue
        if progress:
            if total_frames > 0:
                _emit_progress(
                    progress,
                    f"Re-encoding… {frame_idx}/{total_frames}",
                    frame_idx,
                    total_frames,
                )
            else:
                _emit_progress(progress, f"Re-encoding… frame {frame_idx}")

    err = proc.stderr.read() if proc.stderr is not None else ""
    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg failed to transcode {src.name}: {err.strip() or code}")
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg produced an empty file: {dest}")
    if total_frames > 0:
        _emit_progress(progress, "Re-encoding complete", total_frames, total_frames)


def _transcode_with_opencv(
    src: Path,
    dest: Path,
    *,
    progress: ProgressFn,
) -> None:
    if dest.exists():
        dest.unlink()
    with _suppress_ffmpeg_stderr():
        cap = _open_video_capture(src)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video for re-encode: {src}")
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0) or 30.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            raise RuntimeError(f"Could not read first frame for re-encode: {src}")
        if w <= 0 or h <= 0:
            h, w = frame.shape[:2]
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) or 1
        writer = None
        for fourcc_str in ("avc1", "H264", "mp4v"):
            candidate = cv2.VideoWriter(
                str(dest),
                cv2.VideoWriter_fourcc(*fourcc_str),
                fps,
                (w, h),
            )
            if candidate.isOpened():
                writer = candidate
                break
            candidate.release()
        if writer is None:
            cap.release()
            raise RuntimeError(f"Could not create MP4 writer for {dest}")
        try:
            idx = 0
            while True:
                if idx == 0:
                    current = frame
                else:
                    ok, current = cap.read()
                    if not ok or current is None:
                        break
                if current.shape[1] != w or current.shape[0] != h:
                    current = cv2.resize(current, (w, h), interpolation=cv2.INTER_AREA)
                writer.write(current)
                idx += 1
                if progress and (idx == 1 or idx % 30 == 0 or idx >= total):
                    _emit_progress(
                        progress,
                        f"Re-encoding… {idx}/{total}",
                        idx,
                        total,
                    )
        finally:
            cap.release()
            writer.release()
    if not dest.is_file() or dest.stat().st_size == 0:
        raise RuntimeError(f"OpenCV re-encode produced an empty file: {dest}")


def normalize_playback_path(
    src: Path,
    video_dir: Path,
    *,
    progress: ProgressFn = None,
) -> Path:
    """
    Ensure ``video_dir/source.mp4`` exists for playback.

    Returns the path to use for OpenCV reads (usually ``source.mp4``).
    """
    src = src.resolve()
    video_dir = video_dir.resolve()
    dest = video_dir / f"source{_PREFERRED_SUFFIX}"

    if dest.is_file() and dest.stat().st_size > 0:
        if src == dest or not needs_transcode(src):
            return dest

    if not needs_transcode(src):
        if src == dest or (src.parent == video_dir and src.suffix.lower() == _PREFERRED_SUFFIX):
            return src
        _emit_progress(progress, f"Copying {src.name}…")
        shutil.copy2(src, dest)
        return dest

    _emit_progress(progress, f"Preparing H.264 MP4 from {src.name}…", 0, -1)
    transcode_to_h264_mp4(src, dest, progress=progress)

    # Drop a superseded session copy once H.264 exists beside it.
    if (
        src.parent == video_dir
        and src != dest
        and src.name.startswith("source.")
        and src.suffix.lower() != _PREFERRED_SUFFIX
    ):
        try:
            src.unlink()
        except OSError:
            pass
    return dest


def migrate_legacy_playback(video_dir: Path, *, progress: ProgressFn = None) -> Path | None:
    """If the folder only has a legacy ``source.*`` file, transcode to ``source.mp4``."""
    video_dir = video_dir.resolve()
    preferred = video_dir / f"source{_PREFERRED_SUFFIX}"
    if preferred.is_file():
        return preferred
    for p in sorted(video_dir.glob("source.*")):
        if p.suffix.lower() == ".json" or not p.is_file():
            continue
        if needs_transcode(p):
            return normalize_playback_path(p, video_dir, progress=progress)
        return p
    return None
