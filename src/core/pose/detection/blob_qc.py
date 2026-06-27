"""Timeline QC: flag large jumps in blob crop center."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult, detect_blob_square_crop


@dataclass
class FrameBlobQC:
    frame_index: int
    center_x: float
    center_y: float
    found: bool
    jump_px: float
    flagged: bool


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
                center_x=blob.center_x,
                center_y=blob.center_y,
                found=blob.found,
                jump_px=jump,
                flagged=flagged,
            )
        )
        idx += 1
        if progress is not None:
            progress(idx, total_hint or idx)
    return results


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
            }
            for f in frames
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
