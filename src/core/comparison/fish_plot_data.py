"""Plot-ready data for the fish comparison view (no PyQt or plotting imports)."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from src.core.analysis.summary_statistics import get_parameter_units
from src.core.comparison.fish_data import LoadedFish

# Okabe-Ito palette: distinguishable for most color-vision types.
FISH_COLORS = (
    "#0072B2",  # blue
    "#E69F00",  # orange
    "#009E73",  # green
    "#D55E00",  # vermillion
    "#CC79A7",  # pink
    "#56B4E9",  # sky blue
    "#F0E442",  # yellow
    "#000000",  # black
)

TIME_COLUMN = "Time"
TIME_AXIS_LABEL = "Time (frames)"


class FishColorMap:
    """
    Gives each fish one color that stays the same in every plot.

    A fish keeps its color when other fish are hidden or renamed. A removed fish
    frees its color for the next fish added. With more fish than palette colors,
    colors repeat.
    """

    def __init__(self, palette: Tuple[str, ...] = FISH_COLORS) -> None:
        self._palette = palette
        self._colors: Dict[str, str] = {}

    def color_for(self, fish_id: str) -> str:
        """Return the fish's color, assigning the least-used palette color if new."""
        if fish_id not in self._colors:
            usage = {color: 0 for color in self._palette}
            for color in self._colors.values():
                usage[color] += 1
            self._colors[fish_id] = min(self._palette, key=lambda color: usage[color])
        return self._colors[fish_id]

    def release(self, fish_id: str) -> None:
        """Forget a removed fish so its color can be reused."""
        self._colors.pop(fish_id, None)


def get_time_series(fish: LoadedFish, parameter: str) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return ``(x, y)`` arrays for one fish and parameter.

    ``x`` is the frame number (the ``Time`` column, or the row number if it is
    missing). Non-numeric values and infinities become NaN so a plotted line
    breaks there instead of failing.

    Raises:
        KeyError: If the fish has no such parameter.
    """
    results = fish.results
    if parameter not in results.columns:
        raise KeyError(f"{fish.label} has no parameter '{parameter}'")

    y = pd.to_numeric(results[parameter], errors="coerce").to_numpy(dtype=float)
    y[~np.isfinite(y)] = np.nan
    if TIME_COLUMN in results.columns:
        x = pd.to_numeric(results[TIME_COLUMN], errors="coerce").to_numpy(dtype=float)
    else:
        x = np.arange(len(results), dtype=float)
    return x, y


def get_axis_labels(parameter: str, custom_units: Optional[Dict[str, str]] = None) -> Tuple[str, str]:
    """Return ``(x_label, y_label)``; the y label includes the unit when known."""
    unit = get_parameter_units(parameter, custom_units)
    y_label = f"{parameter} ({unit})" if unit else parameter
    return TIME_AXIS_LABEL, y_label