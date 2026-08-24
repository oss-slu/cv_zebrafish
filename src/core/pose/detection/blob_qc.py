"""Timeline QC: flag blob size / volume / center-jump outliers vs video averages."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import cv2

from core.pose.cache.playback_blob_cache import PlaybackBlobEntry
from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop, mask_bbox_stats

# Outlier rules (see UI Overhaul Plan — Pre-Analyze, Video panel).
MISMATCH_SIZE_FACTOR = 2.0
MISMATCH_JUMP_FRACTION = 0.25


@dataclass
class FrameBlobQC:
    frame_index: int
    center_x: float
    center_y: float
    found: bool
    jump_px: float
    flagged: bool
    volume_px: int = 0
    length_px: int = 0
    width_px: int = 0
    crop_side: int = 0


@dataclass(frozen=True)
class BlobFrameStats:
    """Per-frame blob metrics used for mismatch detection."""

    frame_index: int
    found: bool
    center_x: float
    center_y: float
    volume_px: int
    length_px: int
    width_px: int
    crop_side: int


@dataclass(frozen=True)
class BlobAverageStats:
    volume_px: float
    length_px: float
    width_px: float
    crop_side: float


def _blob_frame_stats_from_result(frame_index: int, blob: BlobResult) -> BlobFrameStats:
    if not blob.found:
        return BlobFrameStats(frame_index, False, blob.center_x, blob.center_y, 0, 0, 0, 0)
    volume, length, width = mask_bbox_stats(blob.mask)
    return BlobFrameStats(
        frame_index,
        True,
        blob.center_x,
        blob.center_y,
        volume,
        length,
        width,
        int(blob.side),
    )


def stats_from_playback_entries(
    entries: Sequence[PlaybackBlobEntry],
    *,
    progress: Callable[[int, int], None] | None = None,
) -> list[BlobFrameStats]:
    """Build mismatch stats from Update-for-all / playback blob cache entries."""
    stats: list[BlobFrameStats] = []
    n = len(entries)
    for i, entry in enumerate(entries):
        if progress is not None and (i % 32 == 0 or i + 1 == n):
            progress(i + 1, n)
        if not entry.found:
            stats.append(BlobFrameStats(i, False, 0.0, 0.0, 0, 0, 0, 0))
            continue
        if entry.mask.size > 0 and entry.mask.any():
            volume, length, width = mask_bbox_stats(entry.mask)
        else:
            fw = max(0, entry.fish_x1 - entry.fish_x0)
            fh = max(0, entry.fish_y1 - entry.fish_y0)
            volume = fw * fh
            length = max(fw, fh)
            width = min(fw, fh) if fw and fh else 0
        cx = (entry.fish_x0 + entry.fish_x1) / 2.0
        cy = (entry.fish_y0 + entry.fish_y1) / 2.0
        stats.append(
            BlobFrameStats(
                i,
                True,
                cx,
                cy,
                int(volume),
                int(length),
                int(width),
                int(entry.crop_side),
            )
        )
    return stats


def stats_from_qc_frames(frames: Sequence[FrameBlobQC]) -> list[BlobFrameStats]:
    """Build mismatch stats from blob scan / saved blob_qc.json frames."""
    return [
        BlobFrameStats(
            f.frame_index,
            f.found,
            f.center_x,
            f.center_y,
            f.volume_px,
            f.length_px,
            f.width_px,
            f.crop_side,
        )
        for f in frames
    ]


def compute_average_stats(stats: Sequence[BlobFrameStats]) -> BlobAverageStats | None:
    """Mean blob metrics over frames where a fish was found."""
    found = [s for s in stats if s.found]
    if not found:
        return None
    n = len(found)
    return BlobAverageStats(
        sum(s.volume_px for s in found) / n,
        sum(s.length_px for s in found) / n,
        sum(s.width_px for s in found) / n,
        sum(s.crop_side for s in found) / n,
    )


def find_mismatch_frames(
    stats: Sequence[BlobFrameStats],
    *,
    averages: BlobAverageStats | None = None,
    size_factor: float = MISMATCH_SIZE_FACTOR,
    jump_fraction: float = MISMATCH_JUMP_FRACTION,
) -> list[int]:
    """
    Return sorted frame indices that violate blob QC rules vs video averages.

    Flags frames where blob volume >= size_factor * average volume,
    length or width >= size_factor * average length/width, center jumped
    > jump_fraction * average crop side vs the immediately previous frame,
    or no blob was found.
    """
    if not stats:
        return []
    avg = averages if averages is not None else compute_average_stats(stats)
    if avg is None or avg.crop_side <= 0:
        return sorted({s.frame_index for s in stats if not s.found})

    mismatches: list[int] = []
    prev: BlobFrameStats | None = None
    for s in stats:
        if not s.found:
            mismatches.append(s.frame_index)
            prev = s
            continue

        flagged = False
        if avg.volume_px > 0 and s.volume_px >= size_factor * avg.volume_px:
            flagged = True
        if avg.length_px > 0 and s.length_px >= size_factor * avg.length_px:
            flagged = True
        if avg.width_px > 0 and s.width_px >= size_factor * avg.width_px:
            flagged = True

        if prev is not None and prev.found:
            dx = s.center_x - prev.center_x
            dy = s.center_y - prev.center_y
            jump = float((dx * dx + dy * dy) ** 0.5)
            if jump > jump_fraction * avg.crop_side:
                flagged = True

        if flagged:
            mismatches.append(s.frame_index)
        prev = s

    return mismatches


def next_mismatch_frame(mismatch_frames: Sequence[int], cursor: int) -> int | None:
    """
    Return the next mismatch frame strictly after ``cursor``.

    Wraps to the first mismatch when ``cursor`` is at or after the last one.
    Returns ``None`` when ``mismatch_frames`` is empty.
    """
    ordered = sorted({int(f) for f in mismatch_frames})
    if not ordered:
        return None
    for frame_index in ordered:
        if frame_index > cursor:
            return frame_index
    return ordered[0]


def find_mismatch_frames_from_cache(
    entries: Sequence[PlaybackBlobEntry],
    *,
    progress: Callable[[int, int], None] | None = None,
    **kwargs,
) -> list[int]:
    """Prefer playback cache stats when Update-for-all cache is available."""
    return find_mismatch_frames(
        stats_from_playback_entries(entries, progress=progress),
        **kwargs,
    )


def find_mismatch_frames_from_qc(
    frames: Sequence[FrameBlobQC],
    **kwargs,
) -> list[int]:
    """Fallback mismatch detection from blob scan / blob_qc.json results."""
    return find_mismatch_frames(stats_from_qc_frames(frames), **kwargs)


def scan_video_blob_centers(
    cap,
    arena: ArenaConfig,
    params: BlobParams,
    *,
    jump_threshold_px: float = 80.0,
    max_frames: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[FrameBlobQC]:
    """Scan OpenCV VideoCapture; caller owns cap lifecycle."""
    results: list[FrameBlobQC] = []
    prev_cx, prev_cy = None, None
    total_hint = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) if hasattr(cap, "get") else 0
    if max_frames is not None and total_hint:
        total_hint = min(total_hint, max_frames)
    elif max_frames is not None:
        total_hint = max_frames
    idx = 0
    while True:
        if max_frames is not None and idx >= max_frames:
            break
        ok, frame = cap.read()
        if not ok:
            break
        blob: BlobResult = detect_blob_square_crop(frame, arena, params)
        metrics = _blob_frame_stats_from_result(idx, blob)
        jump = 0.0
        flagged = False
        if blob.found and prev_cx is not None:
            dx = blob.center_x - prev_cx
            dy = blob.center_y - prev_cy
            jump = float((dx * dx + dy * dy) ** 0.5)
            flagged = jump > jump_threshold_px
        if blob.found:
            prev_cx, prev_cy = blob.center_x, blob.center_y
        results.append(
            FrameBlobQC(
                frame_index=idx,
                center_x=metrics.center_x,
                center_y=metrics.center_y,
                found=metrics.found,
                jump_px=jump,
                flagged=flagged,
                volume_px=metrics.volume_px,
                length_px=metrics.length_px,
                width_px=metrics.width_px,
                crop_side=metrics.crop_side,
            )
        )
        idx += 1
        if progress is not None:
            progress(idx, total_hint or idx)
    return results


def load_blob_qc(path: Path) -> tuple[list[FrameBlobQC], float]:
    """Load blob_qc.json; returns (frames, jump_threshold_px)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    jump_threshold_px = float(data.get("jump_threshold_px", 80.0))
    frames = [
        FrameBlobQC(
            frame_index=int(raw["frame_index"]),
            center_x=float(raw["center_x"]),
            center_y=float(raw["center_y"]),
            found=bool(raw.get("found", False)),
            jump_px=float(raw.get("jump_px", 0.0)),
            flagged=bool(raw.get("flagged", False)),
            volume_px=int(raw.get("volume_px", 0)),
            length_px=int(raw.get("length_px", 0)),
            width_px=int(raw.get("width_px", 0)),
            crop_side=int(raw.get("crop_side", 0)),
        )
        for raw in data.get("frames", [])
    ]
    return frames, jump_threshold_px


def save_blob_qc(path: Path, frames: list[FrameBlobQC], *, jump_threshold_px: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "jump_threshold_px": jump_threshold_px,
        "frames": [
            {
                "frame_index": f.frame_index,
                "center_x": f.center_x,
                "center_y": f.center_y,
                "found": f.found,
                "jump_px": f.jump_px,
                "flagged": f.flagged,
                "volume_px": f.volume_px,
                "length_px": f.length_px,
                "width_px": f.width_px,
                "crop_side": f.crop_side,
            }
            for f in frames
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
