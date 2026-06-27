"""Load DLC multi-header CSV into a LabelDataset."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from core.pose.labeling.labels_store import LabelDataset
from core.pose.labeling.schema import PoseSchema

_FRAME_RE = re.compile(r"frame\s*(\d+)", re.IGNORECASE)


def _parse_frame_index(label: str) -> int | None:
    if not label:
        return None
    m = _FRAME_RE.search(str(label).strip())
    if m:
        return int(m.group(1))
    try:
        return int(float(label))
    except (TypeError, ValueError):
        return None


def _bodypart_columns(raw: pd.DataFrame) -> tuple[list[str], dict[str, tuple[int, int]]]:
    bp_cells = [str(v).strip() for v in raw.iloc[1, 1:].tolist()]
    coord_cells = [str(v).strip().lower() for v in raw.iloc[2, 1:].tolist()]

    bodyparts: list[str] = []
    col_map: dict[str, tuple[int, int]] = {}
    i = 0
    while i < len(bp_cells):
        bp = bp_cells[i]
        if not bp or bp.lower() == "nan":
            i += 1
            continue
        # Detect stride from coord row (x,y,likelihood) or (x,y)
        stride = 3
        if i + 1 < len(coord_cells) and coord_cells[i] == "x" and coord_cells[i + 1] == "y":
            if i + 2 < len(coord_cells) and "likelihood" in coord_cells[i + 2]:
                stride = 3
            else:
                stride = 2
        if bp not in col_map:
            bodyparts.append(bp)
            col_map[bp] = (i + 1, i + 2)
        i += stride
    return bodyparts, col_map


def import_dlc_csv(path: Path) -> tuple[LabelDataset, int, list[str]]:
    """
    Parse a DLC-shaped CSV into a LabelDataset.

    Returns ``(dataset, frame_count, bodyparts)``.
    """
    raw = pd.read_csv(path, header=None)
    if raw.shape[0] < 4:
        raise ValueError(f"Not a DLC CSV (need header rows + data): {path}")

    bodyparts, col_map = _bodypart_columns(raw)
    if not bodyparts:
        raise ValueError(f"No bodyparts found in DLC CSV: {path}")

    ds = LabelDataset(schema=PoseSchema(bodyparts=list(bodyparts)))
    max_frame = -1

    for r in range(3, raw.shape[0]):
        row = raw.iloc[r]
        fi = _parse_frame_index(str(row.iloc[0]))
        if fi is None:
            continue
        max_frame = max(max_frame, fi)
        for bp in bodyparts:
            x_col, y_col = col_map[bp]
            try:
                xv = row.iloc[x_col]
                yv = row.iloc[y_col]
            except IndexError:
                continue
            if pd.isna(xv) or pd.isna(yv) or str(xv).strip() == "" or str(yv).strip() == "":
                ds.skip_point(fi, bp)
            else:
                ds.set_point(fi, bp, float(xv), float(yv))

    frame_count = max_frame + 1 if max_frame >= 0 else 0
    return ds, frame_count, bodyparts
