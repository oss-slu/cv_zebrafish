"""Global UI scale factor for stylesheets (see ``set_ui_scale_factor``)."""

from __future__ import annotations

import re

_SCALE_FACTOR = 1.0

# Match CSS lengths in pt / px (avoid touching em, %, hex colors).
_RE_PT = re.compile(r"(?P<n>\d+(?:\.\d+)?)\s*pt\b")
_RE_PX = re.compile(r"(?P<n>\d+(?:\.\d+)?)\s*px\b")


def set_ui_scale_factor(factor: float) -> None:
    """Clamp and store the multiplier applied to theme + app QSS (Normal ≈ 1.0)."""
    global _SCALE_FACTOR
    try:
        x = float(factor)
    except (TypeError, ValueError):
        x = 1.0
    _SCALE_FACTOR = max(0.5, min(2.0, x))


def get_ui_scale_factor() -> float:
    return _SCALE_FACTOR


def scaled_px(base: float) -> int:
    """Integer px for layouts (margins, spacing, min sizes) using the global UI scale."""
    try:
        b = float(base)
    except (TypeError, ValueError):
        b = 1.0
    return max(1, int(round(b * get_ui_scale_factor())))


def scale_stylesheet(css: str, factor: float) -> str:
    """Scale ``font-size`` / padding-like ``px`` and ``pt`` tokens in a Qt stylesheet fragment."""

    if not css or abs(factor - 1.0) < 1e-9:
        return css

    def sub_pt(m: re.Match[str]) -> str:
        v = float(m.group("n")) * factor
        s = f"{v:.4f}".rstrip("0").rstrip(".")
        return f"{s}pt"

    def sub_px(m: re.Match[str]) -> str:
        v = float(m.group("n")) * factor
        iv = int(round(v))
        return f"{iv}px"

    out = _RE_PT.sub(sub_pt, css)
    out = _RE_PX.sub(sub_px, out)
    return out


def scale_stylesheet_current(css: str) -> str:
    """Apply the globally configured scale factor."""
    return scale_stylesheet(css, get_ui_scale_factor())
