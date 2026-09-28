"""Export a selected frame range of a results DataFrame to CSV.

This module backs the "Export Selected Graph Range Data" feature (issue #115).
It is deliberately free of any Qt/UI code so it can be unit-tested with plain
pandas objects and reused from scripts.

Range semantics
---------------
* A range is a pair of **zero-based row positions** ``(start, end)`` into the
  DataFrame produced by the calculation pipeline (one row per video frame).
* Both ends are **inclusive**: ``(10, 20)`` exports 11 rows.
* The original index and the ``Time`` column are left untouched, so exported
  rows keep their original frame numbers.

Note
----
Metadata columns such as ``timeRangeStart_N`` / ``timeRangeEnd_N`` are only
populated in row 0 of the full dataset. A selected range that does not include
row 0 therefore exports those columns (headers preserved) without their values.

Example
-------
    from src.core.calculations.export_selected_range import (
        default_export_filename,
        export_range_to_csv,
    )

    name = default_export_filename("fish1.csv", 100, 250)   # fish1_frames_100-250.csv
    export_range_to_csv(results_df, 100, 250, name)
"""

from __future__ import annotations

from numbers import Integral
from pathlib import Path
from typing import Any, Optional, Tuple, Union

import pandas as pd

PathLike = Union[str, Path]

DEFAULT_FILENAME_STEM = "results"
CSV_SUFFIX = ".csv"


class InvalidRangeError(ValueError):
    """Raised when a requested export range is empty, malformed, or out of bounds."""


def _as_int(value: Any, name: str) -> int:
    """Return ``value`` as a plain ``int`` or raise :class:`InvalidRangeError`.

    Accepts Python and NumPy integers. Rejects booleans, floats, strings, and
    ``None`` so that a silently truncated or mistyped bound never reaches the
    slice.
    """
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise InvalidRangeError(f"{name} must be a whole number (got {value!r}).")
    return int(value)


def validate_range(df: Optional[pd.DataFrame], start: Any, end: Any) -> Tuple[int, int]:
    """Validate a ``(start, end)`` row range against ``df``.

    Args:
        df: The DataFrame the range refers to.
        start: First row position to include (zero-based).
        end: Last row position to include (zero-based, inclusive).

    Returns:
        The validated ``(start, end)`` as plain integers.

    Raises:
        InvalidRangeError: If ``df`` is missing or empty, either bound is not a
            whole number, ``start`` is negative, ``end`` is past the last row,
            or ``start`` is greater than ``end``.
    """
    if not isinstance(df, pd.DataFrame):
        raise InvalidRangeError("No dataset is available to export.")
    if df.empty:
        raise InvalidRangeError("The dataset is empty; there are no rows to export.")

    start_i = _as_int(start, "Start frame")
    end_i = _as_int(end, "End frame")
    last_row = len(df) - 1

    if start_i < 0:
        raise InvalidRangeError(f"Start frame cannot be negative (got {start_i}).")
    if end_i > last_row:
        raise InvalidRangeError(
            f"End frame {end_i} is beyond the last frame ({last_row})."
        )
    if start_i > end_i:
        raise InvalidRangeError(
            f"Start frame ({start_i}) must not be greater than end frame ({end_i})."
        )
    return start_i, end_i


def select_range(df: Optional[pd.DataFrame], start: Any, end: Any) -> pd.DataFrame:
    """Return the rows of ``df`` from ``start`` to ``end`` (inclusive).

    The result is an independent copy with all columns, the original index, and
    the original values preserved.

    Raises:
        InvalidRangeError: See :func:`validate_range`.
    """
    start_i, end_i = validate_range(df, start, end)
    return df.iloc[start_i : end_i + 1].copy()


def default_export_filename(
    source_csv: Optional[PathLike], start: int, end: int
) -> str:
    """Build a suggested file name such as ``fish1_frames_100-250.csv``.

    Args:
        source_csv: Path of the CSV the data came from. When missing or empty,
            ``results`` is used as the base name.
        start: First exported frame.
        end: Last exported frame.
    """
    stem = Path(str(source_csv)).stem if source_csv else ""
    stem = stem or DEFAULT_FILENAME_STEM
    return f"{stem}_frames_{start}-{end}{CSV_SUFFIX}"


def export_range_to_csv(
    df: Optional[pd.DataFrame],
    start: Any,
    end: Any,
    output_path: PathLike,
) -> Path:
    """Write rows ``start``..``end`` (inclusive) of ``df`` to a CSV file.

    Column headers and values are written exactly as they appear in ``df``; the
    DataFrame index is not written. A ``.csv`` extension is added if
    ``output_path`` has none, and missing parent folders are created.

    Args:
        df: The processed results DataFrame.
        start: First row position to export (zero-based).
        end: Last row position to export (zero-based, inclusive).
        output_path: Destination file.

    Returns:
        The path that was written.

    Raises:
        InvalidRangeError: If the range is invalid (nothing is written).
        OSError: If the file cannot be written.
    """
    subset = select_range(df, start, end)

    path = Path(output_path).expanduser()
    if not path.suffix:
        path = path.with_suffix(CSV_SUFFIX)
    path.parent.mkdir(parents=True, exist_ok=True)

    subset.to_csv(path, index=False)
    return path