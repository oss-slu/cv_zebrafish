"""
Dynamic body part detection module for zebrafish kinematic analysis.

Detects body part names automatically from DLC CSV files and enriched
output CSVs instead of relying on hardcoded names. This allows the
pipeline to work with any lab's tracking configuration.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Core result dataclass
# ---------------------------------------------------------------------------

class BodyPartDetectionResult:
    """
    Structured result from body part detection.

    Attributes:
        all_body_parts: Complete list of all detected body part names.
        grouped: Body parts grouped by category (spine, fin, tail, etc.)
                 as detected from the CSV structure.
        source_type: Either 'dlc_raw' or 'enriched' depending on CSV type.
        column_map: Mapping of body part name to column indices
                    {name: {'x': int, 'y': int, 'conf': int}}.
        skipped_columns: Columns that could not be mapped to a body part.
        warnings: Non-fatal issues encountered during detection.
    """

    def __init__(
        self,
        all_body_parts: List[str],
        grouped: Dict[str, List[str]],
        source_type: str,
        column_map: Dict[str, Dict[str, int]],
        skipped_columns: List[str],
        warnings: List[str],
    ):
        self.all_body_parts = all_body_parts
        self.grouped = grouped
        self.source_type = source_type
        self.column_map = column_map
        self.skipped_columns = skipped_columns
        self.warnings = warnings

    def to_dict(self) -> Dict[str, Any]:
        """Serialise result to a plain dictionary."""
        return {
            "all_body_parts": self.all_body_parts,
            "grouped": self.grouped,
            "source_type": self.source_type,
            "column_map": self.column_map,
            "skipped_columns": self.skipped_columns,
            "warnings": self.warnings,
            "body_part_count": len(self.all_body_parts),
        }

    def __repr__(self) -> str:
        return (
            f"BodyPartDetectionResult("
            f"source_type='{self.source_type}', "
            f"body_parts={self.all_body_parts}, "
            f"groups={list(self.grouped.keys())})"
        )

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_body_parts(csv_path: str) -> BodyPartDetectionResult:
    """
    Automatically detect body parts from a CSV file.

    Supports CSV formats:
    1. Raw DLC output: has `scorer` / `bodyparts` / `coords` header rows (classic x,y,likelihood or XY-only x,y per part)
    2. Enriched output: has prefixed columns like Spine_Head_x, LeftFin_LF1_x

    Args:
        csv_path: Path to the CSV file (raw DLC or enriched output).

    Returns:
        BodyPartDetectionResult with all detected body parts and their
        column mappings.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If the file cannot be parsed as a valid CSV.

    Example:
        >>> result = detect_body_parts('data/samples/csv/correct_format.csv')
        >>> print(result.all_body_parts)
        ['BF', 'ET', 'Head', 'LF1', 'LF2', 'LE', 'RE', ...]
        >>> print(result.grouped)
        {'spine': ['Head', 'BF', ...], 'left_fin': ['LF1', 'LF2'], ...}
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    warn_list: List[str] = []

    # Detect which format the CSV is in
    source_type = _detect_csv_format(path)

    if source_type == "dlc_raw":
        return _detect_from_dlc_raw(path, warn_list)
    else:
        return _detect_from_enriched(path, warn_list)

def detect_body_parts_from_dataframe(
    df: pd.DataFrame,
    source_type: str = "auto",
) -> BodyPartDetectionResult:
    """
    Detect body parts from an already-loaded DataFrame.

    Args:
        df: DataFrame loaded from a DLC CSV or enriched CSV.
        source_type: 'dlc_raw', 'enriched', or 'auto' (default).
                     'auto' will try to detect the format automatically.

    Returns:
        BodyPartDetectionResult.

    Example:
        >>> df = pd.read_csv('correct_format.csv', header=1)
        >>> result = detect_body_parts_from_dataframe(df)
    """
    warn_list: List[str] = []

    if source_type == "auto":
        source_type = _detect_format_from_columns(list(df.columns))

    if source_type == "dlc_raw":
        return _detect_from_dlc_df(df, warn_list)
    else:
        return _detect_from_enriched_df(df, warn_list)

