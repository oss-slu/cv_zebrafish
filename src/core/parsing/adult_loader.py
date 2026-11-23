"""Adult zebrafish DeepLabCut CSV loader and merger (#153).

Adult zebrafish tracking data comes as two separate DLC CSV files per video:
- body_points (*_1100000.csv): Midline points p0..p9
- caudal_fin (*_600000.csv): Caudal fin landmark caudal_fin

This module validates, aligns, and merges these files into a unified DLC-style
DataFrame, and checks that all bodyparts required by the configuration are present
to prevent silent empty analyses (#143).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

from ..input_source import CsvSource
from ..validation.csv_verifier import verify_deeplabcut_csv


def get_required_bodyparts(config: Dict[str, Any]) -> List[str]:
    """Collect all non-empty bodypart names required by the configuration."""
    points = config.get("points", {})
    required: Set[str] = set()
    for key in ("spine", "tail", "left_fin", "right_fin"):
        val = points.get(key)
        if isinstance(val, (list, tuple)):
            for p in val:
                if isinstance(p, str) and p.strip():
                    required.add(p.strip())
    head = points.get("head")
    if isinstance(head, dict):
        for k in ("pt1", "pt2"):
            pt = head.get(k)
            if isinstance(pt, str) and pt.strip():
                required.add(pt.strip())
    return sorted(required)


def _load_dlc_multiindex(source: CsvSource) -> pd.DataFrame:
    """Load a DeepLabCut CSV source into a DataFrame with (scorer, bodyparts, coords) MultiIndex columns."""
    if isinstance(source, pd.DataFrame):
        if isinstance(source.columns, pd.MultiIndex):
            return source.copy()
        raise ValueError("DataFrame source must have MultiIndex columns: (scorer, bodyparts, coords).")

    df = pd.read_csv(source, header=[0, 1, 2], index_col=0)
    df.columns.names = ["scorer", "bodyparts", "coords"]
    return df


def merge_adult_dlc_csvs(
    body_points_source: CsvSource,
    caudal_fin_source: Optional[CsvSource] = None,
    *,
    config: Optional[Dict[str, Any]] = None,
    unified_scorer: Optional[str] = None,
) -> pd.DataFrame:
    """Merge body_points and optional caudal_fin DeepLabCut CSVs into one combined DLC DataFrame.

    Validates each CSV using verify_deeplabcut_csv, verifies that frame counts match,
    merges on frame index (retaining column definitions even if model scorers differ),
    and validates that all required body parts specified in config are present.

    Args:
        body_points_source: Path, file-like, or DataFrame for the body_points model (p0..p9).
        caudal_fin_source: Optional path, file-like, or DataFrame for the caudal_fin model.
        config: Optional configuration dictionary (e.g. AdultConfig.json) to validate against.
        unified_scorer: Optional name to override the top-level scorer level across all columns.

    Returns:
        pd.DataFrame: Merged DataFrame with MultiIndex columns (scorer, bodyparts, coords)
        and frame index 0..N-1.

    Raises:
        ValueError: If file verification fails, frame counts mismatch, or required bodyparts are missing.
    """
    # 1. Format verification with verify_deeplabcut_csv
    bp_errors, _ = verify_deeplabcut_csv(body_points_source)
    if bp_errors:
        err_msg = "\n".join(bp_errors)
        raise ValueError(f"body_points CSV verification failed:\n{err_msg}")

    if caudal_fin_source is not None:
        cf_errors, _ = verify_deeplabcut_csv(caudal_fin_source)
        if cf_errors:
            err_msg = "\n".join(cf_errors)
            raise ValueError(f"caudal_fin CSV verification failed:\n{err_msg}")

    # 2. Load DataFrames
    body_df = _load_dlc_multiindex(body_points_source)

    if caudal_fin_source is not None:
        caudal_df = _load_dlc_multiindex(caudal_fin_source)

        # 3. Frame count check
        if len(body_df) != len(caudal_df):
            raise ValueError(
                f"Frame count mismatch: body_points has {len(body_df)} frames, "
                f"while caudal_fin has {len(caudal_df)} frames."
            )

        # Align index to body_df to ensure clean frame-by-frame concatenation
        caudal_df.index = body_df.index

        # 4. Concatenate columns
        combined_df = pd.concat([body_df, caudal_df], axis=1)
    else:
        combined_df = body_df.copy()

    if unified_scorer:
        combined_df.columns = pd.MultiIndex.from_tuples(
            [(unified_scorer, bp, coord) for _, bp, coord in combined_df.columns],
            names=["scorer", "bodyparts", "coords"],
        )

    # 5. Required bodyparts validation against config (fixes #143)
    if config is not None:
        required_parts = get_required_bodyparts(config)
        available_parts = set(combined_df.columns.get_level_values(1).unique())
        missing_parts = [p for p in required_parts if p not in available_parts]
        if missing_parts:
            raise ValueError(
                f"Missing required bodyparts in merged adult CSV: {missing_parts}"
            )

    return combined_df
