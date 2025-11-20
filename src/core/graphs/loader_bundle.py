"""
Lightweight container for graphing inputs.

`GraphDataBundle` groups the outputs of `GraphDataLoader` so runner/plot modules
can accept a single argument instead of a wide parameter list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .data_loader import GraphDataLoader


@dataclass(frozen=True)
class GraphDataBundle:
    """
    Structured bundle of graphing inputs.

    Attributes:
        time_ranges: List of [start, end] frame indices for bouts.
        input_values: Nested dict matching legacy `inputValues` shape.
        calculated_values: Dict of numpy arrays matching legacy `calculatedValues`.
        config: Runtime configuration dict.
        dataframe: Optional pandas DataFrame backing the data.
    """

    time_ranges: List[List[int]]
    input_values: Dict[str, Any]
    calculated_values: Dict[str, Any]
    config: Dict[str, Any]
    dataframe: Optional[Any] = None

    @classmethod
    def from_loader(cls, loader: GraphDataLoader) -> "GraphDataBundle":
        """Convenience constructor to pull all required pieces from a loader."""
        return cls(
            time_ranges=loader.get_time_ranges(),
            input_values=loader.get_input_values(),
            calculated_values=loader.get_calculated_values(),
            config=loader.get_config(),
            dataframe=loader.get_dataframe(),
        )


__all__ = ["GraphDataBundle"]