def get_body_part_names(csv_path: str) -> List[str]:
    """
    Convenience function: return just the list of body part names.

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Sorted list of unique body part names detected in the CSV.

    Example:
        >>> names = get_body_part_names('correct_format.csv')
        >>> print(names)
        ['BF', 'ET', 'Head', 'LF1', 'LF2', ...]
    """
    result = detect_body_parts(csv_path)
    return result.all_body_parts

def get_grouped_body_parts(csv_path: str) -> Dict[str, List[str]]:
    """
    Convenience function: return body parts grouped by category.

    Groups are inferred from naming patterns:
    - Spine points: Head, BF, SB, T1-T10, ET
    - Left fin points: LF1, LF2
    - Right fin points: RF1, RF2
    - Eye points: LE, RE
    - Unknown: anything that does not match known patterns

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Dictionary mapping group name to list of body part names.

    Example:
        >>> groups = get_grouped_body_parts('correct_format.csv')
        >>> print(groups['spine'])
        ['Head', 'BF', 'SB', 'T1', 'T2', ...]
    """
    result = detect_body_parts(csv_path)
    return result.grouped

# ---------------------------------------------------------------------------
# Private: format detection
# ---------------------------------------------------------------------------

def _detect_csv_format(path: Path) -> str:
    """
    Detect whether a CSV is raw DLC format or enriched output format.
    Reads only the first row to determine format efficiently.
    """
    try:
        header_df = pd.read_csv(path, nrows=1, header=None)
        first_row_values = header_df.iloc[0].tolist()

        # Raw DLC CSVs have 'scorer' as the very first cell
        if str(first_row_values[0]).lower().strip() == "scorer":
            return "dlc_raw"

        # Enriched CSVs have column names like Spine_Head_x, LeftFin_LF1_x
        columns = [str(v) for v in first_row_values]
        if any("_x" in col or "_y" in col or "_conf" in col for col in columns):
            return "enriched"

        # Check second interpretation: read with header=0
        df_check = pd.read_csv(path, nrows=0)
        cols = list(df_check.columns)
        if any(
            col.startswith(("Spine_", "LeftFin_", "RightFin_", "Tail_"))
            for col in cols
        ):
            return "enriched"

        return "dlc_raw"

    except Exception:
        return "dlc_raw"

def _detect_format_from_columns(columns: List[str]) -> str:
    """Detect format from column names alone."""
    if any(
        col.startswith(("Spine_", "LeftFin_", "RightFin_", "Tail_"))
        for col in columns
    ):
        return "enriched"
    return "dlc_raw"

# ---------------------------------------------------------------------------
# Private: DLC raw CSV detection
# ---------------------------------------------------------------------------

def _dlc_coord_stride_from_coords_row(coords_row: List[Any]) -> int:
    """
    Return 3 for classic DLC (x, y, likelihood) or 2 for XY-only exports (x, y).

    Detection is based on the coords header row (row 2 in a raw DLC file).
    """
    lowered = [str(v).strip().lower() for v in coords_row]
    return 3 if any(c == "likelihood" for c in lowered) else 2


def _detect_from_dlc_raw(path: Path, warn_list: List[str]) -> BodyPartDetectionResult:
    """
    Detect body parts from a raw DLC CSV file.

    DLC CSV structure:
        Row 0: scorer    - model name repeated
        Row 1: bodyparts - body part name repeated per coordinate column
        Row 2: coords    - x, y, [likelihood] repeated for each bodypart
        Row 3+: data
    """
    try:
        raw = pd.read_csv(path, header=None, nrows=3)
    except Exception as exc:
        raise ValueError(f"Could not read DLC CSV at {path}: {exc}")

    coords_header = raw.iloc[2, 1:].tolist()  # Skip first column (label)
    stride = _dlc_coord_stride_from_coords_row(coords_header)

    # Row 1 contains body part names (repeated once per coordinate column)
    bodyparts_row = raw.iloc[1, 1:].tolist()  # Skip first column (label)

    seen: Set[str] = set()
    ordered_parts: List[str] = []
    column_map: Dict[str, Dict[str, int]] = {}
    skipped: List[str] = []

    for idx, name in enumerate(bodyparts_row):
        name_str = str(name).strip()
        if name_str in ("nan", "", "bodyparts", "coords"):
            skipped.append(f"col_{idx + 1}")
            continue

        if name_str not in seen:
            seen.add(name_str)
            ordered_parts.append(name_str)
            # Column index offset by 1 for the label column
            col_offset = idx + 1
            if stride == 3:
                column_map[name_str] = {
                    "x": col_offset,
                    "y": col_offset + 1,
                    "conf": col_offset + 2,
                }
            else:
                column_map[name_str] = {
                    "x": col_offset,
                    "y": col_offset + 1,
                    "conf": -1,
                }

    if not ordered_parts:
        warn_list.append("No body parts detected in the DLC CSV bodyparts row.")

    grouped = _group_body_parts(ordered_parts)

    return BodyPartDetectionResult(
        all_body_parts=sorted(ordered_parts),
        grouped=grouped,
        source_type="dlc_raw",
        column_map=column_map,
        skipped_columns=skipped,
        warnings=warn_list,
    )

