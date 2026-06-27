"""Build frame index queues for labeling (gap + blob-shape diversity)."""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from core.pose.detection.arena import ArenaConfig
from core.pose.detection.blob import BlobParams, detect_blob_square_crop

# Normalized fish-mask canvas (shape only — position in dish removed).
_NORMALIZED_SHAPE_SIDE = 32
# Phase 1 stops when the best new shape is less than this fraction of the
# best min-distance seen so far (no more very different blobs).
_DIVERSITY_STOP_FRACTION = 0.22


def coarse_stride_for_gap(avg_gap: int) -> int:
    """Broad-scan stride: one shape sample about every ``avg_gap`` frames."""
    return max(1, int(avg_gap))


def shape_scan_coarse_stride(avg_gap: int) -> int:
    """Fingerprint sampling stride — several times denser than queue spacing."""
    return max(1, max(1, int(avg_gap)) // 4)


def _should_coarse_sample(frame_index: int, frame_count: int, stride: int) -> bool:
    if frame_count <= 0:
        return False
    if frame_index == 0 or frame_index >= frame_count - 1:
        return True
    return frame_index % stride == 0


def _refinement_indices(
    frame_count: int,
    avg_gap: int,
    fingerprints: list[np.ndarray | None],
    *,
    coarse_stride: int | None = None,
) -> set[int]:
    """Frames to refine after a coarse pass (finer scan inside wide temporal gaps)."""
    n = max(0, int(frame_count))
    if n == 0:
        return set()
    coarse = max(1, int(coarse_stride if coarse_stride is not None else coarse_stride_for_gap(avg_gap)))
    fine = max(1, coarse // 4)
    if fine >= coarse:
        return set()

    coarse_indices = [i for i in range(n) if _should_coarse_sample(i, n, coarse)]
    if not coarse_indices:
        return set()

    refine: set[int] = set()
    bounds = [-1] + coarse_indices + [n]
    for j in range(len(bounds) - 1):
        lo = bounds[j] + 1
        hi = bounds[j + 1]
        if hi - lo > coarse * 2:
            for idx in range(lo, hi, fine):
                if 0 <= idx < n and fingerprints[idx] is None:
                    refine.add(idx)
    return refine


def _sampled_frame_indices(fingerprints: list[np.ndarray | None]) -> list[int]:
    return [i for i, fp in enumerate(fingerprints) if fp is not None]


def target_label_frame_count(frame_count: int, avg_gap: int) -> int:
    """
    How many frames the user will label given average spacing.

    avg_gap 0 → every frame; avg_gap N → floor(total / N), at least 1.
    """
    n = max(0, int(frame_count))
    if n == 0:
        return 0
    g = max(0, int(avg_gap))
    if g == 0:
        return n
    return max(1, n // g)


def gap_from_frames_to_analyze(frame_count: int, frames_to_analyze: int) -> int:
    """Derive average frame spacing from a target number of frames to label."""
    n = max(0, int(frame_count))
    target = max(1, int(frames_to_analyze))
    if n == 0:
        return 1
    if target >= n:
        return 0
    return max(1, n // target)


def frames_to_analyze_cap(frame_count: int, requested: int, max_allowed: int) -> int:
    """Clamp target frame count to ``[1, min(frame_count, max_allowed)]``."""
    n = max(0, int(frame_count))
    cap = max(1, int(max_allowed))
    if n == 0:
        return max(1, min(requested, cap))
    return max(1, min(int(requested), n, cap))


def _resolve_queue_target(
    frame_count: int,
    gap: int,
    frames_to_analyze: int | None,
) -> int:
    """Exact queue length: prefer the user's ``frames_to_analyze`` when given."""
    n = max(0, int(frame_count))
    if n == 0:
        return 0
    if frames_to_analyze is not None:
        return max(1, min(int(frames_to_analyze), n))
    return target_label_frame_count(n, gap)


def pad_queue_to_target(
    queue: list[int],
    target: int,
    frame_count: int,
) -> list[int]:
    """Trim or widen a frame queue to exactly ``target`` unique indices."""
    n = max(0, int(frame_count))
    if n == 0:
        return []
    tgt = max(1, min(int(target), n))
    selected = sorted({int(i) for i in queue if 0 <= int(i) < n})
    if len(selected) >= tgt:
        return selected[:tgt]
    selected_set = set(selected)
    fps_none: list[np.ndarray | None] = [None] * n
    while len(selected) < tgt:
        pick = _pick_widest_gap_frame(sorted(selected), n, fps_none)
        if pick < 0 or pick in selected_set:
            step = max(1, n // tgt)
            added = False
            for i in range(0, n, step):
                if i not in selected_set:
                    selected.append(i)
                    selected_set.add(i)
                    added = True
                    break
            if not added:
                for i in range(n):
                    if i not in selected_set:
                        selected.append(i)
                        selected_set.add(i)
                        break
        else:
            selected.append(pick)
            selected_set.add(pick)
    return sorted(selected)[:tgt]


def build_label_frame_queue(
    frame_count: int,
    gap: int,
    *,
    target: int | None = None,
) -> list[int]:
    """
    Uniform stride fallback when blob scan is unavailable.

    gap 0 → every frame; gap N → 0, N, 2N, … up to ``target`` frames.
    """
    n = max(0, int(frame_count))
    if n == 0:
        return []
    tgt = _resolve_queue_target(n, gap, target)
    if tgt >= n:
        return list(range(n))
    g = max(1, int(gap))
    out: list[int] = []
    i = 0
    while i < n and len(out) < tgt:
        out.append(i)
        i += g
    if out and out[-1] != n - 1 and len(out) < tgt:
        out.append(n - 1)
    return pad_queue_to_target(out, tgt, n)


def _normalize_mask_shape(roi: np.ndarray) -> np.ndarray:
    """Center and scale a binary fish mask to a fixed canvas (shape-only)."""
    binary = (roi > 0.5).astype(np.uint8)
    ys, xs = np.where(binary)
    if len(xs) == 0:
        return np.zeros(_NORMALIZED_SHAPE_SIDE * _NORMALIZED_SHAPE_SIDE, dtype=np.float32)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    tight = binary[y0:y1, x0:x1].astype(np.float32)
    th, tw = tight.shape
    side = _NORMALIZED_SHAPE_SIDE - 2
    scale = side / max(th, tw, 1)
    nh = max(1, int(round(th * scale)))
    nw = max(1, int(round(tw * scale)))
    small = cv2.resize(tight, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((_NORMALIZED_SHAPE_SIDE, _NORMALIZED_SHAPE_SIDE), dtype=np.float32)
    yoff = (_NORMALIZED_SHAPE_SIDE - nh) // 2
    xoff = (_NORMALIZED_SHAPE_SIDE - nw) // 2
    canvas[yoff : yoff + nh, xoff : xoff + nw] = small
    vec = canvas.flatten()
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec


def blob_shape_fingerprint(
    frame_bgr: np.ndarray,
    arena: ArenaConfig,
    params: BlobParams,
) -> np.ndarray | None:
    """Normalized blob-shape vector for one frame (independent of fish position)."""
    blob = detect_blob_square_crop(frame_bgr, arena, params)
    if not blob.found:
        return None
    y0, y1, x0, x1 = blob.y0, blob.y1, blob.x0, blob.x1
    if y1 <= y0 or x1 <= x0:
        return None
    roi = blob.mask[y0:y1, x0:x1]
    if roi.size == 0:
        return None
    return _normalize_mask_shape(roi.astype(np.float32))


def shape_distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def scan_shape_fingerprints(
    frame_count: int,
    read_frame: Callable[[int], np.ndarray | None],
    arena: ArenaConfig,
    blob_params: BlobParams,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> list[np.ndarray | None]:
    """One pass over the video — normalized blob-shape fingerprint per frame."""
    n = max(0, int(frame_count))
    out: list[np.ndarray | None] = [None] * n
    for i in range(n):
        if progress is not None:
            progress(i, n)
        frame = read_frame(i)
        if frame is None:
            continue
        out[i] = blob_shape_fingerprint(frame, arena, blob_params)
    return out


def scan_shape_fingerprints_sequential(
    cap,
    frame_count: int,
    arena: ArenaConfig,
    blob_params: BlobParams,
    *,
    progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[np.ndarray | None]:
    """Sequential ``read()`` pass — avoids O(n²) MJPEG seeks from random access."""
    n = max(0, int(frame_count))
    out: list[np.ndarray | None] = [None] * n
    if n == 0:
        return out
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for i in range(n):
        if should_stop is not None and should_stop():
            break
        if progress is not None:
            progress(i, n)
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        out[i] = blob_shape_fingerprint(frame, arena, blob_params)
    return out


def scan_shape_fingerprints_adaptive_sequential(
    cap,
    frame_count: int,
    avg_gap: int,
    arena: ArenaConfig,
    blob_params: BlobParams,
    *,
    progress_coarse: Callable[[int, int], None] | None = None,
    progress_refine: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    status: Callable[[str], None] | None = None,
) -> tuple[list[np.ndarray | None], int]:
    """
    Broad pass (every ~gap frames), then finer samples inside wide temporal gaps.

    Gap-filling queue frames use timeline midpoints without extra shape reads.
    """
    n = max(0, int(frame_count))
    fps: list[np.ndarray | None] = [None] * n
    if n == 0:
        return fps, 1

    coarse = shape_scan_coarse_stride(avg_gap)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for i in range(n):
        if should_stop is not None and should_stop():
            break
        if progress_coarse is not None:
            progress_coarse(i + 1, n)
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if _should_coarse_sample(i, n, coarse):
            fps[i] = blob_shape_fingerprint(frame, arena, blob_params)

    if should_stop is not None and should_stop():
        return fps, coarse

    if status is not None:
        status("Planning refinement regions…")
    refine = _refinement_indices(n, avg_gap, fps, coarse_stride=coarse)
    if not refine:
        return fps, coarse

    if status is not None:
        status("Refining distinct poses…")

    max_refine = max(refine)
    refine_done = 0
    refine_total = len(refine)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for i in range(n):
        if should_stop is not None and should_stop():
            break
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        if i in refine:
            fps[i] = blob_shape_fingerprint(frame, arena, blob_params)
            refine_done += 1
            if progress_refine is not None:
                progress_refine(refine_done, refine_total)
        if i >= max_refine and refine_done >= refine_total:
            break
    return fps, coarse


def _first_valid_frame(fingerprints: list[np.ndarray | None]) -> int:
    for i, fp in enumerate(fingerprints):
        if fp is not None:
            return i
    return 0


def _best_farthest_candidate(
    fingerprints: list[np.ndarray | None],
    selected: list[int],
    selected_set: set[int],
    candidates: list[int],
) -> tuple[int, float]:
    """Frame with largest min-distance to the already-selected shape set."""
    best_f = -1
    best_min = -1.0
    for f in candidates:
        if f in selected_set:
            continue
        fp = fingerprints[f]
        if fp is None:
            continue
        min_d = min(shape_distance(fp, fingerprints[s]) for s in selected if fingerprints[s] is not None)
        if min_d > best_min:
            best_min = min_d
            best_f = f
    return best_f, best_min


def _pick_widest_gap_frame(
    selected: list[int],
    n: int,
    fingerprints: list[np.ndarray | None],
) -> int:
    """Midpoint inside the widest temporal gap (expand outward if occupied)."""
    bounds = [-1] + selected + [n]
    best_lo = -1
    best_hi = -1
    best_width = -1
    for j in range(len(bounds) - 1):
        left = bounds[j]
        right = bounds[j + 1]
        width = right - left - 1
        if width > best_width:
            best_width = width
            best_lo = left + 1
            best_hi = right
    if best_width <= 0 or best_lo < 0 or best_hi <= best_lo:
        return -1

    mid = (best_lo + best_hi - 1) // 2
    span = best_hi - best_lo
    for offset in range(span):
        for candidate in (mid - offset, mid + offset):
            if best_lo <= candidate < best_hi and candidate not in selected:
                if offset == 0 or fingerprints[candidate] is not None:
                    return candidate
                if not any(
                    fingerprints[i] is not None for i in range(best_lo, best_hi)
                ):
                    return candidate
    return -1


def _phase1_farthest_shape_picks(
    fingerprints: list[np.ndarray | None],
    *,
    target: int,
    n: int,
    on_pick: Callable[[list[int]], None] | None = None,
) -> list[int]:
    """
    Greedy farthest-point on blob shapes.

    1. Seed with the first valid blob near the start of the video.
    2. Repeatedly add the frame whose shape is most different from all picks so far.
    3. Stop when no very different blobs remain, or half of ``target`` is reached.
    """
    if n == 0:
        return []
    first = _first_valid_frame(fingerprints)
    selected = [first]
    selected_set = {first}
    if on_pick is not None:
        on_pick(list(selected))
    half_target = max(1, (target + 1) // 2)
    peak_min_dist = 0.0
    candidates = _sampled_frame_indices(fingerprints)

    while len(selected) < half_target and len(selected) < target:
        best_f, best_min = _best_farthest_candidate(
            fingerprints, selected, selected_set, candidates
        )
        if best_f < 0:
            break
        if peak_min_dist > 0 and best_min < _DIVERSITY_STOP_FRACTION * peak_min_dist:
            break
        peak_min_dist = max(peak_min_dist, best_min)
        selected.append(best_f)
        selected_set.add(best_f)
        selected.sort()
        if on_pick is not None:
            on_pick(list(selected))

    return selected


def _phase2_fill_gaps(
    selected: list[int],
    *,
    target: int,
    n: int,
    fingerprints: list[np.ndarray | None],
    on_pick: Callable[[list[int]], None] | None = None,
) -> list[int]:
    """Fill widest timeline gaps until ``target`` frames are chosen."""
    selected_set = set(selected)
    while len(selected) < target:
        pick = _pick_widest_gap_frame(sorted(selected), n, fingerprints)
        if pick < 0 or pick in selected_set:
            break
        selected.append(pick)
        selected_set.add(pick)
        selected.sort()
        if on_pick is not None:
            on_pick(list(selected))
    return selected


def distinctness_vs_selected(
    fingerprints: list[np.ndarray | None],
    selected: list[int],
) -> list[float]:
    """Per-frame min shape-distance to the queue (for UI hints)."""
    n = len(fingerprints)
    scores = [0.0] * n
    sel = [s for s in selected if fingerprints[s] is not None]
    if not sel:
        return scores
    for i, fp in enumerate(fingerprints):
        if fp is None:
            continue
        scores[i] = min(shape_distance(fp, fingerprints[s]) for s in sel)
    mx = max(scores) if scores else 0.0
    if mx > 0:
        scores = [s / mx for s in scores]
    return scores


def build_diverse_label_frame_queue(
    frame_count: int,
    avg_gap: int,
    fingerprints: list[np.ndarray | None] | None = None,
    *,
    target: int | None = None,
    on_pick: Callable[[list[int]], None] | None = None,
    on_build_progress: Callable[[int, int], None] | None = None,
) -> list[int]:
    """
    Build a labeling queue with exactly ``target`` frames (or derived from gap).

    Phase 1 — farthest blob-shape picks (seed at first blob, then globally most
    different from the set, until diversity runs out or half of target is filled).

    Phase 2 — fill widest temporal gaps (midpoints) until target is reached.
    """
    n = max(0, int(frame_count))
    if n == 0:
        return []
    if avg_gap <= 0 and target is None:
        return list(range(n))
    tgt = _resolve_queue_target(n, avg_gap, target)
    if tgt >= n:
        return list(range(n))

    fps: list[np.ndarray | None]
    if fingerprints is None or len(fingerprints) != n:
        fps = [None] * n
    else:
        fps = fingerprints

    if all(f is None for f in fps):
        return build_label_frame_queue(n, avg_gap, target=tgt)

    build_steps = 0

    def _pick_cb(picks: list[int]) -> None:
        nonlocal build_steps
        build_steps = len(picks)
        if on_pick is not None:
            on_pick(picks)
        if on_build_progress is not None:
            on_build_progress(build_steps, tgt)

    selected = _phase1_farthest_shape_picks(fps, target=tgt, n=n, on_pick=_pick_cb)
    selected = _phase2_fill_gaps(
        selected, target=tgt, n=n, fingerprints=fps, on_pick=_pick_cb
    )
    if on_build_progress is not None:
        on_build_progress(tgt, tgt)
    return pad_queue_to_target(selected, tgt, n)
