"""Compact per-frame blob snapshots for smooth Arena & Blob playback."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, BlobResult
from core.pose.labeling.pose_scan_cache import video_token

PLAYBACK_OVERLAY_VERSION = 1
PLAYBACK_OVERLAY_META = "playback_overlay_cache.json"
PLAYBACK_OVERLAY_DATA = "playback_overlay_cache.npz"


@dataclass(frozen=True)
class PlaybackBlobEntry:
    """Blob overlay at preview resolution (mask + crop geometry)."""

    found: bool
    fish_x0: int
    fish_y0: int
    fish_x1: int
    fish_y1: int
    crop_x0: int
    crop_y0: int
    crop_side: int
    mask: np.ndarray

    @classmethod
    def empty(cls) -> "PlaybackBlobEntry":
        return cls(False, 0, 0, 0, 0, 0, 0, 0, np.zeros((0, 0), dtype=bool))

    @classmethod
    def from_blob(cls, blob: BlobResult) -> "PlaybackBlobEntry":
        if not blob.found:
            return cls.empty()
        ys, xs = np.where(blob.mask)
        if xs.size == 0:
            return cls.empty()
        return cls(
            True,
            int(xs.min()),
            int(ys.min()),
            int(xs.max()) + 1,
            int(ys.max()) + 1,
            int(blob.x0),
            int(blob.y0),
            int(blob.side),
            blob.mask.astype(bool, copy=True),
        )

    def to_blob_result(self) -> BlobResult:
        if not self.found or self.mask.size == 0:
            return BlobResult(
                mask=np.zeros((1, 1), dtype=bool),
                center_x=0.0,
                center_y=0.0,
                side=0,
                x0=0,
                y0=0,
                x1=0,
                y1=0,
                found=False,
            )
        cx = (self.fish_x0 + self.fish_x1) / 2.0
        cy = (self.fish_y0 + self.fish_y1) / 2.0
        return BlobResult(
            mask=self.mask,
            center_x=cx,
            center_y=cy,
            side=self.crop_side,
            x0=self.crop_x0,
            y0=self.crop_y0,
            x1=self.crop_x0 + self.crop_side,
            y1=self.crop_y0 + self.crop_side,
            found=True,
        )


def playback_blob_cache_key(arena: ArenaConfig, params: BlobParams) -> str:
    payload = {
        "arena": arena.to_dict(),
        "blob": params.to_dict(),
        "cache_version": 2,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _entries_to_arrays(
    entries: list[PlaybackBlobEntry],
) -> tuple[int, int, dict[str, np.ndarray]]:
    n = len(entries)
    mask_h = mask_w = 0
    for entry in entries:
        if entry.found and entry.mask.size > 0:
            mask_h, mask_w = entry.mask.shape[:2]
            break
    found = np.zeros(n, dtype=bool)
    fish_x0 = np.zeros(n, dtype=np.int32)
    fish_y0 = np.zeros(n, dtype=np.int32)
    fish_x1 = np.zeros(n, dtype=np.int32)
    fish_y1 = np.zeros(n, dtype=np.int32)
    crop_x0 = np.zeros(n, dtype=np.int32)
    crop_y0 = np.zeros(n, dtype=np.int32)
    crop_side = np.zeros(n, dtype=np.int32)
    masks = (
        np.zeros((n, mask_h, mask_w), dtype=np.uint8)
        if mask_h > 0 and mask_w > 0
        else np.zeros((n, 0, 0), dtype=np.uint8)
    )
    for i, entry in enumerate(entries):
        found[i] = entry.found
        fish_x0[i] = entry.fish_x0
        fish_y0[i] = entry.fish_y0
        fish_x1[i] = entry.fish_x1
        fish_y1[i] = entry.fish_y1
        crop_x0[i] = entry.crop_x0
        crop_y0[i] = entry.crop_y0
        crop_side[i] = entry.crop_side
        if entry.found and entry.mask.size > 0 and masks.size > 0:
            masks[i] = entry.mask.astype(np.uint8)
    return mask_h, mask_w, {
        "found": found,
        "fish_x0": fish_x0,
        "fish_y0": fish_y0,
        "fish_x1": fish_x1,
        "fish_y1": fish_y1,
        "crop_x0": crop_x0,
        "crop_y0": crop_y0,
        "crop_side": crop_side,
        "masks": masks,
    }


def _entries_from_arrays(data: dict[str, np.ndarray]) -> list[PlaybackBlobEntry]:
    found = data["found"]
    n = int(found.shape[0])
    masks = data.get("masks")
    entries: list[PlaybackBlobEntry] = []
    for i in range(n):
        if not bool(found[i]):
            entries.append(PlaybackBlobEntry.empty())
            continue
        if masks is not None and masks.size > 0:
            mask = masks[i].astype(bool)
        else:
            mask = np.zeros((0, 0), dtype=bool)
        entries.append(
            PlaybackBlobEntry(
                True,
                int(data["fish_x0"][i]),
                int(data["fish_y0"][i]),
                int(data["fish_x1"][i]),
                int(data["fish_y1"][i]),
                int(data["crop_x0"][i]),
                int(data["crop_y0"][i]),
                int(data["crop_side"][i]),
                mask,
            )
        )
    return entries


def load_playback_overlay_cache(
    video_dir: Path,
    *,
    frame_count: int,
    video_path: Path,
    arena: ArenaConfig,
    blob_params: BlobParams,
    preview_max_edge: int,
) -> list[PlaybackBlobEntry] | None:
    """Load cached playback overlays from the video folder, if settings still match."""
    video_dir = video_dir.resolve()
    meta_path = video_dir / PLAYBACK_OVERLAY_META
    data_path = video_dir / PLAYBACK_OVERLAY_DATA
    if not meta_path.is_file() or not data_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if int(meta.get("version", 0)) != PLAYBACK_OVERLAY_VERSION:
            return None
        if int(meta.get("frame_count", -1)) != int(frame_count):
            return None
        if int(meta.get("preview_max_edge", -1)) != int(preview_max_edge):
            return None
        if meta.get("settings_hash") != playback_blob_cache_key(arena, blob_params):
            return None
        if meta.get("video_token") != video_token(video_path):
            return None
        data = np.load(data_path)
        entries = _entries_from_arrays(dict(data))
        if len(entries) < frame_count:
            return None
        return entries[:frame_count]
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def save_playback_overlay_cache(
    video_dir: Path,
    entries: list[PlaybackBlobEntry],
    *,
    frame_count: int,
    video_path: Path,
    arena: ArenaConfig,
    blob_params: BlobParams,
    preview_max_edge: int,
) -> None:
    """Persist playback overlays beside the video for reuse across sessions."""
    video_dir.mkdir(parents=True, exist_ok=True)
    mask_h, mask_w, arrays = _entries_to_arrays(entries)
    np.savez_compressed(video_dir / PLAYBACK_OVERLAY_DATA, **arrays)
    meta = {
        "version": PLAYBACK_OVERLAY_VERSION,
        "frame_count": int(frame_count),
        "preview_max_edge": int(preview_max_edge),
        "mask_h": mask_h,
        "mask_w": mask_w,
        "settings_hash": playback_blob_cache_key(arena, blob_params),
        "video_token": video_token(video_path),
    }
    (video_dir / PLAYBACK_OVERLAY_META).write_text(
        json.dumps(meta, indent=2),
        encoding="utf-8",
    )
