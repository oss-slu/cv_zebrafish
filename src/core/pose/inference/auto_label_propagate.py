"""Frame-by-frame auto-label propagation with constrained heatmap decode."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import cv2
import numpy as np

from core.pose.inference.dlc_heatmap_predictor import CropHeatmapResult, _heatmaps_are_usable
from core.pose.inference.heatmap_store import (
    full_crop_heatmaps,
    heatmaps_dir,
    load_heatmaps_for_frame,
    save_frame_heatmaps,
)

from app_platform.paths import ai_labelled_dir, human_labelled_dir, pose_video_dir
from core.pose.dataset.export_dlc import export_dlc_csv
from core.pose.dataset.import_dlc_csv import import_dlc_csv
from core.pose.labeling.labels_store import save_schema
from core.pose.detection.arena import ArenaConfig, load_arena
from core.pose.detection.blob import BlobParams, detect_blob_square_crop, load_blob_params
from core.pose.detection.crop import crop_to_full_frame, extract_square_crop, fish_mask_in_crop, full_frame_to_crop
from core.pose.inference.bone_reference import median_bone_lengths
from core.pose.inference.constrained_decode import (
    ConstrainedDecodeParams,
    bone_stretch_violations,
    decode_frame_constrained,
)
from core.pose.labeling.labels_store import LabelDataset, load_labels
from core.pose.labeling.schema import PoseSchema
from core.pose.video.video_registry import read_video_meta, resolve_video_source


ProgressCallback = Callable[[int, int, str], None]
# First argument is 1-based completed frame count (propagation order), not video frame index.


class HeatmapPredictor(Protocol):
    """Predict per-bodypart heatmaps on a square fish crop (BGR)."""

    def predict_crop(
        self,
        crop_bgr: np.ndarray,
        bodyparts: list[str],
    ) -> CropHeatmapResult | dict[str, np.ndarray]: ...


@dataclass
class AutoLabelParams:
    """User-facing auto-label settings."""

    seed_frame: int = 0
    min_likelihood: float = 0.6
    search_radius_px: float = 45.0
    bone_stretch_ratio: float = 2.0
    save_heatmaps: bool = True
    use_existing_heatmaps: bool = False
    finish_incomplete_archive: bool = False
    heatmap_source_dir: str | None = None

    def to_decode_params(self) -> ConstrainedDecodeParams:
        return ConstrainedDecodeParams(
            min_likelihood=self.min_likelihood,
            bone_stretch_ratio=self.bone_stretch_ratio,
            default_search_radius_px=self.search_radius_px,
        )


@dataclass
class AutoLabelReport:
    """QC summary written beside ``tracking.csv``."""

    seed_frame: int
    frames_processed: int = 0
    frames_blob_missing: int = 0
    heatmaps_saved: int = 0
    heatmap_dir: str = ""
    estimated_heatmap_bytes: int = 0
    outlier_frames: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seed_frame": self.seed_frame,
            "frames_processed": self.frames_processed,
            "frames_blob_missing": self.frames_blob_missing,
            "heatmaps_saved": self.heatmaps_saved,
            "heatmap_dir": self.heatmap_dir,
            "estimated_heatmap_bytes": self.estimated_heatmap_bytes,
            "outlier_frames": self.outlier_frames,
        }


def seed_frame_is_complete(dataset: LabelDataset, seed_frame: int) -> tuple[bool, list[str]]:
    """True when every schema bodypart has a coordinate on ``seed_frame``."""
    missing: list[str] = []
    for bp in dataset.bodyparts():
        if dataset.get_point(seed_frame, bp) is None:
            missing.append(bp)
    return not missing, missing


def first_complete_seed_frame(dataset: LabelDataset) -> int | None:
    """Return the lowest frame index with all bodyparts labeled, if any."""
    for fi in sorted(dataset.frames.keys()):
        ok, _ = seed_frame_is_complete(dataset, fi)
        if ok:
            return fi
    return None


def nearest_complete_seed_frame(dataset: LabelDataset, preferred: int) -> int | None:
    """Frame at or after ``preferred`` with a full label set, else earliest complete."""
    candidates = [
        fi for fi in sorted(dataset.frames.keys()) if seed_frame_is_complete(dataset, fi)[0]
    ]
    if not candidates:
        return None
    for fi in candidates:
        if fi >= preferred:
            return fi
    return candidates[0]


def _search_radii(bodyparts: list[str], radius_px: float) -> dict[str, float]:
    return {bp: radius_px for bp in bodyparts}


def _copy_human_labels(
    human_labels: LabelDataset,
    out: LabelDataset,
    bodyparts: list[str],
) -> None:
    for fi in sorted(human_labels.frames.keys()):
        for bp in bodyparts:
            xy = human_labels.get_point(fi, bp)
            if xy is not None:
                out.set_point(fi, bp, xy[0], xy[1])


def _prev_full_from_out(
    out: LabelDataset,
    prev_fi: int,
    bodyparts: list[str],
) -> dict[str, tuple[float, float] | None]:
    return {bp: out.get_point(prev_fi, bp) for bp in bodyparts}


def _prev_crop_positions(
    prev_full: dict[str, tuple[float, float] | None],
    blob,
    bodyparts: list[str],
) -> dict[str, tuple[float, float] | None]:
    out: dict[str, tuple[float, float] | None] = {}
    for bp in bodyparts:
        xy = prev_full.get(bp)
        if xy is None:
            out[bp] = None
        else:
            out[bp] = full_frame_to_crop(xy[0], xy[1], blob)
    return out


def _unwrap_crop_prediction(
    result: CropHeatmapResult | dict[str, np.ndarray],
) -> CropHeatmapResult:
    if isinstance(result, CropHeatmapResult):
        return result
    return CropHeatmapResult(heatmaps=result)


def _heatmap_write_dir(
    heatmap_out_dir: Path | None,
    heatmap_source_dir: Path | None,
    params: AutoLabelParams,
) -> Path | None:
    if heatmap_out_dir is not None:
        return heatmap_out_dir
    if heatmap_source_dir is not None and params.finish_incomplete_archive:
        return heatmap_source_dir
    return None


def _infer_and_save_heatmaps(
    *,
    fi: int,
    crop,
    bodyparts: list[str],
    predictor: HeatmapPredictor,
    write_dir: Path,
    report: AutoLabelReport,
) -> dict[str, np.ndarray]:
    crop_h, crop_w = crop.shape[:2]
    prediction = _unwrap_crop_prediction(predictor.predict_crop(crop, bodyparts))
    heatmaps = full_crop_heatmaps(prediction.heatmaps, crop_h, crop_w)
    if not _heatmaps_are_usable(heatmaps):
        raise RuntimeError(
            f"Auto Label aborted at frame {fi}: model returned all-zero heatmaps "
            "(empty pose prediction). Fix the DLC crop predictor / snapshot before "
            "re-running — ai_labelled tracking.csv was not overwritten."
        )
    save_frame_heatmaps(
        write_dir,
        fi,
        heatmaps,
        crop_h=crop_h,
        crop_w=crop_w,
        peak_locref=prediction.peak_locref,
    )
    report.heatmaps_saved += 1
    report.estimated_heatmap_bytes += sum(hm.nbytes for hm in heatmaps.values())
    return heatmaps


def _decode_and_write_frame(
    *,
    fi: int,
    frame,
    prev_fi: int,
    out: LabelDataset,
    human_labels: LabelDataset,
    bodyparts: list[str],
    edges: list[tuple[int, int]],
    arena: ArenaConfig,
    blob_params: BlobParams,
    predictor: HeatmapPredictor | None,
    params: AutoLabelParams,
    decode_params: ConstrainedDecodeParams,
    radii: dict[str, float],
    ref_lengths: dict[tuple[str, str], float],
    report: AutoLabelReport,
    heatmap_out_dir: Path | None,
    heatmap_source_dir: Path | None = None,
) -> None:
    human_complete = seed_frame_is_complete(human_labels, fi)[0]
    decode_only = (
        heatmap_source_dir is not None and not params.finish_incomplete_archive
    )
    # Re-decode from saved heatmaps: human scaffold frames need no archive entry.
    if human_complete and decode_only:
        report.frames_processed += 1
        return

    blob = detect_blob_square_crop(frame, arena, blob_params)
    if not blob.found:
        report.frames_blob_missing += 1
        for bp in bodyparts:
            if human_labels.get_point(fi, bp) is None:
                out.skip_point(fi, bp)
        report.frames_processed += 1
        return

    crop = extract_square_crop(frame, blob)
    fish_mask = fish_mask_in_crop(blob)
    crop_h, crop_w = crop.shape[:2]
    heatmaps: dict[str, np.ndarray] | None = None
    if heatmap_source_dir is not None:
        heatmaps = load_heatmaps_for_frame(
            heatmap_source_dir,
            fi,
            crop_h=crop_h,
            crop_w=crop_w,
        )
        if heatmaps is None and not params.finish_incomplete_archive:
            raise ValueError(
                f"No saved heatmap for frame {fi} in {heatmap_source_dir}. "
                "Pick a complete archive, enable Finish labeling, or run inference "
                "to generate heatmaps."
            )

    if heatmaps is None:
        if predictor is None:
            raise ValueError("No heatmap predictor available for auto-label.")
        write_dir = _heatmap_write_dir(heatmap_out_dir, heatmap_source_dir, params)
        if write_dir is not None:
            heatmaps = _infer_and_save_heatmaps(
                fi=fi,
                crop=crop,
                bodyparts=bodyparts,
                predictor=predictor,
                write_dir=write_dir,
                report=report,
            )
        else:
            prediction = _unwrap_crop_prediction(predictor.predict_crop(crop, bodyparts))
            heatmaps = full_crop_heatmaps(prediction.heatmaps, crop_h, crop_w)
            if not _heatmaps_are_usable(heatmaps):
                raise RuntimeError(
                    f"Auto Label aborted at frame {fi}: model returned all-zero heatmaps "
                    "(empty pose prediction). Fix the DLC crop predictor / snapshot before "
                    "re-running — ai_labelled tracking.csv was not overwritten."
                )
    elif not _heatmaps_are_usable(heatmaps):
        raise RuntimeError(
            f"Auto Label aborted at frame {fi}: saved heatmaps are all zeros. "
            "Delete that archive and re-run with model inference "
            "(uncheck \"Use saved heatmaps\")."
        )

    if human_complete:
        report.frames_processed += 1
        return

    prev_full = _prev_full_from_out(out, prev_fi, bodyparts)
    prev_crop = _prev_crop_positions(prev_full, blob, bodyparts)
    decoded = decode_frame_constrained(
        heatmaps,
        fish_mask,
        bodyparts=bodyparts,
        prev_positions_crop=prev_crop,
        search_radii=radii,
        params=decode_params,
        crop_side=blob.side,
    )

    frame_full: dict[str, tuple[float, float] | None] = {}
    for bp in bodyparts:
        human_xy = human_labels.get_point(fi, bp)
        if human_xy is not None:
            frame_full[bp] = human_xy
            continue
        xy_crop = decoded.positions.get(bp)
        if xy_crop is None:
            out.skip_point(fi, bp)
            frame_full[bp] = None
        else:
            fx, fy = crop_to_full_frame(xy_crop[0], xy_crop[1], blob)
            out.set_point(fi, bp, fx, fy)
            frame_full[bp] = (fx, fy)

    violations = bone_stretch_violations(
        frame_full,
        bodyparts,
        edges,
        ref_lengths,
        max_ratio=decode_params.bone_stretch_ratio,
    )
    frame_flags = list(violations)
    for bp, flags in decoded.flags.items():
        if flags:
            frame_flags.append(f"{bp}: {', '.join(flags)}")
    if frame_flags:
        report.outlier_frames[str(fi)] = frame_flags

    report.frames_processed += 1


def propagate_auto_label(
    *,
    video_path: Path,
    frame_count: int,
    arena: ArenaConfig,
    blob_params: BlobParams,
    human_labels: LabelDataset,
    predictor: HeatmapPredictor | None,
    params: AutoLabelParams,
    progress_cb: ProgressCallback | None = None,
    heatmap_out_dir: Path | None = None,
) -> tuple[LabelDataset, AutoLabelReport]:
    """
    Propagate labels forward and backward from a human seed frame.

    Human-labeled points are never overwritten. Bone-length limits use the
    median across every manually labeled frame.
    """
    bodyparts = human_labels.bodyparts()
    if not bodyparts:
        raise ValueError("No bodyparts in label schema.")

    ok, missing = seed_frame_is_complete(human_labels, params.seed_frame)
    if not ok:
        raise ValueError(
            f"Seed frame {params.seed_frame} is missing bodyparts: {', '.join(missing)}. "
            "Label all points on the seed frame in the Label tab first."
        )

    decode_params = params.to_decode_params()
    radii = _search_radii(bodyparts, params.search_radius_px)
    ref_lengths = median_bone_lengths(
        human_labels,
        frame_indices=sorted(human_labels.frames.keys()),
    )
    edges = human_labels.schema.edges

    out = LabelDataset(schema=PoseSchema(bodyparts=list(bodyparts), edges=list(edges)))
    _copy_human_labels(human_labels, out, bodyparts)

    report = AutoLabelReport(seed_frame=params.seed_frame)
    heatmap_source_dir: Path | None = None
    if params.heatmap_source_dir and (
        params.use_existing_heatmaps or params.finish_incomplete_archive
    ):
        heatmap_source_dir = Path(params.heatmap_source_dir)
        if not heatmap_source_dir.is_dir():
            raise ValueError(f"Heatmap archive not found: {heatmap_source_dir}")
        report.heatmap_dir = str(heatmap_source_dir.resolve())
    elif heatmap_out_dir is not None:
        report.heatmap_dir = str(heatmap_out_dir.resolve())

    needs_predictor = heatmap_source_dir is None or params.finish_incomplete_archive
    if needs_predictor and predictor is None:
        raise ValueError(
            "Auto-label needs a model checkpoint or a complete saved heatmap archive."
        )

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    seed = params.seed_frame
    total = max(1, int(frame_count))
    completed = 1
    if progress_cb is not None:
        progress_cb(completed, total, f"{completed} / {total}")

    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, seed)
        ok_read, seed_frame_img = cap.read()
        if ok_read and seed_frame_img is not None:
            _decode_and_write_frame(
                fi=seed,
                frame=seed_frame_img,
                prev_fi=seed,
                out=out,
                human_labels=human_labels,
                bodyparts=bodyparts,
                edges=edges,
                arena=arena,
                blob_params=blob_params,
                predictor=predictor,
                params=params,
                decode_params=decode_params,
                radii=radii,
                ref_lengths=ref_lengths,
                report=report,
                heatmap_out_dir=heatmap_out_dir,
                heatmap_source_dir=heatmap_source_dir,
            )
        else:
            report.frames_processed += 1

        for fi in range(seed + 1, total):
            completed += 1
            if progress_cb is not None:
                progress_cb(completed, total, f"{completed} / {total}")
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok_read, frame = cap.read()
            if not ok_read or frame is None:
                continue
            _decode_and_write_frame(
                fi=fi,
                frame=frame,
                prev_fi=fi - 1,
                out=out,
                human_labels=human_labels,
                bodyparts=bodyparts,
                edges=edges,
                arena=arena,
                blob_params=blob_params,
                predictor=predictor,
                params=params,
                decode_params=decode_params,
                radii=radii,
                ref_lengths=ref_lengths,
                report=report,
                heatmap_out_dir=heatmap_out_dir,
                heatmap_source_dir=heatmap_source_dir,
            )

        for fi in range(seed - 1, -1, -1):
            completed += 1
            if progress_cb is not None:
                progress_cb(completed, total, f"{completed} / {total}")
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ok_read, frame = cap.read()
            if not ok_read or frame is None:
                continue
            _decode_and_write_frame(
                fi=fi,
                frame=frame,
                prev_fi=fi + 1,
                out=out,
                human_labels=human_labels,
                bodyparts=bodyparts,
                edges=edges,
                arena=arena,
                blob_params=blob_params,
                predictor=predictor,
                params=params,
                decode_params=decode_params,
                radii=radii,
                ref_lengths=ref_lengths,
                report=report,
                heatmap_out_dir=heatmap_out_dir,
                heatmap_source_dir=heatmap_source_dir,
            )
    finally:
        cap.release()

    return out, report


def run_auto_label_for_video(
    *,
    session_name: str,
    project_id: str,
    video_id: str,
    predictor: HeatmapPredictor | None,
    params: AutoLabelParams,
    progress_cb: ProgressCallback | None = None,
    scorer: str = "pose_studio",
) -> Path:
    """Load context, propagate, write ``ai_labelled/<video_id>/tracking.csv``."""
    vdir = pose_video_dir(session_name, project_id, video_id)
    video_path = resolve_video_source(vdir)
    if video_path is None:
        raise ValueError(f"No video source for {video_id}")
    meta = read_video_meta(vdir)
    frame_count = meta.frame_count if meta and meta.frame_count > 0 else 0
    if frame_count <= 0:
        cap = cv2.VideoCapture(str(video_path))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) if cap.isOpened() else 0
        cap.release()
    if frame_count <= 0:
        raise ValueError(f"Could not determine frame count for {video_id}")

    arena = load_arena(vdir / "arena.json")
    blob_params = load_blob_params(vdir / "blob_params.json")
    human_labels = load_labels(human_labelled_dir(session_name, project_id, video_id))

    dataset, report = propagate_auto_label(
        video_path=video_path,
        frame_count=frame_count,
        arena=arena,
        blob_params=blob_params,
        human_labels=human_labels,
        predictor=predictor,
        params=params,
        progress_cb=progress_cb,
        heatmap_out_dir=(
            Path(params.heatmap_source_dir)
            if params.finish_incomplete_archive and params.heatmap_source_dir
            else (
                None
                if params.use_existing_heatmaps
                else (
                    heatmaps_dir(session_name, project_id, video_id)
                    if params.save_heatmaps
                    else None
                )
            )
        ),
    )

    out_dir = ai_labelled_dir(session_name, project_id, video_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "tracking.csv"
    new_labeled = dataset.count_frames_with_any_point()
    human_labeled = human_labels.count_frames_with_any_point()
    decode_only = bool(
        params.use_existing_heatmaps
        and params.heatmap_source_dir
        and not params.finish_incomplete_archive
    )
    # Inference produced nothing beyond human seeds — fail instead of overwriting AI.
    if not decode_only and new_labeled <= human_labeled:
        report_path = out_dir / "auto_label_report.json"
        report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        raise RuntimeError(
            "Auto Label produced no new predictions beyond human seed labels "
            f"({new_labeled} labeled frames). The DLC crop predictor returned empty "
            "poses/heatmaps. Check the pose env snapshot, or keep the existing "
            "ai_labelled tracking.csv (not overwritten)."
        )
    if out_csv.is_file():
        try:
            existing, _, _ = import_dlc_csv(out_csv)
            existing_labeled = existing.count_frames_with_any_point()
        except (OSError, ValueError):
            existing_labeled = 0
        if existing_labeled > new_labeled:
            backup = out_dir / "tracking_prev_dense.csv"
            out_csv.replace(backup)
    export_dlc_csv(dataset, frame_count, out_csv, scorer=scorer)
    # Persist Label-tab bones beside CSV (CSV itself has no schema).
    save_schema(out_dir, dataset.schema)
    report_path = out_dir / "auto_label_report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    marker = out_dir / "analyze_mode.txt"
    marker.write_text("auto_label_constrained\n", encoding="utf-8")
    return out_csv


def run_auto_label_job(
    job: dict,
    *,
    progress_cb: ProgressCallback | None = None,
) -> list[Path]:
    """Run constrained auto-label for every video in a train job."""
    session_name = str(job["session_name"])
    project_id = str(job["project_id"])
    scorer = str(job.get("scorer") or "pose_studio")
    video_ids: list[str] = list(job.get("video_ids") or [])

    auto = job.get("auto_label") or {}
    params = AutoLabelParams(
        seed_frame=int(auto.get("seed_frame", 0)),
        min_likelihood=float(auto.get("min_likelihood", 0.6)),
        search_radius_px=float(auto.get("search_radius_px", 45.0)),
        bone_stretch_ratio=float(auto.get("bone_stretch_ratio", 2.0)),
        save_heatmaps=bool(auto.get("save_heatmaps", True)),
        use_existing_heatmaps=bool(auto.get("use_existing_heatmaps", False)),
        finish_incomplete_archive=bool(auto.get("finish_incomplete_archive", False)),
        heatmap_source_dir=auto.get("heatmap_source_dir"),
    )

    decode_only = (
        params.use_existing_heatmaps
        and bool(params.heatmap_source_dir)
        and not params.finish_incomplete_archive
    )
    predictor = None
    if not decode_only:
        from core.pose.inference.dlc_heatmap_predictor import build_heatmap_predictor

        predictor = build_heatmap_predictor(job)
    written: list[Path] = []
    for vid in video_ids:
        path = run_auto_label_for_video(
            session_name=session_name,
            project_id=project_id,
            video_id=vid,
            predictor=predictor,
            params=params,
            progress_cb=progress_cb,
            scorer=scorer,
        )
        written.append(path)
    return written
