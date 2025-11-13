import pandas as pd
import numpy as np

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
    BA = np.array([A["x"] - B["x"], A["y"] - B["y"]])
    BC = np.array([C["x"] - B["x"], C["y"] - B["y"]])
    
    # Compute cosine of angle
    cosine_angle = np.dot(BA, BC) / (np.linalg.norm(BA) * np.linalg.norm(BC))
    
    # Numerical safety (avoid slight overflows)
    cosine_angle = np.clip(cosine_angle, -1.0, 1.0)
    
    angle_rad = np.arccos(cosine_angle)
    return np.degrees(angle_rad)