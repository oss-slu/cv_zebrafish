"""Persist blob-shape fingerprints and diverse labeling queues on disk."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams

SCAN_CACHE_VERSION = 1
SCAN_CACHE_META = "pose_scan_cache.json"
SCAN_CACHE_DATA = "pose_scan_cache.npz"
_FINGERPRINT_DIM = 32 * 32


@dataclass
class PoseScanCache:
    fingerprints: list[np.ndarray | None]
    queues_by_gap: dict[int, list[int]]
    queues_by_target: dict[int, list[int]]
    coarse_stride: int
    fingerprints_loaded: bool = True
    last_frames_to_analyze: int = 0
    last_queue: list[int] = field(default_factory=list)


def scan_settings_hash(
    arena: ArenaConfig,
    blob_params: BlobParams,
) -> str:
    payload = json.dumps(
        {
            "arena": arena.to_dict(),
            "blob": blob_params.to_dict(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def video_token(video_path: Path) -> str:
    stat = video_path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _sparse_from_fingerprints(fingerprints: list[np.ndarray | None]) -> tuple[np.ndarray, np.ndarray]:
    indices: list[int] = []
    vectors: list[np.ndarray] = []
    for i, fp in enumerate(fingerprints):
        if fp is None:
            continue
        indices.append(i)
        vectors.append(np.asarray(fp, dtype=np.float32).reshape(-1))
    if not indices:
        return np.zeros(0, dtype=np.int32), np.zeros((0, _FINGERPRINT_DIM), dtype=np.float32)
    return np.asarray(indices, dtype=np.int32), np.vstack(vectors)


def _fingerprints_from_sparse(
    frame_count: int,
    indices: np.ndarray,
    vectors: np.ndarray,
) -> list[np.ndarray | None]:
    out: list[np.ndarray | None] = [None] * frame_count
    for i, vec in zip(indices.tolist(), vectors):
        if 0 <= i < frame_count:
            out[i] = np.asarray(vec, dtype=np.float32)
    return out


def _read_scan_cache_meta(
    meta_path: Path,
    *,
    frame_count: int,
    video_path: Path,
    arena: ArenaConfig,
    blob_params: BlobParams,
) -> dict | None:
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if int(meta.get("version", 0)) != SCAN_CACHE_VERSION:
            return None
        if int(meta.get("frame_count", -1)) != frame_count:
            return None
        if meta.get("settings_hash") != scan_settings_hash(arena, blob_params):
            return None
        if not video_path.is_file() or meta.get("video_token") != video_token(video_path):
            return None
        return meta
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def load_pose_scan_cache(
    video_dir: Path,
    *,
    frame_count: int,
    video_path: Path,
    arena: ArenaConfig,
    blob_params: BlobParams,
    load_fingerprints: bool = True,
) -> PoseScanCache | None:
    meta_path = video_dir / SCAN_CACHE_META
    data_path = video_dir / SCAN_CACHE_DATA
    meta = _read_scan_cache_meta(
        meta_path,
        frame_count=frame_count,
        video_path=video_path,
        arena=arena,
        blob_params=blob_params,
    )
    if meta is None:
        return None
    if load_fingerprints and not data_path.is_file():
        return None
    try:
        queues_raw = meta.get("queues_by_gap") or {}
        queues_by_gap = {int(k): list(v) for k, v in queues_raw.items()}
        targets_raw = meta.get("queues_by_target") or {}
        queues_by_target = {int(k): list(v) for k, v in targets_raw.items()}
        coarse_stride = int(meta.get("coarse_stride", 1))
        last_frames_to_analyze = int(meta.get("last_frames_to_analyze", 0))
        last_queue = [int(x) for x in (meta.get("last_queue") or [])]
        if load_fingerprints:
            data = np.load(data_path)
            indices = data["indices"]
            vectors = data["vectors"]
            fingerprints = _fingerprints_from_sparse(frame_count, indices, vectors)
            fingerprints_loaded = True
        else:
            fingerprints = []
            fingerprints_loaded = False
        return PoseScanCache(
            fingerprints=fingerprints,
            queues_by_gap=queues_by_gap,
            queues_by_target=queues_by_target,
            coarse_stride=coarse_stride,
            fingerprints_loaded=fingerprints_loaded,
            last_frames_to_analyze=last_frames_to_analyze,
            last_queue=last_queue,
        )
    except (OSError, ValueError, KeyError):
        return None


def save_pose_scan_cache(
    video_dir: Path,
    *,
    frame_count: int,
    video_path: Path,
    arena: ArenaConfig,
    blob_params: BlobParams,
    fingerprints: list[np.ndarray | None],
    coarse_stride: int,
    queue: list[int] | None = None,
    gap: int | None = None,
    frames_to_analyze: int | None = None,
    fingerprints_unchanged: bool = False,
) -> None:
    video_dir.mkdir(parents=True, exist_ok=True)
    meta_path = video_dir / SCAN_CACHE_META
    data_path = video_dir / SCAN_CACHE_DATA

    queues_by_gap: dict[int, list[int]] = {}
    queues_by_target: dict[int, list[int]] = {}
    last_frames_to_analyze = 0
    last_queue: list[int] = []
    if meta_path.is_file():
        try:
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
            if (
                int(existing.get("version", 0)) == SCAN_CACHE_VERSION
                and int(existing.get("frame_count", -1)) == frame_count
                and existing.get("settings_hash") == scan_settings_hash(arena, blob_params)
                and existing.get("video_token") == video_token(video_path)
            ):
                queues_by_gap = {
                    int(k): list(v) for k, v in (existing.get("queues_by_gap") or {}).items()
                }
                queues_by_target = {
                    int(k): list(v)
                    for k, v in (existing.get("queues_by_target") or {}).items()
                }
                last_frames_to_analyze = int(existing.get("last_frames_to_analyze", 0))
                last_queue = [int(x) for x in (existing.get("last_queue") or [])]
        except (OSError, ValueError, json.JSONDecodeError):
            queues_by_gap = {}
            queues_by_target = {}

    if queue is not None and gap is not None:
        queues_by_gap[int(gap)] = list(queue)
    if queue is not None and frames_to_analyze is not None:
        queues_by_target[int(frames_to_analyze)] = list(queue)
    if queue is not None:
        last_queue = list(queue)
        if frames_to_analyze is not None:
            last_frames_to_analyze = int(frames_to_analyze)

    indices, vectors = _sparse_from_fingerprints(fingerprints)
    if not fingerprints_unchanged:
        np.savez_compressed(data_path, indices=indices, vectors=vectors)

    meta = {
        "version": SCAN_CACHE_VERSION,
        "frame_count": frame_count,
        "settings_hash": scan_settings_hash(arena, blob_params),
        "video_token": video_token(video_path),
        "coarse_stride": coarse_stride,
        "queues_by_gap": {str(k): v for k, v in queues_by_gap.items()},
        "queues_by_target": {str(k): v for k, v in queues_by_target.items()},
        "last_frames_to_analyze": last_frames_to_analyze,
        "last_queue": last_queue,
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
