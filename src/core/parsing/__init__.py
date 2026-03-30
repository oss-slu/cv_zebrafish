"""
Parsing module for zebrafish kinematic analysis.

Provides CSV parsing and dynamic body part detection
for DLC raw and enriched output CSV formats.
"""

from .body_part_detector import (
    BodyPartDetectionResult,
    detect_body_parts,
    detect_body_parts_from_dataframe,
    get_body_part_names,
    get_grouped_body_parts,
)

__all__ = [
    "BodyPartDetectionResult",
    "detect_body_parts",
    "detect_body_parts_from_dataframe",
    "get_body_part_names",
    "get_grouped_body_parts",
]

__version__ = "1.0.0"