def _detect_from_dlc_df(
    df: pd.DataFrame, warn_list: List[str]
) -> BodyPartDetectionResult:
    """
    Detect body parts from a DataFrame already loaded with header=1
    (the bodyparts row as header), which is how parser.py loads files.

    Column names look like:
        Head, Head.1, Head.2, LE, LE.1, LE.2 ... (with likelihood)
        or Head, Head.1, LE, LE.1 ... (XY-only; no .2 likelihood column)
    The base name (without .N suffix) is the body part name.
    """
    columns = list(df.columns)
    seen: Set[str] = set()
    ordered_parts: List[str] = []
    column_map: Dict[str, Dict[str, int]] = {}
    skipped: List[str] = []

    for idx, col in enumerate(columns):
        col_str = str(col).strip()

        # Skip pandas-added numeric suffixes (.1, .2) — these are y and conf
        if "." in col_str:
            parts = col_str.rsplit(".", 1)
            if parts[-1].isdigit():
                continue

        # Skip known non-body-part columns
        if col_str.lower() in ("coords", "scorer", "bodyparts", "nan", ""):
            skipped.append(col_str)
            continue

        if col_str not in seen:
            seen.add(col_str)
            ordered_parts.append(col_str)
            x_idx = idx
            y_col = f"{col_str}.1"
            conf_col = f"{col_str}.2"
            y_idx = columns.index(y_col) if y_col in columns else -1
            conf_idx = columns.index(conf_col) if conf_col in columns else -1

            column_map[col_str] = {
                "x": x_idx,
                "y": y_idx,
                "conf": conf_idx,
            }

            if y_idx == -1:
                warn_list.append(
                    f"Body part '{col_str}' is missing y column."
                )

    if not ordered_parts:
        warn_list.append("No body parts detected from DataFrame columns.")

    grouped = _group_body_parts(ordered_parts)

    return BodyPartDetectionResult(
        all_body_parts=sorted(ordered_parts),
        grouped=grouped,
        source_type="dlc_raw",
        column_map=column_map,
        skipped_columns=skipped,
        warnings=warn_list,
    )

# ---------------------------------------------------------------------------
# Private: enriched CSV detection
# ---------------------------------------------------------------------------

def _detect_from_enriched(
    path: Path, warn_list: List[str]
) -> BodyPartDetectionResult:
    """Detect body parts from an enriched output CSV file."""
    try:
        df = pd.read_csv(path, nrows=0)  # Read headers only
    except Exception as exc:
        raise ValueError(f"Could not read enriched CSV at {path}: {exc}")

    return _detect_from_enriched_df(df, warn_list)

