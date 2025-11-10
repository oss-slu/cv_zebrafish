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

def getDataFromColumn(df, columnPointDict):
    xColumn = pd.to_numeric(df.iloc[1:, columnPointDict["x"]])
    yColumn = pd.to_numeric(df.iloc[1:, columnPointDict["y"]])
    confColumn = pd.to_numeric(df.iloc[1:, columnPointDict["conf"]])
    return {
        "x": xColumn.values,
        "y": yColumn.values,
        "conf": confColumn.values
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
    return inputValues
