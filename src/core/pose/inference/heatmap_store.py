"""Persist full-resolution per-bodypart heatmaps from auto-label runs."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


@dataclass(frozen=True)
class HeatmapArchive:
    """On-disk folder of per-frame ``frame######.npz`` heatmap archives."""

    key: str
    label: str
    path: Path
    frame_count: int

    def relative_label(self, base: Path | None = None) -> str:
        if base is None:
            return self.label
        try:
            rel = self.path.relative_to(base)
            return f"{self.label} ({rel})"
        except ValueError:
            return self.label


def heatmaps_dir(session_name: str, project_id: str, video_id: str) -> Path:
    from app_platform.paths import ai_labelled_dir

    return ai_labelled_dir(session_name, project_id, video_id) / "heatmaps"


def count_heatmap_frames(archive_dir: Path) -> int:
    """Number of ``frame*.npz`` files in an archive directory."""
    if not archive_dir.is_dir():
        return 0
    return len(list_heatmap_frame_indices(archive_dir))


def list_heatmap_frame_indices(archive_dir: Path) -> set[int]:
    """Frame indices with a saved ``frame######.npz`` in ``archive_dir``."""
    indices: set[int] = set()
    if not archive_dir.is_dir():
        return indices
    for path in archive_dir.glob("frame*.npz"):
        stem = path.stem
        if not stem.startswith("frame"):
            continue
        try:
            indices.add(int(stem[5:]))
        except ValueError:
            continue
    return indices


def archive_missing_frames(archive_dir: Path, video_frame_count: int) -> list[int]:
    """Video frame indices with no heatmap file in the archive."""
    present = list_heatmap_frame_indices(archive_dir)
    return [fi for fi in range(max(0, int(video_frame_count))) if fi not in present]


def archive_is_complete(archive_dir: Path, video_frame_count: int) -> bool:
    """True when every video frame index has a heatmap ``.npz`` in the archive."""
    return not archive_missing_frames(archive_dir, video_frame_count)


def list_heatmap_archives(
    session_name: str,
    project_id: str,
    video_id: str,
) -> list[HeatmapArchive]:
    """
    Discover saved heatmap folders under ``ai_labelled/<video_id>/``.

    Includes the default ``heatmaps/`` folder and any sibling ``heatmaps*`` dirs.
    """
    from app_platform.paths import ai_labelled_dir

    video_out = ai_labelled_dir(session_name, project_id, video_id)
    if not video_out.is_dir():
        return []

    candidates: list[Path] = []
    default = video_out / "heatmaps"
    if default.is_dir():
        candidates.append(default)
    for child in sorted(video_out.iterdir()):
        if not child.is_dir() or child == default:
            continue
        if child.name.startswith("heatmaps"):
            candidates.append(child)

    archives: list[HeatmapArchive] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        n_frames = count_heatmap_frames(path)
        if n_frames <= 0:
            continue
        seen.add(resolved)
        try:
            rel = path.relative_to(video_out)
            rel_name = str(rel).replace("\\", "/")
        except ValueError:
            rel_name = path.name
        label = f"{rel_name} — {n_frames:,} frames"
        archives.append(
            HeatmapArchive(
                key=str(resolved),
                label=label,
                path=path,
                frame_count=n_frames,
            )
        )
    return archives


def heatmap_frame_path(archive_dir: Path, frame_index: int) -> Path:
    return Path(archive_dir) / f"frame{int(frame_index):06d}.npz"


def delete_heatmap_archive(archive_dir: Path) -> None:
    """Delete a heatmap archive directory and its ``frame*.npz`` files."""
    path = Path(archive_dir)
    if not path.is_dir():
        raise FileNotFoundError(f"Heatmap archive not found: {path}")
    shutil.rmtree(path)


def load_heatmaps_for_frame(
    archive_dir: Path,
    frame_index: int,
    *,
    crop_h: int,
    crop_w: int,
) -> dict[str, np.ndarray] | None:
    """Load full-crop heatmaps for one frame, or None if the archive file is missing."""
    path = heatmap_frame_path(archive_dir, frame_index)
    if not path.is_file():
        return None
    _fi, maps = load_frame_heatmaps(path)
    return full_crop_heatmaps(maps, crop_h, crop_w)


def upsample_heatmap_to_crop(
    heatmap: np.ndarray,
    crop_h: int,
    crop_w: int,
) -> np.ndarray:
    """Resize a scoremap to square crop resolution (linear upsample)."""
    hm = np.asarray(heatmap, dtype=np.float32)
    if hm.shape[0] == crop_h and hm.shape[1] == crop_w:
        return hm
    if cv2 is None:
        # Nearest-neighbor fallback without OpenCV.
        yy = (np.linspace(0, hm.shape[0] - 1, crop_h)).astype(np.int32)
        xx = (np.linspace(0, hm.shape[1] - 1, crop_w)).astype(np.int32)
        return hm[np.ix_(yy, xx)]
    return cv2.resize(hm, (crop_w, crop_h), interpolation=cv2.INTER_LINEAR)


def full_crop_heatmaps(
    heatmaps: dict[str, np.ndarray],
    crop_h: int,
    crop_w: int,
) -> dict[str, np.ndarray]:
    """Ensure every bodypart map is ``crop_h × crop_w`` float32."""
    out: dict[str, np.ndarray] = {}
    for bp, hm in heatmaps.items():
        out[bp] = upsample_heatmap_to_crop(hm, crop_h, crop_w)
    return out


def estimate_heatmap_archive_bytes(
    frame_count: int,
    bodypart_count: int,
    crop_side: int,
    *,
    dtype_bytes: int = 2,
) -> int:
    """Rough uncompressed size (float16 per pixel per bodypart per frame)."""
    side = max(1, int(crop_side))
    return int(frame_count) * int(bodypart_count) * side * side * dtype_bytes


def save_frame_heatmaps(
    out_dir: Path,
    frame_index: int,
    heatmaps: dict[str, np.ndarray],
    *,
    crop_h: int,
    crop_w: int,
) -> Path:
    """
    Write one compressed ``.npz`` per frame with full crop-resolution maps (float16).

    Keys are bodypart names; ``frame_index`` is stored as metadata.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"frame{frame_index:06d}.npz"
    full = full_crop_heatmaps(heatmaps, crop_h, crop_w)
    payload = {bp: arr.astype(np.float16) for bp, arr in full.items()}
    payload["frame_index"] = np.int32(frame_index)
    np.savez_compressed(path, **payload)
    return path


def load_frame_heatmaps(path: Path) -> tuple[int, dict[str, np.ndarray]]:
    """Load a single frame archive written by ``save_frame_heatmaps``."""
    with np.load(path, allow_pickle=False) as data:
        fi = int(data["frame_index"])
        maps = {k: np.asarray(data[k], dtype=np.float32) for k in data.files if k != "frame_index"}
    return fi, maps
