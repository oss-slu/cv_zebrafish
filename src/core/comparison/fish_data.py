"""Load fish for comparison: validate a DeepLabCut CSV and run the analysis.

This module has no PyQt imports, so it can be reused outside the desktop app.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import pandas as pd

from src.core.calculations.Driver import run_calculations
from src.core.parsing.Parser import parse_dlc_csv
from src.core.validation import csv_verifier

PathLike = Union[str, Path]
ProgressCallback = Callable[[int, int, str], None]


class FishLoadError(Exception):
    """A fish file could not be loaded; the message is safe to show to the user."""


@dataclass
class LoadedFish:
    """One fish held in memory for comparison."""

    fish_id: str
    label: str
    source_file: str
    results: pd.DataFrame
    warnings: List[str] = field(default_factory=list)


def unique_label(label: str, taken: Iterable[str]) -> str:
    """Return ``label``, or ``label (2)``, ``label (3)``... if it is already taken."""
    taken_labels = set(taken)
    base = label.strip() or "Fish"
    candidate = base
    suffix = 2
    while candidate in taken_labels:
        candidate = f"{base} ({suffix})"
        suffix += 1
    return candidate


def load_fish(
    csv_path: PathLike,
    config: Dict[str, Any],
    fish_id: str,
    label: Optional[str] = None,
) -> LoadedFish:
    """
    Validate a DeepLabCut CSV and run the analysis pipeline on it.

    Raises:
        FishLoadError: If the file is invalid or the analysis fails or is empty.
    """
    path = Path(csv_path)
    try:
        errors, warnings = csv_verifier.verify_deeplabcut_csv(str(path))
    except Exception as exc:
        raise FishLoadError(f"Could not read the file: {exc}") from exc
    if errors:
        raise FishLoadError("\n".join(str(error) for error in errors))

    try:
        parsed_points = parse_dlc_csv(str(path), config)
        results = run_calculations(parsed_points, config)
    except Exception as exc:
        raise FishLoadError(f"Analysis failed: {exc}") from exc
    if results is None or results.empty:
        raise FishLoadError(
            "The analysis produced no results. Check that the config matches the file's body parts."
        )

    return LoadedFish(
        fish_id=fish_id,
        label=label or path.stem,
        source_file=str(path),
        results=results,
        warnings=[str(warning) for warning in warnings],
    )


def load_fish_batch(
    csv_paths: Sequence[PathLike],
    config: Dict[str, Any],
    existing_labels: Iterable[str] = (),
    first_number: int = 1,
    on_progress: Optional[ProgressCallback] = None,
) -> Tuple[List[LoadedFish], List[Tuple[str, str]]]:
    """
    Load several files, skipping any that fail instead of stopping.

    Args:
        csv_paths: Files to load.
        config: Analysis config applied to every file.
        existing_labels: Labels already in use, so new labels stay unique.
        first_number: Number used for the first new fish ID (``fish_<n>``).
        on_progress: Called as ``(index, total, file_name)`` before each file.

    Returns:
        ``(loaded_fish, failures)`` where failures are ``(path, message)`` pairs.
    """
    loaded: List[LoadedFish] = []
    failures: List[Tuple[str, str]] = []
    taken_labels = set(existing_labels)
    number = first_number

    for index, csv_path in enumerate(csv_paths, start=1):
        if on_progress is not None:
            on_progress(index, len(csv_paths), Path(csv_path).name)
        label = unique_label(Path(csv_path).stem, taken_labels)
        try:
            fish = load_fish(csv_path, config, f"fish_{number}", label)
        except FishLoadError as exc:
            failures.append((str(csv_path), str(exc)))
            continue
        taken_labels.add(fish.label)
        loaded.append(fish)
        number += 1

    return loaded, failures