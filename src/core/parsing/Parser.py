import numpy as np
import pandas as pd


def getDataFrameFromPath(csvPath):
    if isinstance(csvPath, pd.DataFrame):
        return csvPath
    df = pd.read_csv(csvPath, header=1)
    return df


def getIndex(headerList, headerName):
    for i, name in enumerate(headerList):
        if name == headerName:
            return i
    return -1


def getPointRow(df, columnName):
    if isinstance(df.columns, pd.MultiIndex):
        level_names = [n for n in df.columns.names if n is not None]
        bp_level = "bodyparts" if "bodyparts" in level_names else 1
        bodyparts = df.columns.get_level_values(bp_level)
        if columnName in bodyparts:
            return {"bodypart": columnName}
        return {"bodypart": None}

    columnHeaderList = list(df.columns)
    xPos = getIndex(columnHeaderList, f"{columnName}")
    yPos = getIndex(columnHeaderList, f"{columnName}.1")
    likelihoodPos = getIndex(columnHeaderList, f"{columnName}.2")
    return {"x": xPos, "y": yPos, "conf": likelihoodPos}


def _empty_point(n_frames: int):
    arr = np.full(int(n_frames), np.nan, dtype=float)
    return {"x": arr.copy(), "y": arr.copy(), "conf": arr.copy()}


def getDataFromColumn(df, columnPointDict):
    if isinstance(df.columns, pd.MultiIndex):
        n_frames = len(df)
        bp = columnPointDict.get("bodypart")
        if not bp:
            return _empty_point(n_frames)
        level_names = [n for n in df.columns.names if n is not None]
        bp_level = "bodyparts" if "bodyparts" in level_names else 1
        coord_level = "coords" if "coords" in level_names else -1
        sub = df.xs(bp, level=bp_level, axis=1)
        coords = sub.columns.get_level_values(coord_level)
        if "x" not in coords or "y" not in coords:
            return _empty_point(n_frames)
        x_vals = pd.to_numeric(sub.xs("x", level=coord_level, axis=1).iloc[:, 0], errors="coerce").values
        y_vals = pd.to_numeric(sub.xs("y", level=coord_level, axis=1).iloc[:, 0], errors="coerce").values
        if "likelihood" in coords:
            conf_vals = pd.to_numeric(sub.xs("likelihood", level=coord_level, axis=1).iloc[:, 0], errors="coerce").values
        else:
            conf_vals = np.ones(n_frames, dtype=float)
        return {
            "x": x_vals,
            "y": y_vals,
            "conf": conf_vals,
        }

    # DLC CSVs have a "coords" row after the header row; frames start at row index 1.
    n_frames = max(0, len(df.index) - 1)
    x_idx = int(columnPointDict.get("x", -1))
    y_idx = int(columnPointDict.get("y", -1))
    c_idx = int(columnPointDict.get("conf", -1))

    # If x/y are missing, return a NaN point of the correct length
    # instead of accidentally indexing the last column (pandas iloc[-1]).
    if x_idx < 0 or y_idx < 0:
        return _empty_point(n_frames)

    xColumn = pd.to_numeric(df.iloc[1:, x_idx], errors="coerce")
    yColumn = pd.to_numeric(df.iloc[1:, y_idx], errors="coerce")
    # XY-only exports omit likelihood; treat confidence as fully trusted so downstream
    # filters (spine plots, optional min_conf gates) do not drop frames.
    if c_idx < 0:
        conf_vals = np.ones(n_frames, dtype=float)
    else:
        conf_vals = pd.to_numeric(df.iloc[1:, c_idx], errors="coerce").values
    return {
        "x": xColumn.values,
        "y": yColumn.values,
        "conf": conf_vals,
    }


def parse_dlc_csv(csv_path, config):
    df = getDataFrameFromPath(csv_path)
    points_cfg = (config or {}).get("points", {})
    spine_pts = points_cfg.get("spine") or []
    right_fin_pts = points_cfg.get("right_fin") or []
    left_fin_pts = points_cfg.get("left_fin") or []
    head_cfg = points_cfg.get("head") or {}
    tail_pts = points_cfg.get("tail") or []

    clp1_pt = head_cfg.get("pt1")
    clp2_pt = head_cfg.get("pt2")
    tp_pt = spine_pts[-1] if spine_pts else None
    head_pt = spine_pts[0] if spine_pts else None

    inputValues = {
        "spine": [getDataFromColumn(df, getPointRow(df, p)) for p in spine_pts],
        "right_fin": [getDataFromColumn(df, getPointRow(df, p)) for p in right_fin_pts],
        "left_fin": [getDataFromColumn(df, getPointRow(df, p)) for p in left_fin_pts],
        "clp1": getDataFromColumn(df, getPointRow(df, clp1_pt)) if clp1_pt else _empty_point(len(df)),
        "clp2": getDataFromColumn(df, getPointRow(df, clp2_pt)) if clp2_pt else _empty_point(len(df)),
        "tp": getDataFromColumn(df, getPointRow(df, tp_pt)) if tp_pt else _empty_point(len(df)),
        "head": getDataFromColumn(df, getPointRow(df, head_pt)) if head_pt else _empty_point(len(df)),
        "tailPoints": tail_pts,
        "tail": [getDataFromColumn(df, getPointRow(df, p)) for p in tail_pts],
    }

    # Optional: parse custom calculation points (only when enabled).
    try:
        three_cfg = ((config or {}).get("custom_calculations") or {}).get("three_point_angle") or {}
        enabled = bool(three_cfg.get("enabled", False))
        points = three_cfg.get("points") or []
        if enabled and isinstance(points, (list, tuple)) and len(points) == 3:
            labels = [str(p) for p in points]
            inputValues["custom_points"] = {
                lbl: getDataFromColumn(df, getPointRow(df, lbl)) for lbl in labels
            }
    except Exception:
        # Never break the pipeline for optional custom inputs.
        pass

    return inputValues


def parse_adult_dlc_csv(body_points_path, caudal_fin_path=None, config=None):
    """Load adult zebrafish body_points and optional caudal_fin CSVs and parse into inputValues."""
    from .adult_loader import merge_adult_dlc_csvs

    df = merge_adult_dlc_csvs(body_points_path, caudal_fin_path, config=config)
    return parse_dlc_csv(df, config)
