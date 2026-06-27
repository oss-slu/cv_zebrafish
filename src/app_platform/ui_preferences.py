"""Machine-local UI preferences (theme, scale) stored under ``data/local/ui_preferences.json``."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app_platform.paths import ui_preferences_path

_POSE_ENV_NAME = "cv-zebrafish-pose"

_VALID_THEMES = frozenset({"dark", "light"})
_VALID_PRESETS = frozenset({"tiny", "small", "normal", "large", "extra_large"})
_VALID_VIDEO_UPLOAD_POLICIES = frozenset({"ask", "always_copy", "always_reference"})

# Multipliers relative to the design baseline (Normal = current shipped sizes).
PRESET_MULTIPLIERS: dict[str, float] = {
    "tiny": 0.82,
    "small": 0.90,
    "normal": 1.0,
    "large": 1.10,
    "extra_large": 1.22,
}

PRESET_LABELS: list[tuple[str, str]] = [
    ("tiny", "Tiny"),
    ("small", "Small"),
    ("normal", "Normal"),
    ("large", "Large"),
    ("extra_large", "Extra Large"),
]


def dpi_auto_multiplier(
    logical_dpi: float,
    screen_w: int = 1920,
    screen_h: int = 1080,
    device_pixel_ratio: float = 1.0,
) -> float:
    """
    Automatic UI scale using logical resolution, device pixel ratio, and DPI.

    Large canvases (logical QHD+ **or** approx. physical QHD+ via ``width × dpr``)
    map to the **Small** preset (~0.90), matching dense 2K–class layouts including
    2880×1620-like panels under fractional OS scaling.
    """
    try:
        w = max(1, int(screen_w))
        h = max(1, int(screen_h))
    except (TypeError, ValueError):
        w, h = 1920, 1080
    try:
        dpi = float(logical_dpi)
    except (TypeError, ValueError):
        dpi = 96.0
    try:
        dpr = max(1.0, float(device_pixel_ratio))
    except (TypeError, ValueError):
        dpr = 1.0

    approx_pw = int(w * dpr + 0.5)
    approx_ph = int(h * dpr + 0.5)
    dpi_ratio = dpi / 96.0

    large_logical = w >= 2560 and h >= 1400
    large_approx_physical = approx_pw >= 2560 and approx_ph >= 1400

    if large_logical or large_approx_physical:
        base = PRESET_MULTIPLIERS["small"]
    elif w >= 1920 and h >= 1080:
        base = 0.96
    else:
        base = 1.0

    if dpi_ratio > 1.0:
        if large_logical or large_approx_physical:
            # Already using compact scale — lighter DPI correction than smaller desktops.
            base *= max(0.94, min(1.0, 1.04 / dpi_ratio))
        else:
            base *= max(0.88, min(1.0, 1.08 / dpi_ratio))

    return max(0.78, min(1.12, base))


@dataclass
class UiPreferences:
    theme: str = "dark"
    ui_scale_locked: bool = False
    ui_scale_preset: str = "normal"
    last_auto_scale: float = 1.0
    video_upload_policy: str = "ask"
    dlc_python_path: str = ""
    pose_max_frames_to_analyze: int = 300

    def effective_ui_scale(
        self,
        logical_dpi: float,
        screen_w: int = 1920,
        screen_h: int = 1080,
        device_pixel_ratio: float = 1.0,
    ) -> float:
        if self.ui_scale_locked:
            return PRESET_MULTIPLIERS.get(self.ui_scale_preset, 1.0)
        return dpi_auto_multiplier(logical_dpi, screen_w, screen_h, device_pixel_ratio)


def _parse_prefs(raw: dict[str, Any]) -> UiPreferences:
    theme = raw.get("theme", "dark")
    if theme not in _VALID_THEMES:
        theme = "dark"
    locked = bool(raw.get("ui_scale_locked", False))
    preset = raw.get("ui_scale_preset", "normal")
    if preset not in _VALID_PRESETS:
        preset = "normal"
    try:
        last_auto = float(raw.get("last_auto_scale", 1.0))
    except (TypeError, ValueError):
        last_auto = 1.0
    vup = raw.get("video_upload_policy", "ask")
    if vup not in _VALID_VIDEO_UPLOAD_POLICIES:
        vup = "ask"
    dlc_py = str(raw.get("dlc_python_path", "") or "").strip()
    try:
        pose_max = int(raw.get("pose_max_frames_to_analyze", 300))
    except (TypeError, ValueError):
        pose_max = 300
    pose_max = max(10, min(5000, pose_max))
    return UiPreferences(
        theme=theme,
        ui_scale_locked=locked,
        ui_scale_preset=preset,
        last_auto_scale=last_auto,
        video_upload_policy=vup,
        dlc_python_path=dlc_py,
        pose_max_frames_to_analyze=pose_max,
    )


def discover_dlc_python() -> str:
    """Return ``python.exe`` for ``cv-zebrafish-pose`` if installed in a standard conda layout."""
    home = Path.home()
    rel = Path("envs") / _POSE_ENV_NAME / ("python.exe" if os.name == "nt" else "bin/python")
    for root in (
        home / "miniconda3",
        home / "AppData" / "Local" / "miniconda3",
        home / "anaconda3",
        home / "AppData" / "Local" / "anaconda3",
    ):
        candidate = root / rel
        if candidate.is_file():
            return str(candidate)
    return ""


def load_ui_preferences() -> UiPreferences:
    path = ui_preferences_path()
    if not path.is_file():
        prefs = UiPreferences()
    else:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                prefs = UiPreferences()
            else:
                prefs = _parse_prefs(data)
        except (OSError, json.JSONDecodeError):
            prefs = UiPreferences()

    if not prefs.dlc_python_path or not Path(prefs.dlc_python_path).is_file():
        discovered = discover_dlc_python()
        if discovered:
            prefs.dlc_python_path = discovered
            save_ui_preferences(prefs)
    return prefs


def save_ui_preferences(prefs: UiPreferences) -> None:
    path = ui_preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(prefs), indent=2), encoding="utf-8")


def sync_prefs_after_launch(
    prefs: UiPreferences,
    logical_dpi: float,
    screen_w: int = 1920,
    screen_h: int = 1080,
    device_pixel_ratio: float = 1.0,
) -> None:
    """
    Persist prefs on each run when scale follows DPI (unlocked).

    When unlocked, refresh ``last_auto_scale`` and save so the file reflects the
    active automatic multiplier. When locked, do not rewrite the file on startup.
    """
    if prefs.ui_scale_locked:
        return
    prefs.last_auto_scale = dpi_auto_multiplier(
        logical_dpi, screen_w, screen_h, device_pixel_ratio
    )
    save_ui_preferences(prefs)
