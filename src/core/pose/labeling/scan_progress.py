"""Unified 0–10000 progress for the pose diversity scan pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

PROGRESS_TOTAL = 10_000
_COARSE_END = 5_500
_REFINE_END = 7_500
_BUILD_END = 9_500


@dataclass
class UnifiedScanProgress:
    """Map pipeline substeps onto one monotonic progress bar."""

    emit: Callable[[int, int, str], None]

    def coarse(self, current: int, total: int, label: str) -> None:
        frac = current / max(1, total)
        value = int(_COARSE_END * frac)
        self.emit(value, PROGRESS_TOTAL, label)

    def refine(self, current: int, total: int, label: str) -> None:
        frac = current / max(1, total)
        span = _REFINE_END - _COARSE_END
        value = _COARSE_END + int(span * frac)
        self.emit(value, PROGRESS_TOTAL, label)

    def begin_build_from_cache(self, label: str) -> None:
        self.emit(_REFINE_END, PROGRESS_TOTAL, label)

    def build_from_cache(self, current: int, total: int, label: str) -> None:
        """Build step when coarse/refine were skipped (disk cache hit)."""
        self.build(current, total, label)

    def build(self, current: int, total: int, label: str) -> None:
        frac = current / max(1, total)
        span = _BUILD_END - _REFINE_END
        value = _REFINE_END + int(span * frac)
        extra = f" ({current}/{total})" if total > 0 else ""
        self.emit(value, PROGRESS_TOTAL, f"{label}{extra}")

    def save(self, label: str) -> None:
        self.emit(_BUILD_END, PROGRESS_TOTAL, label)

    def done(self, label: str = "Pose scan complete") -> None:
        self.emit(PROGRESS_TOTAL, PROGRESS_TOTAL, label)
