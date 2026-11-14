"""Normalize the ways a CSV can be passed into the analysis core."""

from __future__ import annotations

import os
from typing import IO, Union

import pandas as pd

CsvSource = Union[str, "os.PathLike[str]", IO, pd.DataFrame]


class InputSourceError(ValueError):
    """The input could not be read as a CSV table."""


def is_path(source: CsvSource) -> bool:
    """Return True if ``source`` is a filesystem path (str or PathLike)."""
    return isinstance(source, (str, os.PathLike))


def load_csv_source(source: CsvSource) -> pd.DataFrame:
    """Return a DataFrame from a path, file-like object, or DataFrame.

    A DataFrame is returned as a copy so callers cannot mutate the original.
    File-like objects are rewound first so they can be read more than once.

    Raises:
        InputSourceError: If the content is empty or cannot be parsed.
        FileNotFoundError: If ``source`` is a path that does not exist.
    """
    if isinstance(source, pd.DataFrame):
        return source.copy()
    if hasattr(source, "seek"):
        source.seek(0)
    try:
        return pd.read_csv(source)
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise InputSourceError(f"Could not read the file as a CSV table: {exc}") from exc
    