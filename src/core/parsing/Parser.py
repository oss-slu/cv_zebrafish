import pandas as pd
import numpy as np

def getDataFrameFromPath(csvPath):
    df = pd.read_csv(csvPath, header=1)
    return df

def getIndex(headerList, headerName):
    for i, name in enumerate(headerList):
        if name == headerName:
            return i
    return -1

def getPointRow(df, columnName):
    columnHeaderList = list(df.columns)
    xPos = getIndex(columnHeaderList, f"{columnName}")
    yPos = getIndex(columnHeaderList, f"{columnName}.1")
    likelihoodPos = getIndex(columnHeaderList, f"{columnName}.2")
    return {"x": xPos, "y": yPos, "conf": likelihoodPos}

def _empty_point(n_frames: int):
    arr = np.full(int(n_frames), np.nan, dtype=float)
    return {"x": arr.copy(), "y": arr.copy(), "conf": arr.copy()}

def getDataFromColumn(df, columnPointDict):
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
    inputValues = {
        "spine": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["spine"]],
        "right_fin": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["right_fin"]],
        "left_fin": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["left_fin"]],
        "clp1": getDataFromColumn(df, getPointRow(df, config["points"]["head"]["pt1"])),
        "clp2": getDataFromColumn(df, getPointRow(df, config["points"]["head"]["pt2"])),
        "tp": getDataFromColumn(df, getPointRow(df, config["points"]["spine"][-1])),
        "head": getDataFromColumn(df, getPointRow(df, config["points"]["spine"][0])),
        "tailPoints": config["points"]["tail"],
        "tail": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["tail"]]
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
