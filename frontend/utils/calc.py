from logging import config
import pandas as pd
import numpy as np
import os
from configSetup import loadConfig

def getDataFrameFromPath(csvPath):
    df = pd.read_csv(csvPath, header = 1)
    return df

def setupValueStructs(config, df):
    numRows = len(df)
    calculatedValues = {
        "rightFinAngles": np.zeros(numRows),
        "leftFinAngles": np.zeros(numRows),
        "rightFinThreePointAngles": np.zeros(numRows),
        "leftFinThreePointAngles": np.zeros(numRows),
        "tailDistances": np.zeros(numRows),
        "sides": np.array([""] * numRows, dtype=object),
        "headX": np.zeros(numRows),
        "headY": np.zeros(numRows),
        "headPixelsX": np.zeros(numRows),
        "headPixelsY": np.zeros(numRows),
        "tailPixelsX": np.zeros(numRows),
        "tailPixelsY": np.zeros(numRows),
        "tailRelativePos": np.zeros(numRows),
        "headYaw": np.zeros(numRows),
        "furthestTailPoint": np.array([""] * numRows, dtype=object)
    }

    ###Data is acquired for input values via the data file, and getDataFromColumn()

    test = [print(getPointRow(df, p)) for p in config["points"]["spine"]]
    print("config:" + str(config))
    inputValues = {
        #Spine points for head tracking points and spine plot
        "spine": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["spine"]],
        #Fins:
        "rightFin": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["right_fin"]],
        "leftFin": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["left_fin"]],
        #Center line
        "clp1": getDataFromColumn(df, getPointRow(df, config["points"]["head"]["pt1"])),
        "clp2": getDataFromColumn(df, getPointRow(df, config["points"]["head"]["pt2"])),
        #Tail
        "tp": getDataFromColumn(df, getPointRow(df, config["points"]["spine"][len(config["points"]["spine"]) - 1])),
        #Head / Main position
        "head": getDataFromColumn(df, getPointRow(df, config["points"]["spine"][0])),
        #Tail
        "tailPoints": config["points"]["tail"],
        "tail": [getDataFromColumn(df, getPointRow(df, p)) for p in config["points"]["tail"]]
    }

    return calculatedValues, inputValues


""" MATH FUNCTIONS """
def getIndex(headerList, headerName):
    for i in range(0, len(headerList)):
        if (headerList[i] == headerName):
            return i
    return -1

def getDataFromColumn(df, columnPointDict):
    xColumn = pd.to_numeric(df.iloc[1:,columnPointDict["x"]])
    yColumn = pd.to_numeric(df.iloc[1:,columnPointDict["y"]])
    confColumn = pd.to_numeric(df.iloc[1:,columnPointDict["conf"]])

    length = len(xColumn)
    dataPoints = []

    for i in range(0, length):
        dataPoints.append({
            "x": xColumn.iloc[i],
            "y": yColumn.iloc[i],
            "conf": confColumn.iloc[i]
        })

    return dataPoints

def getFinAngle(head1, head2, finPoints, leftFin = False):
    if len(finPoints) < 2:
        return 0

    # Head vector: head2 - head1
    v1x = head2['x'] - head1['x']
    v1y = head2['y'] - head1['y']

    # Fin vector: tip - base (stable ordering!)
    base = finPoints[0]
    tip = finPoints[-1]
    v2x = tip['x'] - base['x']
    v2y = tip['y'] - base['y']

    # Angle from head vector to fin vector
    angle_rad = np.arctan2(v2y, v2x) - np.arctan2(v1y, v1x)
    angle_deg = np.degrees(angle_rad)

    # Normalize to [-180, 180]
    if angle_deg < -180:
        angle_deg += 360
    elif angle_deg > 180:
        angle_deg -= 360

    # Flip for left fin
    if leftFin:
        return angle_deg
    else:
        return -angle_deg

def getPointRow(df, columnName):
    columnHeaderList = list(df.columns)
    xPos = getIndex(columnHeaderList, f"{columnName}")
    yPos = getIndex(columnHeaderList, f"{columnName}.1")
    likelihoodPos = getIndex(columnHeaderList, f"{columnName}.2")

    return {"x":xPos, "y":yPos, "conf":likelihoodPos}

def getYawDeg(x1, y1, x2, y2):
    dx = x2 - x1
    dy = y2 - y1
    angleRad = np.arctan2(dy, dx)
    angleDeg = np.degrees(angleRad)
    return -angleDeg

def getAngleBetweenPoints(A, B, C):   
    # Vectors from B to A and B to C
    BA = np.array([A["x"] - B["x"], A["y"] - B["y"]], dtype=float)
    BC = np.array([C["x"] - B["x"], C["y"] - B["y"]], dtype=float)

    # Guard against zero-length segments
    nBA = np.linalg.norm(BA)
    nBC = np.linalg.norm(BC)
    if nBA == 0 or nBC == 0:
        return np.nan  # or 0.0, depending on your preference

    # Dot- and cross- (z component) for the 2D vectors
    dot   = float(np.dot(BA, BC))
    cross = float(BA[0]*BC[1] - BA[1]*BC[0])  # >0 means BC is CCW from BA

    # Unsigned angle between BA and BC in [0, π]
    unsigned = np.arctan2(abs(cross), dot)

    # Deflection from "straight" (π radians), carry the sign from the cross
    signed = np.sign(cross) * (np.pi - unsigned)

    return np.degrees(signed)


if __name__ == "__main__":
    # test paths
    csv_test_path = "./../../data_schema_validation/sample_inputs/csv/correct_format.csv"
    json_test_path = "./../../data_schema_validation/sample_inputs/jsons/BaseConfig.json"

    # tests they exist
    if not os.path.exists(csv_test_path):
        raise FileNotFoundError(f"Test CSV file not found: {csv_test_path}")
    if not os.path.exists(json_test_path):
        raise FileNotFoundError(f"Test JSON file not found: {json_test_path}")

    config = loadConfig(json_test_path)
    df = getDataFrameFromPath(csv_test_path)
    calculatedValues, inputValues = setupValueStructs(config, df)