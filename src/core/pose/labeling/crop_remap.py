"""Keep full-frame labels consistent when arena / blob crop settings change.

**Update for all frames** must never delete labels. Use ``frames_with_labels_outside_crops``
and UI warnings (orange timeline dots) only. ``prune_labels_outside_crops`` is a low-level
utility kept for tests / optional future tooling — not wired to the Video tab button.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from core.pose.detection.blob import BlobResult
from core.pose.detection.crop import full_frame_to_crop
from core.pose.labeling.labels_store import LabelDataset


def point_inside_square_crop(x_full: float, y_full: float, blob: BlobResult) -> bool:
    """True when a full-frame point lies inside the square crop box."""
    if not blob.found:
        return False
    x_c, y_c = full_frame_to_crop(x_full, y_full, blob)
    side = float(max(1, int(blob.side)))
    return 0.0 <= x_c < side and 0.0 <= y_c < side


def prune_labels_outside_crops(
    dataset: LabelDataset,
    crop_for_frame: Callable[[int], BlobResult | None],
    *,
    frame_indices: Sequence[int] | None = None,
) -> tuple[int, int]:
    """
    Drop labeled points that fall outside the new square crop.

    **Not used by Update for all frames** — the app keeps all labels and flags
    outside-crop points in the UI instead. See ``frames_with_labels_outside_crops``.

    Labels stay in full-frame coordinates; points inside the new crop keep their
    world position (and therefore sit correctly relative to the new crop).

    - If no fish/crop is found for a labeled frame, all points on that frame
      are removed.
    - If a point falls outside the new square crop box, it is removed.

    Returns ``(removed_points, frames_cleared)``.
    """
    if frame_indices is None:
        indices = sorted(dataset.frames.keys())
    else:
        indices = sorted({int(i) for i in frame_indices})

    removed_points = 0
    frames_cleared = 0

    for fi in indices:
        fl = dataset.frames.get(fi)
        if fl is None or not fl.points:
            continue
        blob = crop_for_frame(fi)
        if blob is None or not blob.found:
            n = sum(1 for xy in fl.points.values() if xy is not None)
            if n:
                removed_points += n
                frames_cleared += 1
            fl.points.clear()
            if not fl.points:
                dataset.frames.pop(fi, None)
            continue

        drop_names = [
            name
            for name, xy in fl.points.items()
            if xy is not None and not point_inside_square_crop(xy[0], xy[1], blob)
        ]
        # Also drop explicit skips? keep skips (None) — only prune real coords.
        for name in drop_names:
            del fl.points[name]
            removed_points += 1
        if not fl.points:
            dataset.frames.pop(fi, None)
            if drop_names:
                frames_cleared += 1

    return removed_points, frames_cleared


def frames_with_labels_outside_crops(
    dataset: LabelDataset,
    crop_for_frame: Callable[[int], BlobResult | None],
    *,
    frame_indices: Sequence[int] | None = None,
) -> tuple[set[int], int]:
    """
    Find labeled frames with any point outside the current square crop.

    Does not modify the dataset. Returns ``(frame_indices, outside_point_count)``.
    """
    if frame_indices is None:
        indices = sorted(dataset.frames.keys())
    else:
        indices = sorted({int(i) for i in frame_indices})

    outside_frames: set[int] = set()
    outside_points = 0

    for fi in indices:
        fl = dataset.frames.get(fi)
        if fl is None or not fl.points:
            continue
        blob = crop_for_frame(fi)
        if blob is None or not blob.found:
            for xy in fl.points.values():
                if xy is not None:
                    outside_frames.add(fi)
                    outside_points += 1
            continue

        frame_outside = False
        for xy in fl.points.values():
            if xy is None:
                continue
            if not point_inside_square_crop(xy[0], xy[1], blob):
                frame_outside = True
                outside_points += 1
        if frame_outside:
            outside_frames.add(fi)

    return outside_frames, outside_points


def crop_lookup_from_blob_results(
    crops_by_frame: Mapping[int, BlobResult],
) -> Callable[[int], BlobResult | None]:
    """Build a ``crop_for_frame`` callback from a sparse frame→blob map."""

    def _lookup(frame_index: int) -> BlobResult | None:
        return crops_by_frame.get(int(frame_index))

    return _lookup
