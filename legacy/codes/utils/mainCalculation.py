from utils.mainFuncs import *
from utils.outputDisplay import getTimeRanges

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

def getCalculated(inputValues, calculatedValues, config, df):
    scaleFactor = config["video_parameters"]["pixel_scale_factor"] * config["video_parameters"]["dish_diameter_m"] / config["video_parameters"]["pixel_diameter"]

    resultsList = []

    #Initialize input values:
    clp1 = inputValues["clp1"]
    clp2 = inputValues["clp2"]
    leftFin = inputValues["leftFin"]
    rightFin = inputValues["rightFin"]
    tp = inputValues["tp"]
    head = inputValues["head"]
    tailPoints = inputValues["tailPoints"]
    tail = inputValues["tail"]
    spine = inputValues["spine"]

    for row in range(0, len(df) - 1):

        # Get center line (2/3 head points)    
        centerlineXs = (clp1[row]["x"], clp2[row]["x"])
        centerlineYs = (clp1[row]["y"], clp2[row]["y"])
        centerlineSlope, intercept = np.polyfit(centerlineXs, centerlineYs, 1)

        # Get right fin angles (2 right fin points)
        calculatedValues["rightFinAngles"][row] = getFinAngle(clp1[row], clp2[row], [p[row] for p in rightFin])

        # Get left fin angles (2 left fin points)
        calculatedValues["leftFinAngles"][row] = getFinAngle(clp1[row], clp2[row], [p[row] for p in leftFin], leftFin=True)

        #Get fin angles (3 fin points)
        if len(rightFin) == 3:
            calculatedValues["rightFinThreePointAngles[row]"] = getAngleBetweenPoints(rightFin[0][row], rightFin[1][row], rightFin[2][row])
            calculatedValues["leftFinThreePointAngles[row]"] = getAngleBetweenPoints(leftFin[0][row], leftFin[1][row], leftFin[2][row])

        #Get distance of tail from center line (tail point)
        tailRelativePos = (centerlineSlope * tp[row]["x"] - tp[row]["y"] + intercept) / np.sqrt(centerlineSlope**2 + 1)

        #exactDistance = abs(tailRelativePos) / np.sqrt(centerlineSlope**2 + 1)
        calculatedValues["tailDistances"][row] = tailRelativePos * scaleFactor

        #Get side of tail from center line
        if tailRelativePos < 0:
            calculatedValues["sides"][row] = "Right"
        elif tailRelativePos > 0:
            calculatedValues["sides"][row] = "Left"
        else:
            calculatedValues["sides"][row] = "On the line"

        #Get head position *** Needs fix with relavent scaling factors for headPixels X & Y
        calculatedValues["headX"][row] = head[row]["x"] * scaleFactor
        calculatedValues["headY"][row] = head[row]["y"] * scaleFactor

        #Get head pixels
        calculatedValues["headPixelsX"][row] = head[row]["x"]
        calculatedValues["headPixelsY"][row] = head[row]["y"]

        #Get tail pixels
        calculatedValues["tailPixelsX"][row] = tp[row]["x"]
        calculatedValues["tailPixelsY"][row] = tp[row]["y"]

        #Get furthest point from midline:
        currentMax = 0
        currentFurthestPoint = tailPoints[0]
        for point in range(len(tail)):
            currentPointDist = (centerlineSlope * tail[point][row]["x"] - tail[point][row]["y"] + intercept) / np.sqrt(centerlineSlope**2 + 1)
            currentAbsDistance = abs(currentPointDist)
            if currentAbsDistance > currentMax:
                currentMax = currentAbsDistance
                currentFurthestPoint = tailPoints[point]
        calculatedValues["furthestTailPoint"][row] = currentFurthestPoint

        #Get head yaw
        calculatedValues["headYaw"][row] = getYawDeg(clp1[row]["x"], clp1[row]["y"], clp2[row]["x"], clp2[row]["y"])
        currentResultsListRow = {
            "Time": row,
            "RF_Angle": calculatedValues["rightFinAngles"][row],
            "LF_Angle": calculatedValues["leftFinAngles"][row],
            "LF_Three_Point_Angle": calculatedValues["leftFinThreePointAngles"][row],
            "RF_Three_Point_Angle": calculatedValues["rightFinThreePointAngles"][row],
            "ET_DistancefromCenterline": calculatedValues["tailRelativePos"], #exactDistance,
            "ET_Side": calculatedValues["sides"][row],
            "Furthest_Tail_Point": calculatedValues["furthestTailPoint"][row]
        }

        #Get spine point angles
        for i in range(len(spine) - 2):
            currentSpineAngle = getAngleBetweenPoints(spine[i][row], spine[i + 1][row], spine[i + 2][row])
            currentResultsListRow[f"TailAngle {i}"] = currentSpineAngle

        #Collect results for current row for final table.
        resultsList.append(currentResultsListRow)

    if (config["auto_find_time_ranges"] == False):
        timeRanges = config["time_ranges"] #  [[100, 200], [300, 400]]
    else:
        timeRanges = getTimeRanges(calculatedValues["leftFinAngles"], calculatedValues["rightFinAngles"], calculatedValues["tailDistances"],
            config["graph_cutoffs"]["left_fin_angle"], config["graph_cutoffs"]["right_fin_angle"],
            config["graph_cutoffs"]["tail_angle"], config["graph_cutoffs"]["movement_bout_width"],
            len(df) - 1,
            config["graph_cutoffs"]["swim_bout_buffer"], config["graph_cutoffs"]["swim_bout_right_shift"],
            config["graph_cutoffs"]["use_tail_angle"])

    #Center head yaw for each swim bout
    for startIndex, endIndex in timeRanges:
        centerYaw = calculatedValues["headYaw"][startIndex]

        for i in range(startIndex, endIndex + 1):
            calculatedValues["headYaw"][i] = calculatedValues["headYaw"][i] - centerYaw

    """ SAVE EXTRA RESULTS TO EXCEL """
    #Fill empty slots with nothing, so the graph won't be put past the time ranges
    for row in range(0, len(df) - 1):
        resultsList[row]["curBoutHeadYaw"] = ""

    for startIndex, endIndex in timeRanges:
        for row in range(startIndex, endIndex + 1):
            resultsList[row]["curBoutHeadYaw"] = calculatedValues["headYaw"][row]

    for timeRange in range(len(timeRanges)):
        resultsList[timeRange]["timeRangeStart"] = timeRanges[timeRange][0]
        resultsList[timeRange]["timeRangeEnd"] = timeRanges[timeRange][1]

    return resultsList, timeRanges