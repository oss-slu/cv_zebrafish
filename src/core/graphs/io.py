"""
IO helpers for graph outputs: folder creation, logging, and Excel export.

This is a modular replacement for the ad-hoc file handling in `outputDisplay.py`.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import pandas as pd


@dataclass(frozen=True)
class OutputContext:
    """Holds paths for an output run."""

    output_folder: str
    log_path: str


def _next_results_folder(base_path: str) -> OutputContext:
    """
    Create the next `Results N` folder under base_path and return its paths.
    Mirrors legacy rotation logic.
    """
    os.makedirs(base_path, exist_ok=True)
    pattern = re.compile(r"^Results (\d+)$")
    existing_numbers = []

    for name in os.listdir(base_path):
        full_path = os.path.join(base_path, name)
        match = pattern.match(name)
        if os.path.isdir(full_path) and match:
            existing_numbers.append(int(match.group(1)))

    next_index = max(existing_numbers) + 1 if existing_numbers else 1
    new_folder_name = f"Results {next_index}"
    output_folder = os.path.join(base_path, new_folder_name)
    os.makedirs(output_folder, exist_ok=True)

    log_path = os.path.join(output_folder, "log.txt")
    return OutputContext(output_folder=output_folder, log_path=log_path)


def get_output_context(config: dict, base_path: str = "results") -> Optional[OutputContext]:
    """
    Create and return an OutputContext unless running bulk input (legacy behavior
    was to skip folder creation when bulk_input is True).
    """
    if config.get("bulk_input"):
        return None
    return _next_results_folder(base_path)


def print_to_output(text: str, ctx: Optional[OutputContext]) -> None:
    """
    Print to console and append to log if a context is available.
    Safe to call with ctx=None (will only print).
    """
    print(text, end="")
    if ctx:
        with open(ctx.log_path, "a", encoding="utf-8") as f:
            f.write(text)


def save_results_to_excel(rows: Iterable[dict], ctx: Optional[OutputContext], filename: str = "output_data.xlsx") -> None:
    """Persist tabular results to Excel in the provided context folder."""
    if not ctx:
        return
    df = pd.DataFrame(rows)
    output_file_path = os.path.join(ctx.output_folder, filename)
    df.to_excel(output_file_path, index=False)


__all__ = ["OutputContext", "get_output_context", "print_to_output", "save_results_to_excel"]
