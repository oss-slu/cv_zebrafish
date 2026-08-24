"""DLC PyTorch heatmap inference on square fish crops."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass(frozen=True)
class RunnerScoremaps:
    """Raw DLC scoremaps at model resolution plus peak locref offsets."""

    scoremaps: dict[str, np.ndarray]
    peak_locref: dict[str, np.ndarray]


@dataclass(frozen=True)
class CropHeatmapResult:
    """Per-crop heatmaps for decode / persistence."""

    heatmaps: dict[str, np.ndarray]
    peak_locref: dict[str, np.ndarray] | None = None


def _find_pytorch_config(work_dir: Path, snapshot_path: Path | None = None) -> Path | None:
    """
    Locate the DLC 3 PyTorch model config used for inference.

    ``get_pose_inference_runner`` expects ``pytorch_config.yaml`` from the train
    folder (with a ``method`` field), not ``test/pose_cfg.yaml``.
    """
    if snapshot_path is not None:
        adjacent = Path(snapshot_path).parent / "pytorch_config.yaml"
        if adjacent.is_file():
            return adjacent
    candidates = sorted(
        work_dir.glob("dlc-models-pytorch/**/train/pytorch_config.yaml"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _gaussian_heatmap(
    height: int,
    width: int,
    center_x: float,
    center_y: float,
    sigma: float,
    amplitude: float = 1.0,
) -> np.ndarray:
    yy, xx = np.ogrid[:height, :width]
    dist_sq = (xx - center_x) ** 2 + (yy - center_y) ** 2
    return amplitude * np.exp(-dist_sq / (2.0 * sigma * sigma))


def gaussian_heatmaps_from_coords(
    crop_h: int,
    crop_w: int,
    coords: dict[str, tuple[float, float] | None],
    *,
    sigma: float = 8.0,
    amplitude: float = 1.0,
) -> dict[str, np.ndarray]:
    """Build synthetic heatmaps (used when DLC map tensors are unavailable)."""
    out: dict[str, np.ndarray] = {}
    for bp, xy in coords.items():
        hm = np.zeros((crop_h, crop_w), dtype=np.float64)
        if xy is not None:
            hm = _gaussian_heatmap(crop_h, crop_w, xy[0], xy[1], sigma, amplitude)
        out[bp] = hm
    return out


def _heatmaps_are_usable(heatmaps: dict[str, np.ndarray]) -> bool:
    """True when at least one map has a non-trivial peak."""
    for hm in heatmaps.values():
        arr = np.asarray(hm)
        if arr.size > 0 and float(np.nanmax(arr)) > 1e-8:
            return True
    return False


def _peak_locref_at_argmax(
    maps: np.ndarray,
    locref: np.ndarray,
    names: list[str],
) -> dict[str, np.ndarray]:
    """Extract (dx, dy) from locref fields at each bodypart heatmap argmax."""
    lr = np.asarray(locref, dtype=np.float32)
    if lr.ndim == 4 and lr.shape[0] == 1:
        lr = lr[0]
    k = len(names)
    out: dict[str, np.ndarray] = {}
    for i, name in enumerate(names):
        hm = np.asarray(maps[i], dtype=np.float32)
        if hm.size == 0:
            out[name] = np.zeros(2, dtype=np.float32)
            continue
        iy, ix = np.unravel_index(int(np.argmax(hm)), hm.shape)
        dx, dy = 0.0, 0.0
        if lr.ndim == 3 and lr.shape[0] == 2 * k:
            dx = float(lr[2 * i, iy, ix])
            dy = float(lr[2 * i + 1, iy, ix])
        elif lr.ndim == 3 and lr.shape[0] == k and lr.shape[1] == 2:
            dx = float(lr[i, 0, iy, ix])
            dy = float(lr[i, 1, iy, ix])
        out[name] = np.array([dx, dy], dtype=np.float32)
    return out


def poses_array_to_coords(
    poses: np.ndarray,
    bodyparts: list[str],
    *,
    min_likelihood: float = 0.0,
) -> dict[str, tuple[float, float] | None]:
    """
    Map a DLC ``poses`` array to bodypart name → (x, y).

    Expected shapes (first individual used when multiple animals present):
    - ``(n_animals, n_bodyparts, 3)`` — x, y, likelihood
    - ``(n_bodyparts, 3)``
    """
    arr = np.asarray(poses, dtype=np.float64)
    if arr.ndim == 3:
        if arr.shape[0] < 1:
            return {bp: None for bp in bodyparts}
        arr = arr[0]
    if arr.ndim != 2 or arr.shape[1] < 2:
        return {bp: None for bp in bodyparts}

    coords: dict[str, tuple[float, float] | None] = {}
    for i, bp in enumerate(bodyparts):
        if i >= arr.shape[0]:
            coords[bp] = None
            continue
        x, y = float(arr[i, 0]), float(arr[i, 1])
        lik = float(arr[i, 2]) if arr.shape[1] >= 3 else 1.0
        if not np.isfinite(x) or not np.isfinite(y) or lik < min_likelihood:
            coords[bp] = None
        else:
            coords[bp] = (x, y)
    return coords


def parse_runner_prediction(
    pred: object,
    bodyparts: list[str],
    *,
    min_likelihood: float = 0.0,
) -> dict[str, tuple[float, float] | None]:
    """
    Parse one DLC 3 runner inference item into bodypart coordinates.

    DLC returns nested head dicts such as::

        {"bodypart": {"poses": ndarray(n_animals, n_kpts, 3)}}

    Older / test mocks may use bodypart-name keys directly.
    """
    if pred is None:
        return {bp: None for bp in bodyparts}

    # Legacy / mock: {"Head": [x, y], ...}
    if isinstance(pred, dict) and bodyparts and bodyparts[0] in pred:
        coords: dict[str, tuple[float, float] | None] = {}
        for bp in bodyparts:
            val = pred.get(bp)
            if isinstance(val, (list, tuple, np.ndarray)) and len(val) >= 2:
                coords[bp] = (float(val[0]), float(val[1]))
            else:
                coords[bp] = None
        return coords

    poses = None
    if isinstance(pred, dict):
        for head in ("bodypart", "bodyparts", "pose"):
            block = pred.get(head)
            if isinstance(block, dict) and "poses" in block:
                poses = block["poses"]
                break
            if isinstance(block, np.ndarray):
                poses = block
                break
        if poses is None and "poses" in pred:
            poses = pred["poses"]

    if poses is None:
        return {bp: None for bp in bodyparts}
    return poses_array_to_coords(poses, bodyparts, min_likelihood=min_likelihood)


class SyntheticHeatmapPredictor:
    """Test predictor: peaks near previous-frame crop positions with small jitter."""

    def __init__(self, *, noise_px: float = 2.0) -> None:
        self._noise_px = noise_px
        self._last: dict[str, tuple[float, float]] = {}

    def seed(self, positions_crop: dict[str, tuple[float, float] | None]) -> None:
        self._last = {k: v for k, v in positions_crop.items() if v is not None}

    def predict_crop(
        self,
        crop_bgr: np.ndarray,
        bodyparts: list[str],
    ) -> CropHeatmapResult:
        h, w = crop_bgr.shape[:2]
        coords: dict[str, tuple[float, float] | None] = {}
        for bp in bodyparts:
            prev = self._last.get(bp)
            if prev is None:
                coords[bp] = (w * 0.5, h * 0.5)
            else:
                jitter = np.random.uniform(-self._noise_px, self._noise_px, size=2)
                coords[bp] = (prev[0] + float(jitter[0]), prev[1] + float(jitter[1]))
        heatmaps = gaussian_heatmaps_from_coords(h, w, coords)
        self._last = {k: v for k, v in coords.items() if v is not None}
        return CropHeatmapResult(heatmaps=heatmaps)


class DlcCropHeatmapPredictor:
    """
    Run DLC 3 PyTorch on each crop and return per-bodypart scoremaps.

    Prefers raw scoremaps from the runner preprocessor + model (with peak locref).
    Falls back to Gaussian heatmaps from parsed pose coordinates when scoremaps are
    missing or all-zero.
    """

    def __init__(
        self,
        *,
        config_path: Path,
        snapshot_path: Path,
        work_dir: Path,
        device: str | None = None,
    ) -> None:
        self._config_path = Path(config_path)
        self._snapshot_path = Path(snapshot_path)
        self._work_dir = Path(work_dir)
        self._device = device
        self._runner = None
        self._bodyparts: list[str] = []
        self._init_runner()

    def _init_runner(self) -> None:
        try:
            import deeplabcut.pose_estimation_pytorch as dlc_torch
            from deeplabcut.pose_estimation_pytorch.config import read_config_as_dict
        except ImportError as exc:
            raise RuntimeError(
                "deeplabcut is not installed in the DLC Python environment."
            ) from exc

        pose_cfg_path = _find_pytorch_config(self._work_dir, self._snapshot_path)
        if pose_cfg_path is None:
            raise FileNotFoundError(
                f"No pytorch_config.yaml under {self._work_dir / 'dlc-models-pytorch'}. "
                "Train a model on the Train tab first."
            )
        pose_cfg = read_config_as_dict(str(pose_cfg_path))
        if "method" not in pose_cfg:
            raise ValueError(
                f"{pose_cfg_path.name} is missing required field 'method'. "
                "Expected a DLC 3 PyTorch train config next to the snapshot."
            )
        metadata = pose_cfg.get("metadata") or {}
        self._bodyparts = list(metadata.get("bodyparts") or [])
        self._runner = dlc_torch.apis.utils.get_pose_inference_runner(
            pose_cfg,
            snapshot_path=str(self._snapshot_path),
            device=self._device,
        )

    def _coords_from_runner(
        self,
        crop_bgr: np.ndarray,
        bodyparts: list[str],
    ) -> dict[str, tuple[float, float] | None]:
        with tempfile.TemporaryDirectory(prefix="pose_crop_") as tmp:
            img_path = Path(tmp) / "crop.png"
            cv2.imwrite(str(img_path), crop_bgr)
            # Prefer ndarray input when the runner accepts it (avoids disk round-trip
            # quirks); fall back to path string.
            try:
                outputs = self._runner.inference([crop_bgr])
            except Exception:
                outputs = self._runner.inference([str(img_path)])
        if not outputs:
            return {bp: None for bp in bodyparts}
        pred = outputs[0] if isinstance(outputs, list) else outputs
        return parse_runner_prediction(pred, bodyparts)

    def _scoremaps_from_runner(
        self,
        crop_bgr: np.ndarray,
    ) -> RunnerScoremaps | None:
        """Obtain raw scoremaps and peak locref via the runner preprocessor + model."""
        if self._runner is None:
            return None
        try:
            import torch
            import torch.nn.functional as F

            model = getattr(self._runner, "model", None) or getattr(self._runner, "_model", None)
            preprocessor = getattr(self._runner, "preprocessor", None)
            if model is None:
                return None

            rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            if preprocessor is not None:
                prepared, _context = preprocessor(rgb, {})
                if isinstance(prepared, np.ndarray):
                    tensor = torch.from_numpy(prepared)
                else:
                    tensor = prepared
                if not isinstance(tensor, torch.Tensor):
                    return None
                if tensor.ndim == 3:
                    tensor = tensor.unsqueeze(0)
            else:
                # Last resort — usually wrong (no ImageNet norm); prefer coords path.
                tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().unsqueeze(0) / 255.0

            device = next(model.parameters()).device
            tensor = tensor.to(device)
            with torch.no_grad():
                raw = model(tensor)

            maps = None
            locref_maps = None
            apply_sigmoid = False
            if isinstance(raw, dict):
                head = raw.get("bodypart") or raw.get("bodyparts") or next(iter(raw.values()), None)
                if isinstance(head, dict):
                    if "heatmap" in head:
                        maps = head["heatmap"]
                        apply_sigmoid = True
                    if "locref" in head:
                        locref_maps = head["locref"]
                elif "heatmap" in raw:
                    maps = raw["heatmap"]
                    apply_sigmoid = True
                    locref_maps = raw.get("locref")
            elif isinstance(raw, (list, tuple)):
                raw0 = raw[0]
                if isinstance(raw0, dict) and "heatmap" in raw0:
                    maps = raw0["heatmap"]
                    apply_sigmoid = True
                    locref_maps = raw0.get("locref")
                elif hasattr(raw0, "shape") and getattr(raw0, "ndim", 0) == 4:
                    maps = raw0
            elif hasattr(raw, "shape") and raw.ndim == 4:
                maps = raw

            if maps is None:
                return None
            if apply_sigmoid and isinstance(maps, torch.Tensor):
                maps = F.sigmoid(maps)
            if isinstance(maps, torch.Tensor):
                maps = maps[0].detach().cpu().numpy()
            else:
                maps = np.asarray(maps)
                if maps.ndim == 4:
                    maps = maps[0]

            names = self._bodyparts or []
            if maps.ndim != 3 or maps.shape[0] != len(names):
                return None
            scoremaps = {names[i]: np.asarray(maps[i], dtype=np.float32) for i in range(len(names))}

            peak_locref: dict[str, np.ndarray] = {}
            if locref_maps is not None:
                if isinstance(locref_maps, torch.Tensor):
                    locref_maps = locref_maps[0].detach().cpu().numpy()
                else:
                    locref_maps = np.asarray(locref_maps)
                    if locref_maps.ndim == 4:
                        locref_maps = locref_maps[0]
                peak_locref = _peak_locref_at_argmax(maps, locref_maps, names)

            return RunnerScoremaps(scoremaps=scoremaps, peak_locref=peak_locref)
        except Exception:
            return None

    def predict_crop(
        self,
        crop_bgr: np.ndarray,
        bodyparts: list[str],
    ) -> CropHeatmapResult:
        h, w = crop_bgr.shape[:2]
        from core.pose.inference.heatmap_store import full_crop_heatmaps

        runner_out = self._scoremaps_from_runner(crop_bgr)
        if runner_out is not None:
            subset = {bp: runner_out.scoremaps[bp] for bp in bodyparts if bp in runner_out.scoremaps}
            if _heatmaps_are_usable(subset):
                peak_locref = {
                    bp: runner_out.peak_locref[bp]
                    for bp in bodyparts
                    if bp in runner_out.peak_locref
                }
                return CropHeatmapResult(
                    heatmaps=full_crop_heatmaps(subset, h, w),
                    peak_locref=peak_locref or None,
                )

        # Fallback: pose coordinates → Gaussians when raw scoremaps are unavailable.
        coords = self._coords_from_runner(crop_bgr, bodyparts)
        if any(xy is not None for xy in coords.values()):
            return CropHeatmapResult(
                heatmaps=gaussian_heatmaps_from_coords(h, w, coords),
            )

        # Explicit empty maps — caller must treat as failure (do not pretend peaks exist).
        return CropHeatmapResult(
            heatmaps={bp: np.zeros((h, w), dtype=np.float64) for bp in bodyparts},
        )


def build_heatmap_predictor(job: dict) -> DlcCropHeatmapPredictor | SyntheticHeatmapPredictor:
    """Factory used by subprocess and tests."""
    work_dir = Path(job["work_dir"])
    snapshot = job.get("snapshot_path")
    if snapshot and Path(snapshot).is_file():
        device = job.get("device")
        return DlcCropHeatmapPredictor(
            config_path=Path(job["config_path"]),
            snapshot_path=Path(snapshot),
            work_dir=work_dir,
            device=device,
        )
    return SyntheticHeatmapPredictor()
