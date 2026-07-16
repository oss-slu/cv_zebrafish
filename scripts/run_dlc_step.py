#!/usr/bin/env python3
"""
DLC train/predict subprocess for Pose Studio (isolated from PyQt main process).

Emits JSON-lines progress on stdout. Example:
  {"type": "phase", "phase": "train"}
  {"type": "epoch", "epoch": 1, "total_epochs": 50, "loss": 0.42}

Usage:
  python scripts/run_dlc_step.py --job path/to/train_job.json --step pipeline --epochs 50
  python scripts/run_dlc_step.py --job path/to/train_job.json --step dry_run --epochs 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.pose.training.dlc_subprocess import (  # noqa: E402
    SNAPSHOT_SAVE_EPOCHS,
    clear_stop_flag,
    find_learning_stats_path,
    parse_latest_learning_stats_row,
    parse_learning_stats_csv,
    read_training_progress,
    should_skip_create_training_dataset,
    snapshot_keep_count,
    stop_requested,
)

STOP_FLAG = "stop_after_epoch.flag"


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def stop_requested(work_dir: Path) -> bool:
    return (work_dir / STOP_FLAG).is_file()


def load_job(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def try_import_dlc():
    try:
        import deeplabcut  # noqa: F401

        return True
    except ImportError:
        return False


def _resolve_training_device(use_gpu: bool) -> str | None:
    if not use_gpu:
        return None
    try:
        import torch
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return "cuda:0"


def _find_train_log_path(work_dir: Path) -> Path | None:
    logs = sorted(
        work_dir.glob("dlc-models-pytorch/**/train/train.txt"),
        key=lambda p: p.stat().st_mtime,
    )
    return logs[-1] if logs else None


def _train_status_hint(work_dir: Path) -> str:
    path = _find_train_log_path(work_dir)
    if path is None or not path.is_file():
        return "Initializing model and dataset…"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "Initializing model and dataset…"
    if "Starting pose model training" in text:
        return (
            "Training in progress — the loss curve updates after each epoch completes "
            "(first epoch on CPU can take several minutes)."
        )
    if "Data Transforms" in text or "Loading pretrained weights" in text:
        return (
            "Loading weights and building the data pipeline "
            "(often 10–20 min on CPU before epoch 1 starts)."
        )
    return "Preparing training environment…"


def run_probe_gpu() -> None:
    status = _resolve_training_device(True)
    try:
        import torch

        emit(
            {
                "type": "gpu_probe",
                "cuda_available": bool(torch.cuda.is_available()),
                "torch_version": torch.__version__,
                "device_count": int(torch.cuda.device_count()),
                "device_name": (
                    torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
                ),
                "resolved_device": status or "",
            }
        )
    except Exception as exc:
        emit({"type": "gpu_probe", "cuda_available": False, "error": str(exc)})


def run_create_training_dataset(job: dict) -> None:
    emit({"type": "phase", "phase": "create_training_dataset"})
    config_path = job["config_path"]
    scorer = job.get("scorer", "pose_studio")
    if try_import_dlc():
        import deeplabcut as dlc

        emit(
            {
                "type": "status",
                "message": "Converting labels and building augmented training set (may take a few minutes)…",
            }
        )
        dlc.convertcsv2h5(config_path, userfeedback=False, scorer=scorer)
        result = dlc.create_training_dataset(
            config_path,
            Shuffles=[1],
            augmenter_type="albumentations",
            userfeedback=False,
        )
        if result is None:
            raise ValueError(
                "DLC could not build a training dataset from the prepared labels. "
                "Re-run Prepare training bundle, then try training again."
            )
        emit({"type": "status", "message": "Training dataset created (DLC)."})
    else:
        emit({"type": "status", "message": "Skipped create_training_dataset (deeplabcut not installed)."})


def _emit_epoch_progress(
    row,
    *,
    epochs: int,
    resumed: bool = False,
) -> None:
    payload = {
        "type": "epoch",
        "epoch": row.epoch,
        "total_epochs": epochs,
        "loss": row.total_loss,
    }
    if row.heatmap_loss is not None:
        payload["heatmap_loss"] = row.heatmap_loss
    if row.locref_loss is not None:
        payload["locref_loss"] = row.locref_loss
    if resumed:
        payload["resumed"] = True
    emit(payload)


def run_train(job: dict, epochs: int, use_gpu: bool) -> None:
    emit({"type": "phase", "phase": "train", "total_epochs": epochs, "use_gpu": use_gpu})
    work_dir = Path(job["work_dir"])
    config_path = job["config_path"]

    if try_import_dlc():
        import threading

        import deeplabcut as dlc

        device = _resolve_training_device(use_gpu)
        if use_gpu and device is None:
            raise RuntimeError(
                "GPU was requested but CUDA is not available in the DLC Python env. "
                "Install NVIDIA drivers and CUDA-enabled PyTorch (see docs/POSE_DLC_ENV.md), "
                "or uncheck Use GPU."
            )
        if device:
            emit({"type": "status", "message": f"Training on {device}."})
        emit(
            {
                "type": "status",
                "message": (
                    f"Saving weight checkpoints every {SNAPSHOT_SAVE_EPOCHS} epochs "
                    f"(up to {snapshot_keep_count(epochs)} kept, plus best-by-validation)."
                ),
            }
        )

        baseline_epoch = 0
        stats_path = find_learning_stats_path(work_dir)
        if stats_path is not None:
            prior_row = parse_latest_learning_stats_row(stats_path)
            if prior_row is not None and prior_row.epoch > 0:
                baseline_epoch = prior_row.epoch
                emit(
                    {
                        "type": "status",
                        "message": (
                            f"Resuming from epoch {baseline_epoch} — checkpoints are kept in "
                            "models/dlc_work/ between runs. Use Reset training progress on the "
                            "Train tab to start from epoch 1."
                        ),
                    }
                )
                _emit_epoch_progress(prior_row, epochs=epochs, resumed=True)

        stop = threading.Event()
        force_stop = threading.Event()
        train_started = time.monotonic()
        last_heartbeat = 0.0

        def poll_stats():
            nonlocal stats_path, last_heartbeat
            last_epoch = baseline_epoch
            stop_when_done_after: int | None = None
            while not stop.is_set():
                now = time.monotonic()
                if stop_requested(work_dir) and stop_when_done_after is None:
                    stop_when_done_after = last_epoch

                if now - last_heartbeat >= 8.0:
                    last_heartbeat = now
                    elapsed_s = int(now - train_started)
                    emit(
                        {
                            "type": "heartbeat",
                            "phase": "train",
                            "elapsed_s": elapsed_s,
                            "message": _train_status_hint(work_dir),
                        }
                    )

                path = stats_path or find_learning_stats_path(work_dir)
                if path is not None and path.is_file():
                    stats_path = path
                    row = parse_latest_learning_stats_row(path)
                    if row is not None and row.epoch > last_epoch:
                        last_epoch = row.epoch
                        _emit_epoch_progress(row, epochs=epochs)
                        if (
                            stop_when_done_after is not None
                            and row.epoch > stop_when_done_after
                        ):
                            emit(
                                {
                                    "type": "stopped",
                                    "epoch": row.epoch,
                                    "message": (
                                        f"Stopped after epoch {row.epoch}. "
                                        "Checkpoint saved on disk."
                                    ),
                                }
                            )
                            clear_stop_flag(work_dir)
                            force_stop.set()
                            return
                time.sleep(0.5)

        t = threading.Thread(target=poll_stats, daemon=True)
        t.start()

        def run_dlc_train() -> None:
            gputouse = 0 if device is not None else None
            # YAML often has display_iters: 0; DLC uses it as a modulo divisor and crashes.
            dlc.train_network(
                config_path,
                epochs=epochs,
                save_epochs=SNAPSHOT_SAVE_EPOCHS,
                max_snapshots_to_keep=snapshot_keep_count(epochs),
                display_iters=500,
                device=device,
                gputouse=gputouse,
            )

        train_thread = threading.Thread(target=run_dlc_train, daemon=True)
        train_thread.start()
        try:
            while train_thread.is_alive():
                if force_stop.is_set():
                    os._exit(0)
                time.sleep(0.25)
        finally:
            stop.set()
            t.join(timeout=2.0)
            train_thread.join(timeout=1.0)
        from core.pose.training.model_registry import archive_completed_training

        record = archive_completed_training(job, epochs=epochs)
        if record is not None:
            emit({"type": "model_saved", "run": record.to_dict()})
        emit({"type": "status", "message": "Training finished (DLC)."})
        return

    # Simulated training when DLC is not installed (UI / smoke tests).
    loss = 2.5
    for ep in range(1, epochs + 1):
        if stop_requested(work_dir):
            emit({"type": "stopped", "epoch": ep - 1, "message": "Stopped after epoch."})
            return
        loss *= 0.92
        emit({"type": "epoch", "epoch": ep, "total_epochs": epochs, "loss": round(loss, 4)})
        time.sleep(0.15)
    emit({"type": "status", "message": "Training finished (simulated — install deeplabcut in pose env)."})


def run_analyze(job: dict, *, use_gpu: bool = False) -> None:
    from core.pose.training.analyze_progress import total_analyze_frames

    total_frames = total_analyze_frames(job)
    emit({"type": "phase", "phase": "analyze", "total_frames": total_frames})
    emit({"type": "analyze_start", "total_frames": total_frames})

    config_path = job["config_path"]
    videos = job.get("video_sources") or []
    work_dir = Path(job["work_dir"])

    snapshot_path = job.get("snapshot_path")
    if snapshot_path:
        from core.pose.training.model_registry import stage_snapshot_for_analyze

        staged = stage_snapshot_for_analyze(work_dir, Path(snapshot_path))
        emit({"type": "status", "message": f"Using model weights: {staged.name}"})

    if try_import_dlc():
        import threading

        import deeplabcut as dlc

        device = _resolve_training_device(use_gpu)
        if use_gpu and device is None:
            emit(
                {
                    "type": "status",
                    "message": "GPU unavailable for analysis; running on CPU.",
                }
            )
        gputouse = 0 if device is not None else None
        if videos:
            dlc.analyze_videos(
                config_path,
                videos,
                save_as_csv=True,
                gputouse=gputouse,
                snapshot_index="best",
                device=device,
            )

        if total_frames > 0:
            emit(
                {
                    "type": "frame",
                    "frame": total_frames,
                    "total_frames": total_frames,
                    "phase": "analyze",
                }
            )

        from core.pose.training.dlc_analyze_import import import_dlc_analyze_outputs_to_ai_labelled

        written = import_dlc_analyze_outputs_to_ai_labelled(job)
        if written:
            emit(
                {
                    "type": "status",
                    "message": f"AI predictions saved for {len(written)} video(s) under ai_labelled/.",
                }
            )
        else:
            emit(
                {
                    "type": "status",
                    "message": (
                        "Video analysis finished but no prediction CSV was found next to the "
                        "source video. Check that training produced model snapshots, then re-run "
                        "analyze."
                    ),
                }
            )
        emit({"type": "status", "message": "Video analysis finished (DLC)."})
        return

    # Simulated analyze: write placeholder marker per video.
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    from app_platform.paths import ai_labelled_dir, human_labelled_dir, pose_video_dir  # noqa: E402
    from core.pose.dataset.export_dlc import export_dlc_csv  # noqa: E402
    from core.pose.labeling.labels_store import load_labels  # noqa: E402
    from core.pose.video.video_registry import read_video_meta  # noqa: E402

    session_name = job["session_name"]
    project_id = job["project_id"]
    for vid in job.get("video_ids") or []:
        vdir = pose_video_dir(session_name, project_id, vid)
        meta = read_video_meta(vdir)
        frame_count = meta.frame_count if meta else 0
        if frame_count <= 0:
            frame_count = max(1, total_frames)
        for fi in range(0, frame_count, max(1, frame_count // 20)):
            emit(
                {
                    "type": "frame",
                    "frame": min(fi + 1, frame_count),
                    "total_frames": frame_count,
                    "phase": "analyze",
                }
            )
            time.sleep(0.02)
        emit(
            {
                "type": "frame",
                "frame": frame_count,
                "total_frames": frame_count,
                "phase": "analyze",
            }
        )
        ds = load_labels(human_labelled_dir(session_name, project_id, vid))
        out_dir = ai_labelled_dir(session_name, project_id, vid)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / "tracking.csv"
        export_dlc_csv(ds, frame_count, out_csv, scorer=job.get("scorer", "pose_studio"))
        marker = out_dir / "analyze_mode.txt"
        marker.write_text("simulated\n", encoding="utf-8")
    emit({"type": "status", "message": "Analysis finished (simulated CSV from human labels)."})


def run_auto_label(job: dict, *, use_gpu: bool = False) -> None:
    from core.pose.training.analyze_progress import total_analyze_frames

    total_frames = total_analyze_frames(job)
    emit({"type": "phase", "phase": "auto_label", "total_frames": total_frames})
    emit({"type": "analyze_start", "total_frames": total_frames})

    work_dir = Path(job["work_dir"])
    snapshot_path = job.get("snapshot_path")
    if snapshot_path:
        from core.pose.training.model_registry import stage_snapshot_for_analyze

        staged = stage_snapshot_for_analyze(work_dir, Path(snapshot_path))
        emit({"type": "status", "message": f"Using model weights: {staged.name}"})
        job = dict(job)
        job["snapshot_path"] = str(staged)

    device = _resolve_training_device(use_gpu)
    if device:
        job = dict(job)
        job["device"] = device
    elif use_gpu:
        emit(
            {
                "type": "status",
                "message": "GPU unavailable for auto-label; running on CPU.",
            }
        )

    auto = job.get("auto_label") or {}
    seed = int(auto.get("seed_frame", 0))
    radius = float(auto.get("search_radius_px", 45.0))
    use_stored = bool(auto.get("use_existing_heatmaps") and auto.get("heatmap_source_dir"))
    finish = bool(auto.get("finish_incomplete_archive") and auto.get("heatmap_source_dir"))
    decode_only = use_stored and not finish
    if decode_only:
        src = auto.get("heatmap_source_dir", "")
        emit(
            {
                "type": "status",
                "message": (
                    f"Auto-label: seed frame {seed}, search radius {radius:.0f}px, "
                    f"decoding saved heatmaps from {Path(src).name}."
                ),
            }
        )
    elif finish:
        src = auto.get("heatmap_source_dir", "")
        emit(
            {
                "type": "status",
                "message": (
                    f"Auto-label: seed frame {seed}, search radius {radius:.0f}px, "
                    f"finishing heatmaps in {Path(src).name} (infer missing frames)."
                ),
            }
        )
    else:
        emit(
            {
                "type": "status",
                "message": (
                    f"Auto-label: seed frame {seed}, search radius {radius:.0f}px, "
                    "blob-masked heatmap decode."
                ),
            }
        )

    from core.pose.inference.auto_label_propagate import run_auto_label_job

    def _progress(completed: int, tot: int, _msg: str) -> None:
        emit(
            {
                "type": "frame",
                "frame": completed,
                "total_frames": tot,
                "phase": "auto_label",
            }
        )

    if decode_only:
        written = run_auto_label_job(job, progress_cb=_progress)
        if written:
            emit(
                {
                    "type": "status",
                    "message": (
                        f"Re-decoded labels from saved heatmaps for {len(written)} video(s) "
                        "under ai_labelled/."
                    ),
                }
            )
        else:
            emit(
                {
                    "type": "status",
                    "message": "Auto-label finished but no tracking.csv was written.",
                }
            )
        emit({"type": "status", "message": "Auto-label finished (saved heatmaps)."})
        return

    if try_import_dlc() and job.get("snapshot_path"):
        written = run_auto_label_job(job, progress_cb=_progress)
        if written:
            emit(
                {
                    "type": "status",
                    "message": (
                        f"Constrained auto-label saved for {len(written)} video(s) "
                        "under ai_labelled/."
                    ),
                }
            )
        else:
            emit(
                {
                    "type": "status",
                    "message": "Auto-label finished but no tracking.csv was written.",
                }
            )
        emit({"type": "status", "message": "Auto-label finished (DLC)."})
        return

    # Simulated path (no DLC / no snapshot): synthetic predictor still exercises pipeline.
    written = run_auto_label_job(job, progress_cb=_progress)
    emit(
        {
            "type": "status",
            "message": (
                f"Auto-label finished (simulated — {len(written)} video(s)). "
                "Install deeplabcut and train a model for real heatmaps."
            ),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Pose Studio DLC subprocess step runner")
    parser.add_argument("--job", required=True, help="Path to train_job.json")
    parser.add_argument(
        "--step",
        default="pipeline",
        choices=["create_training_dataset", "train", "analyze", "auto_label", "pipeline", "dry_run", "probe_gpu"],
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--gpu", action="store_true", help="Use GPU when DLC is available")
    parser.add_argument(
        "--skip-create-dataset",
        action="store_true",
        help="Skip convertcsv2h5 / create_training_dataset (resume mid-training)",
    )
    args = parser.parse_args()

    job_path = Path(args.job)
    if not job_path.is_file():
        emit({"type": "error", "message": f"Job file not found: {job_path}"})
        return 1
    job = load_job(job_path)
    work_dir = Path(job["work_dir"])
    work_dir.mkdir(parents=True, exist_ok=True)

    emit({"type": "start", "step": args.step, "job": str(job_path)})
    try:
        if args.step == "probe_gpu":
            run_probe_gpu()
            emit({"type": "done", "work_dir": str(work_dir)})
            return 0
        if args.step in ("train", "dry_run"):
            if args.step == "train":
                skip_dataset = getattr(args, "skip_create_dataset", False)
                if skip_dataset or should_skip_create_training_dataset(work_dir):
                    prior = read_training_progress(work_dir)
                    if prior is not None and prior[0] > 0:
                        emit(
                            {
                                "type": "status",
                                "message": (
                                    f"Skipping dataset rebuild — resuming from epoch "
                                    f"{prior[0]} with existing training artifacts."
                                ),
                            }
                        )
                else:
                    run_create_training_dataset(job)
                    if stop_requested(work_dir):
                        emit({"type": "stopped", "message": "Stopped before train."})
                        return 0
            run_train(job, args.epochs, args.gpu)
            if stop_requested(work_dir):
                return 0
        if args.step == "analyze":
            run_analyze(job, use_gpu=args.gpu)
        if args.step == "auto_label":
            run_auto_label(job, use_gpu=args.gpu)
        if args.step == "dry_run":
            run_train(job, args.epochs, args.gpu)
            if stop_requested(work_dir):
                return 0
            run_analyze(job, use_gpu=args.gpu)
        emit({"type": "done", "work_dir": str(work_dir)})
        return 0
    except Exception as exc:
        emit({"type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