def _detect_from_enriched_df(
    df: pd.DataFrame, warn_list: List[str]
) -> BodyPartDetectionResult:
    """
    Detect body parts from an enriched DataFrame.

    Enriched columns follow the pattern:
        Spine_Head_x, Spine_Head_y, Spine_Head_conf
        LeftFin_LF1_x, LeftFin_LF1_y, LeftFin_LF1_conf
        RightFin_RF1_x ...
        Tail_T1_x ...
    """
    columns = list(df.columns)

    # Known prefixes that indicate body part coordinate columns
    known_prefixes = ("Spine_", "LeftFin_", "RightFin_", "Tail_")

    # Group prefix to canonical group name mapping
    prefix_to_group = {
        "Spine_": "spine",
        "LeftFin_": "left_fin",
        "RightFin_": "right_fin",
        "Tail_": "tail",
    }

    seen: Set[str] = set()
    ordered_parts: List[str] = []
    column_map: Dict[str, Dict[str, int]] = {}
    grouped: Dict[str, List[str]] = {
        "spine": [],
        "left_fin": [],
        "right_fin": [],
        "tail": [],
        "unknown": [],
    }
    skipped: List[str] = []

    for idx, col in enumerate(columns):
        col_str = str(col).strip()

        # Only process _x columns as the base entry point per body part
        if not col_str.endswith("_x"):
            continue

        matched_prefix = None
        for prefix in known_prefixes:
            if col_str.startswith(prefix):
                matched_prefix = prefix
                break

        if matched_prefix is None:
            skipped.append(col_str)
            continue

                # Extract body part name: e.g. Spine_Head_x -> Head
        inner = col_str[len(matched_prefix):-2]  # Remove prefix and _x suffix

        if inner in seen:
            continue

        seen.add(inner)
        ordered_parts.append(inner)

        # Find corresponding y and conf column indices
        y_col = col_str[:-2] + "_y"   # e.g. Spine_Head_y
        conf_col = col_str[:-2] + "_conf"  # e.g. Spine_Head_conf

        y_idx = columns.index(y_col) if y_col in columns else -1
        conf_idx = columns.index(conf_col) if conf_col in columns else -1

        column_map[inner] = {
            "x": idx,
            "y": y_idx,
            "conf": conf_idx,
        }

        if y_idx == -1 or conf_idx == -1:
            warn_list.append(
                f"Body part '{inner}' is missing y or confidence columns."
            )

        # Add to correct group
        group_name = prefix_to_group.get(matched_prefix, "unknown")
        grouped[group_name].append(inner)

    # Remove empty groups
    grouped = {k: v for k, v in grouped.items() if v}

    if not ordered_parts:
        warn_list.append("No body parts detected from enriched DataFrame columns.")

    return BodyPartDetectionResult(
        all_body_parts=sorted(ordered_parts),
        grouped=grouped,
        source_type="enriched",
        column_map=column_map,
        skipped_columns=skipped,
        warnings=warn_list,
    )


# ---------------------------------------------------------------------------
# Private: grouping logic
# ---------------------------------------------------------------------------

def _group_body_parts(body_parts: List[str]) -> Dict[str, List[str]]:
    """
    Group body parts into categories based on naming patterns.

    Patterns (from correct_format.csv):
        Spine:      Head, BF, SB, T1-T10, ET
        Left fin:   LF1, LF2
        Right fin:  RF1, RF2
        Eyes:       LE, RE
        Unknown:    anything else

    Args:
        body_parts: List of detected body part names.

    Returns:
        Dictionary mapping group name to list of body part names.
    """
    groups: Dict[str, List[str]] = {
        "spine": [],
        "left_fin": [],
        "right_fin": [],
        "eyes": [],
        "unknown": [],
    }

    # Known spine point names
    spine_exact = {"Head", "BF", "SB", "ET"}

    for part in body_parts:
        part_upper = part.upper()

        # Left fin
        if part_upper.startswith("LF"):
            groups["left_fin"].append(part)

        # Right fin
        elif part_upper.startswith("RF"):
            groups["right_fin"].append(part)

        # Left eye
        elif part_upper in ("LE",):
            groups["eyes"].append(part)

        # Right eye
        elif part_upper in ("RE",):
            groups["eyes"].append(part)

        # Known spine exact names
        elif part in spine_exact:
            groups["spine"].append(part)

        # Spine tail segments: T1, T2, ... T10
        elif (
            part_upper.startswith("T")
            and len(part) >= 2
            and part[1:].isdigit()
        ):
            groups["spine"].append(part)

        # Anything else
        else:
            groups["unknown"].append(part)

    # Remove empty groups
    groups = {k: v for k, v in groups.items() if v}

    return groups


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

__all__ = [
    "BodyPartDetectionResult",
    "detect_body_parts",
    "detect_body_parts_from_dataframe",
    "get_body_part_names",
    "get_grouped_body_parts",
]
