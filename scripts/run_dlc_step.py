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
import sys
import time
from pathlib import Path

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


def _find_learning_stats_path(work_dir: Path) -> Path | None:
    pytorch = sorted(
        work_dir.glob("dlc-models-pytorch/**/learning_stats.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if pytorch:
        return pytorch[-1]
    legacy = work_dir / "dlc-models" / "iteration-0" / "learning_stats.csv"
    if legacy.is_file():
        return legacy
    return None


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

        stats_path = _find_learning_stats_path(work_dir)
        stop = threading.Event()

        def poll_stats():
            last_epoch = 0
            while not stop.is_set():
                path = stats_path or _find_learning_stats_path(work_dir)
                if path is not None and path.is_file():
                    try:
                        lines = path.read_text(encoding="utf-8").strip().splitlines()
                        if len(lines) > 1:
                            parts = lines[-1].split(",")
                            if len(parts) >= 2:
                                try:
                                    it = int(float(parts[0]))
                                    loss = float(parts[1])
                                    if it > last_epoch:
                                        last_epoch = it
                                        emit(
                                            {
                                                "type": "epoch",
                                                "epoch": it,
                                                "total_epochs": epochs,
                                                "loss": loss,
                                            }
                                        )
                                except ValueError:
                                    pass
                    except OSError:
                        pass
                time.sleep(0.5)

        t = threading.Thread(target=poll_stats, daemon=True)
        t.start()
        try:
            gputouse = 0 if device is not None else None
            dlc.train_network(
                config_path,
                epochs=epochs,
                save_epochs=1,
                display_iters=0,
                device=device,
                gputouse=gputouse,
            )
        finally:
            stop.set()
            t.join(timeout=2.0)
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
    emit({"type": "phase", "phase": "analyze"})
    config_path = job["config_path"]
    videos = job.get("video_sources") or []

    if try_import_dlc():
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
            dlc.analyze_videos(config_path, videos, save_as_csv=True, gputouse=gputouse)
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
        ds = load_labels(human_labelled_dir(session_name, project_id, vid))
        out_dir = ai_labelled_dir(session_name, project_id, vid)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_csv = out_dir / "tracking.csv"
        export_dlc_csv(ds, frame_count, out_csv, scorer=job.get("scorer", "pose_studio"))
        marker = out_dir / "analyze_mode.txt"
        marker.write_text("simulated\n", encoding="utf-8")
    emit({"type": "status", "message": "Analysis finished (simulated CSV from human labels)."})


def main() -> int:
    parser = argparse.ArgumentParser(description="Pose Studio DLC subprocess step runner")
    parser.add_argument("--job", required=True, help="Path to train_job.json")
    parser.add_argument(
        "--step",
        default="pipeline",
        choices=["create_training_dataset", "train", "analyze", "pipeline", "dry_run", "probe_gpu"],
    )
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--gpu", action="store_true", help="Use GPU when DLC is available")
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
        if args.step in ("create_training_dataset", "pipeline"):
            run_create_training_dataset(job)
            if stop_requested(work_dir):
                emit({"type": "stopped", "message": "Stopped before train."})
                return 0
        if args.step in ("train", "pipeline", "dry_run"):
            run_train(job, args.epochs, args.gpu)
            if stop_requested(work_dir):
                return 0
        if args.step in ("analyze", "pipeline", "dry_run"):
            run_analyze(job, use_gpu=args.gpu)
        emit({"type": "done", "work_dir": str(work_dir)})
        return 0
    except Exception as exc:
        emit({"type": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
