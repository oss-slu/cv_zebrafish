import numpy as np
import pandas as pd
import cv2
import os
import re

import plotly.graph_objects as go
import plotly.io as pio
import plotly.express as px
from plotly.subplots import make_subplots
import webbrowser


""" GLOBALS FOR EVENT HANDLER """
# Lag cooldown handling
lastMoveTime = 0

""" GLOBAL FOR FILE SYSTEM"""
outputsDict = {}

""" OUTPUT FILE FUNCTIONS """


def getOutputFile(config):
    if not config["bulk_input"]:
        basePath = 'results'
        os.makedirs(basePath, exist_ok=True)

        pattern = re.compile(r'^Results (\d+)$')
        existingNumbers = []

        for name in os.listdir(basePath):
            fullPath = os.path.join(basePath, name)
            match = pattern.match(name)
            if os.path.isdir(fullPath) and match:
                existingNumbers.append(int(match.group(1)))

        nextIndex = max(existingNumbers) + 1 if existingNumbers else 1
        newFolderName = f"Results {nextIndex}"
        newFolder = os.path.join(basePath, newFolderName)
        os.makedirs(newFolder)

        logPath = os.path.join(newFolder, "log.txt")

        global outputsDict
        outputsDict = {
            'outputFolder': newFolder,
            'log': logPath
        }
        printToOutput(f"Output folder: {newFolderName}")


def printToOutput(text):
    if len(outputsDict) == 0:
        print(
            "outputsDict variable empty. Try running getOutputFile() before printToOutput()")

    print(text, end="")
    with open(outputsDict["log"], 'a') as f:
        f.write(text)


def saveResultstoExcelFile(df):
    resultDf = pd.DataFrame(df)

    outputFilePath = os.path.join(
        outputsDict['outputFolder'], "output_data.xlsx")
    resultDf.to_excel(outputFilePath)


# main function to run all outputs
def runAllOutputs(timeRanges, config, resultsList, inputValues, calculatedValues, df):
    # get values from structs
    spine = inputValues["spine"]
    """
    calculatedValues = {
    "rightFinThreePointAngles": np.zeros(numRows),
    "leftFinThreePointAngles": np.zeros(numRows),
    "sides": np.array([""] * numRows, dtype=object),
    "furthestTailPoint": np.array([""] * numRows, dtype=object)
    """
    headX = calculatedValues["headX"]
    headY = calculatedValues["headY"]
    leftFinAngles = calculatedValues["leftFinAngles"]
    rightFinAngles = calculatedValues["rightFinAngles"]
    tailDistances = calculatedValues["tailDistances"]
    headYaw = calculatedValues["headYaw"]
    headPixelsX = calculatedValues["headPixelsX"]
    headPixelsY = calculatedValues["headPixelsY"]
    tailPixelsX = calculatedValues["tailPixelsX"]
    tailPixelsY = calculatedValues["tailPixelsY"]

    # headX, headY, df, leftFinAngles, rightFinAngles, tailDistances, spine, headYaw, headPixelsX, headPixelsY, tailPixelsX, tailPixelsY
    timeFactor = config["video_parameters"]["recorded_framerate"]

    # PRINT RESULTS in terminal
    if config["shown_outputs"]["print_time_ranges"]:
        printToOutput(f"\n")
        printToOutput(f"Total time range: [0, {len(df) - 2}]\n")
        printToOutput(f"Time ranges selected: [ ")
        if timeRanges:
            printToOutput(f"[{timeRanges[0][0]}, {timeRanges[0][1]}]")
            for i in range(1, len(timeRanges)):
                printToOutput(f", [{timeRanges[i][0]}, {timeRanges[i][1]}]")
            printToOutput(" ]\n")
        else:
            printToOutput(" ]\n")
            exit()

    if config["shown_outputs"]["print_travel_distance"]:
        printToOutput("\n")
        distances = printTotalDistance(headX, headY, timeRanges)
        for row in range(len(distances)):
            resultsList[row]["travelDistance(m/s)"] = distances[row]

    if config["shown_outputs"]["print_travel_velocity"]:
        printToOutput("\n")
        speeds = printTotalSpeed(
            headX, headY, timeRanges, config["video_parameters"]["recorded_framerate"])
        for row in range(len(speeds)):
            resultsList[row]["travelSpeed(m/s^2)"] = speeds[row]

    if config["shown_outputs"]["print_fin_freq"]:
        printToOutput("\n")
        freqValue = printLeftFinFreq(
            config["graph_cutoffs"]["left_fin_angle"], leftFinAngles, timeRanges, timeFactor)
        resultsList[0]["leftFinFreq(x/s)"] = freqValue
        printToOutput("\n")
        freqValue = printRightFinFreq(
            config["graph_cutoffs"]["right_fin_angle"], rightFinAngles, timeRanges, timeFactor)
        resultsList[0]["rightFinFreq(x/s)"] = freqValue

    if config["shown_outputs"]["print_tail_freq"]:
        printToOutput("\n")
        freqValues = printTailFreq(
            config["graph_cutoffs"]["tail_angle"], tailDistances, timeRanges, timeFactor)
        resultsList[0]["tailFinFreq(x/s)"] = freqValue

    # DISPLAY VISUAL RESULTS

    spineResultsRowPos = 0
    if config["shown_outputs"]["show_spines"]:
        selectByBout = config["spine_plot_settings"]["select_by_bout"]
        selectByParallel = config["spine_plot_settings"]["select_by_parallel_fins"]
        selectByPeaks = config["spine_plot_settings"]["select_by_peaks"]
        if selectByBout:
            config["spine_plot_settings"]["select_by_bout"] = True
            config["spine_plot_settings"]["select_by_parallel_fins"] = False
            config["spine_plot_settings"]["select_by_peaks"] = False
            spineOutputInfo = plotSpines(spine, leftFinAngles, rightFinAngles, timeRanges,
                                         config["spine_plot_settings"], config["graph_cutoffs"], config["open_plots"])
            resultsList[spineResultsRowPos]["spineFrameNum"] = "selectedByBout"
            resultsList[spineResultsRowPos]["gapsInSpine"] = ""
            resultsList[spineResultsRowPos]["missingEndPoints"] = ""
            spineResultsRowPos += 1
            for row in range(len(spineOutputInfo[0])):
                resultsList[spineResultsRowPos]["spineFrameNum"] = spineOutputInfo[0][row]
                resultsList[spineResultsRowPos]["gapsInSpine"] = spineOutputInfo[1][row]
                resultsList[spineResultsRowPos]["missingEndPoints"] = spineOutputInfo[2][row]
                spineResultsRowPos += 1
        if selectByParallel:
            config["spine_plot_settings"]["select_by_bout"] = False
            config["spine_plot_settings"]["select_by_parallel_fins"] = True
            config["spine_plot_settings"]["select_by_peaks"] = False
            spineOutputInfo = plotSpines(spine, leftFinAngles, rightFinAngles, timeRanges,
                                         config["spine_plot_settings"], config["graph_cutoffs"], config["open_plots"])
            resultsList[spineResultsRowPos]["spineFrameNum"] = "selectedByParallel"
            resultsList[spineResultsRowPos]["gapsInSpine"] = ""
            resultsList[spineResultsRowPos]["missingEndPoints"] = ""
            spineResultsRowPos += 1
            for row in range(len(spineOutputInfo[0])):
                resultsList[spineResultsRowPos]["spineFrameNum"] = spineOutputInfo[0][row]
                resultsList[spineResultsRowPos]["gapsInSpine"] = spineOutputInfo[1][row]
                resultsList[spineResultsRowPos]["missingEndPoints"] = spineOutputInfo[2][row]
                spineResultsRowPos += 1
        if selectByPeaks:
            config["spine_plot_settings"]["select_by_bout"] = False
            config["spine_plot_settings"]["select_by_parallel_fins"] = False
            config["spine_plot_settings"]["select_by_peaks"] = True
            spineOutputInfo = plotSpines(spine, leftFinAngles, rightFinAngles, timeRanges,
                                         config["spine_plot_settings"], config["graph_cutoffs"], config["open_plots"])
            resultsList[spineResultsRowPos]["spineFrameNum"] = "selectedByPeaks"
            resultsList[spineResultsRowPos]["gapsInSpine"] = ""
            resultsList[spineResultsRowPos]["missingEndPoints"] = ""
            spineResultsRowPos += 1
            for row in range(len(spineOutputInfo[0])):
                resultsList[spineResultsRowPos]["spineFrameNum"] = spineOutputInfo[0][row]
                resultsList[spineResultsRowPos]["gapsInSpine"] = spineOutputInfo[1][row]
                resultsList[spineResultsRowPos]["missingEndPoints"] = spineOutputInfo[2][row]
                spineResultsRowPos += 1

    if config["shown_outputs"]["show_angle_and_distance_plot"]:
        plotFinAndTailCombined(leftFinAngles, rightFinAngles, tailDistances, headYaw,
                               timeRanges, config["angle_and_distance_plot_settings"], config["open_plots"])

    if config["shown_outputs"]["show_movement_track"]:
        plotMovement(headPixelsX, headPixelsY, timeRanges,
                     config["file_inputs"]["video"], config["video_parameters"]["pixel_scale_factor"], config["open_plots"])

    if config["shown_outputs"]["show_heatmap"]:
        plotMovementHeatmap(headPixelsX, headPixelsY, tailPixelsX, tailPixelsY, timeRanges,
                            config["file_inputs"]["video"], config["open_plots"], config["open_plots"])

    if config["shown_outputs"]["show_head_plot"]:
        plotHead(headYaw, leftFinAngles, rightFinAngles, timeRanges,
                 config["head_plot_settings"], config["graph_cutoffs"], config["open_plots"])

    saveResultstoExcelFile(resultsList)

# confidence filtering


def checkConfidence(spine, row, spineAcceptedConfidence, spineAcceptedBrokenPoints):
    brokenPoints = 0
    for spinePoint in range(len(spine)):
        if (spine[spinePoint][row]['conf'] < spineAcceptedConfidence):
            brokenPoints += 1
    if (brokenPoints > spineAcceptedBrokenPoints):
        return False
    return True

# fin & tail movement occurence


def getFrequencyAndPeakNum(cutoff, values, timeRanges, timeFactor):
    peakDistances = []
    onPeak = False

    for startIndex, endIndex in timeRanges:
        peaks = []
        for i in range(startIndex, endIndex + 1):
            if (not onPeak and values[i] > cutoff):  # If on new peak
                onPeak = True
            elif (onPeak and values[i] <= cutoff):  # If current  peak ends
                peaks.append(i)
                onPeak = False

        if (len(peaks) > 1):
            for i in range(0, len(peaks) - 1):
                # ***Still need to adjust for time***
                peakDistances.append(peaks[i + 1] - peaks[i])
    if len(peakDistances) > 0:
        freq = sum(peakDistances) / len(peakDistances) / timeFactor
    else:
        freq = 0
    return freq, len(peaks)


def rotateAroundOrigin(x, y, originX, originY, headAngle, inRads=True):
    if inRads:
        angle_rad = np.pi / 2 - headAngle + np.pi
    else:
        angle_rad = np.deg2rad(headAngle)

    # Translate
    x_shifted = x - originX
    y_shifted = y - originY

    # Rotate
    x_rotated = x_shifted * np.cos(angle_rad) - y_shifted * np.sin(angle_rad)
    y_rotated = x_shifted * np.sin(angle_rad) + y_shifted * np.cos(angle_rad)

    # Translate back
    x_new = x_rotated + originX
    y_new = y_rotated + originY

    return x_new, y_new


def flipAcrossOriginX(x, originX):
    x_new = originX + (originX - x)

    return x_new


def getPeaks(values, cutoff, totalRange, negativeCutoff=False):
    peaks = []
    onPeak = False

    currentPeakPos = 0
    currentPeakMax = 0

    if negativeCutoff:
        for i in range(0, totalRange):
            if (not onPeak and values[i] < cutoff):  # If on new peak
                currentPeakPos = i
                currentPeakMax = values[i]
                onPeak = True
            elif (onPeak and values[i] >= cutoff):  # If current  peak ends
                peaks.append(currentPeakPos)
                onPeak = False
            elif (onPeak):  # If still in peak and peak already exists
                newMax = min(currentPeakMax, values[i])
                if (newMax < currentPeakMax):
                    currentPeakMax = newMax
                    currentPeakPos = i
    else:
        for i in range(0, totalRange):
            if (not onPeak and values[i] > cutoff):  # If on new peak
                currentPeakPos = i
                currentPeakMax = values[i]
                onPeak = True
            elif (onPeak and values[i] <= cutoff):  # If current  peak ends
                peaks.append(currentPeakPos)
                onPeak = False
            elif (onPeak):  # If still in peak and peak already exists
                newMax = max(currentPeakMax, values[i])
                if (newMax > currentPeakMax):
                    currentPeakMax = newMax
                    currentPeakPos = i
    if onPeak:
        peaks.append(i)

    return peaks


def getTimeRanges(leftFinAngles, rightFinAngles, tailDistances, lfCutoff, rfCutoff, tailCutoff, movBoutCutoff, totalRange, swimBoutBuffer, swimBoutRightShift, useTailAngle):
    onRange = False
    timeRanges = []
    newRangeStart = 0

    tailPosPeaks = getPeaks(tailDistances,  tailCutoff, totalRange)
    tailNegPeaks = getPeaks(tailDistances,  tailCutoff, -
                            totalRange, negativeCutoff=True)

    lfPeaks = getPeaks(leftFinAngles,  lfCutoff,   totalRange)
    rfPeaks = getPeaks(rightFinAngles, rfCutoff,   totalRange)
    tailAllPeaks = sorted(tailPosPeaks + tailNegPeaks)

    lastLfPeak = lastRfPeak = lastTailPeak = -movBoutCutoff * 2

    if useTailAngle:
        for i in range(0, totalRange):
            # Add peaks that match current position
            if i in lfPeaks:
                lastLfPeak = i
            if i in rfPeaks:
                lastRfPeak = i
            if i in tailAllPeaks:
                lastTailPeak = i
            # If not on a range already, and both fins and tail have peaks within movBoutCutoff, then start new range
            # and i - lastTailPeak <= movBoutCutoff:
            if not onRange and (i - lastLfPeak <= movBoutCutoff and i - lastRfPeak <= movBoutCutoff and i - lastTailPeak <= movBoutCutoff):
                # Find the earliest peak and start one point before, but not before 0
                newRangeStart = max(min(min(
                    lastLfPeak, lastRfPeak), lastTailPeak) - swimBoutBuffer + swimBoutRightShift, 0)
                onRange = True
            # If already on range, and fins and tail are not within movBoutCutoff, then end range.
            # or i - lastTailPeak > movBoutCutoff):
            elif onRange and (i - lastLfPeak > movBoutCutoff or i - lastRfPeak > movBoutCutoff or i - lastTailPeak > movBoutCutoff):
                # Find the last peak and start one point after, but not after the total range
                newRangeEnd = min(max(max(lastLfPeak, lastRfPeak), lastTailPeak) +
                                  swimBoutBuffer + swimBoutRightShift, totalRange)
                timeRanges.append([newRangeStart, newRangeEnd])
                onRange = False
    else:
        for i in range(0, totalRange):
            # Add peaks that match current position
            if i in lfPeaks:
                lastLfPeak = i
            if i in rfPeaks:
                lastRfPeak = i
            if i in tailAllPeaks:
                lastTailPeak = i
            # If not on a range already, and either fins or tail have peaked within movBoutCutoff, then start new range
            # and i - lastTailPeak <= movBoutCutoff:
            if not onRange and (i - lastLfPeak <= movBoutCutoff and i - lastRfPeak <= movBoutCutoff):
                # Find the earliest peak and start one point before, but not before 0
                newRangeStart = max(
                    min(lastLfPeak, lastRfPeak) - swimBoutBuffer + swimBoutRightShift, 0)
                onRange = True
            # If already on range, and fins and tail are not within movBoutCutoff, then end range.
            # or i - lastTailPeak > movBoutCutoff):
            elif onRange and (i - lastLfPeak > movBoutCutoff or i - lastRfPeak > movBoutCutoff):
                # Find the last peak and start one point after, but not after the total range
                newRangeEnd = min(max(lastLfPeak, lastRfPeak) +
                                  swimBoutBuffer + swimBoutRightShift, totalRange - 1)
                timeRanges.append([newRangeStart, newRangeEnd])
                onRange = False
    if onRange:
        newRangeEnd = min(max(lastLfPeak, lastRfPeak) +
                          swimBoutBuffer + swimBoutRightShift, totalRange - 1)
        timeRanges.append([newRangeStart, newRangeEnd])

    if len(timeRanges) <= 1:
        return timeRanges

    # Combine overlapping time ranges
    mergedTimeRanges = []
    lastStart = timeRanges[0][0]
    lastEnd = timeRanges[0][1]
    for i in range(len(timeRanges)):
        # If current range overlaps with last, then combine them
        if (timeRanges[i][0] <= lastEnd):
            lastEnd = timeRanges[i][1]
        # If current range is separate than last range, then add last range
        else:
            mergedTimeRanges.append([lastStart, lastEnd])
            lastStart = timeRanges[i][0]
            lastEnd = timeRanges[i][1]
        # If current range is last range in set, then add found range
        if i == len(timeRanges) - 1:
            mergedTimeRanges.append([lastStart, lastEnd])
    return mergedTimeRanges


def plotAddLine(currentPlot, values, color, timeRanges):
    for startIndex, endIndex in timeRanges:
        for row in range(startIndex, endIndex):
            timePos = [row, row + 1]

            graphLine = values[row:row + 2]

            currentPlot.plot(timePos, graphLine, color=color, linewidth=1.5)


def addPlotLabels(currentPlot, cursorLineTextBoxes, cursorLineTextLabels, timeRanges, currentGraphMin, totalPlots, currentPlotNum, plotName):
    cursorLineTextBoxPos = timeRanges[0][0] + (timeRanges[len(
        timeRanges)-1][1] - timeRanges[0][0]) * (currentPlotNum / float(totalPlots))
    cursorLineTextBoxes.append(currentPlot.text(
        cursorLineTextBoxPos, currentGraphMin, '', va='bottom', ha='left', backgroundcolor='w'))
    cursorLineTextLabels.append(plotName)


""" PRINTING DATA """


def printLeftFinFreq(cutoff, finAngles, timeRanges, timeFactor):
    freq, peakNum = getFrequencyAndPeakNum(
        cutoff, finAngles, timeRanges, timeFactor)
    printToOutput(
        f"The left fin beats had a frequency of {freq:.5f}/s with {peakNum} peaks.\n")
    return freq


def printRightFinFreq(cutoff, finAngles, timeRanges, timeFactor):
    freq, peakNum = getFrequencyAndPeakNum(
        cutoff, finAngles, timeRanges, timeFactor)
    printToOutput(
        f"The right fin beats had a frequency of {freq:.5f}/s with {peakNum} peaks.\n")
    return freq


def printTailFreq(cutoff, tailAngles, timeRanges, timeFactor):
    freq, peakNum = getFrequencyAndPeakNum(
        cutoff, tailAngles, timeRanges, timeFactor)
    printToOutput(
        f"The tail beats had a frequency of {freq:.5f}/s with {peakNum} peaks.\n")
    return freq


def printTotalDistance(headX, headY, timeRanges):
    distances = []
    for startIndex, endIndex in timeRanges:
        distX = headX[endIndex] - headX[startIndex]
        distY = headY[endIndex] - headY[startIndex]
        finalDist = np.sqrt(distX ** 2 + distY ** 2)
        printToOutput(
            f"The final distance traveled in range {startIndex}-{endIndex} is {finalDist:.7f} m\n")
        distances.append(finalDist)
    return distances


def printTotalSpeed(headX, headY, timeRanges, framerate):
    speeds = []
    for startIndex, endIndex in timeRanges:
        distX = headX[endIndex] - headX[startIndex]
        distY = headY[endIndex] - headY[startIndex]
        finalDist = np.sqrt(distX ** 2 + distY ** 2)
        printToOutput(
            f"The average velocity in range {startIndex}-{endIndex} is {finalDist / framerate:.7f} m/s\n")
        speeds.append(finalDist / framerate)
    return speeds


""" PLOTTING DATA """


def plotSpines(spine, leftFinValues, rightFinValues, timeRanges, spineSettings, cutoffs, openPlots):
    leftFinCutoff = cutoffs["left_fin_angle"]
    rightFinCutoff = cutoffs["right_fin_angle"]

    spineAcceptedConfidence = spineSettings["min_accepted_confidence"]
    spineAcceptedBrokenPoints = spineSettings["accepted_broken_points"]
    spineRemoveConfidence = spineSettings["min_confidence_replace_from_surrounding_points"]
    gradientSpine = spineSettings["draw_with_gradient"]
    drawOffset = spineSettings["plot_draw_offset"]

    spinesPerBout = spineSettings["spines_per_bout"]
    splitByBout = spineSettings["split_plots_by_bout"]

    errorRange = spineSettings["parallel_error_range"]

    removeSyncedPeaks = spineSettings["ignore_synchronized_fin_peaks"]
    syncTimeRange = spineSettings["sync_fin_peaks_range"]

    useRightSideFinpeaks = spineSettings["fin_peaks_for_right_fin"]

    selectByBout = spineSettings["select_by_bout"]
    selectByParallel = spineSettings["select_by_parallel_fins"]
    selectByPeaks = spineSettings["select_by_peaks"]

    # Spine frame num, gaps in spine, missing end points
    spineOutputInfo = [[], [], []]

    if (selectByBout + selectByParallel + selectByPeaks) > 1:
        printToOutput(
            'Please only select one as true from: "spines_by_bout", "spine_by_parallel_fins", and "spine_by_peaks"')
        return spineOutputInfo
    elif (selectByBout + selectByParallel + selectByPeaks) == 0:
        printToOutput(
            'Please deselect "show_spines", or select one as true from: "spines_by_bout", "spine_by_parallel_fins", and "spine_by_peaks.')
        return spineOutputInfo

    spineRowsByBout = []

    if selectByBout:
        plotNum = 0
        for startIndex, endIndex in timeRanges:
            currentSpineRows = []
            brokenSpines = 0
            for i in range(spinesPerBout):
                newSpineRowValue = int(
                    startIndex + (endIndex - startIndex) * (i / float(spinesPerBout - 1)))
                if checkConfidence(spine, newSpineRowValue, spineAcceptedConfidence, spineAcceptedBrokenPoints):
                    currentSpineRows.append(newSpineRowValue)
                else:
                    brokenSpines += 1
            if brokenSpines > 0:
                printToOutput(
                    f"Warning: {brokenSpines} spines removed due to low confidence in spine_plot_{plotNum}")
            spineRowsByBout.append(currentSpineRows)
        imageTag = "byBout"

    if selectByPeaks:
        if useRightSideFinpeaks:
            finValues = rightFinValues
            cutoff = rightFinCutoff
            opposingFinValues = leftFinValues
            opposingCutoff = leftFinCutoff
        else:
            finValues = leftFinValues
            cutoff = leftFinCutoff
            opposingFinValues = rightFinValues
            opposingCutoff = rightFinCutoff
        for startIndex, endIndex in timeRanges:
            currentSpineRows = []
            onPeak = False
            for i in range(startIndex, endIndex + 1):
                if (not onPeak and finValues[i] > cutoff):  # If on new peak
                    currentMaxVal = finValues[i]
                    currentMaxIndex = i
                    onPeak = True
                elif (onPeak and finValues[i] > cutoff):  # If already on peak
                    if finValues[i] > currentMaxVal:
                        currentMaxVal = finValues[i]
                        currentMaxIndex = i
                # If current  peak ends and confidence is right
                elif (onPeak and finValues[i] <= cutoff and checkConfidence(spine, currentMaxIndex, spineAcceptedConfidence, spineAcceptedBrokenPoints)):
                    validPoint = True
                    if removeSyncedPeaks:
                        for i in range(max(0, currentMaxIndex - syncTimeRange), min(currentMaxIndex + syncTimeRange, endIndex)):
                            if opposingFinValues[i] > opposingCutoff:
                                validPoint = False
                    if validPoint:
                        currentSpineRows.append(currentMaxIndex)
                    onPeak = False
            spineRowsByBout.append(currentSpineRows)
        imageTag = "byFinPeaks"

    if selectByParallel:
        onPeak = False
        for startIndex, endIndex in timeRanges:
            currentSpineRows = []
            for i in range(startIndex, endIndex + 1):
                leftDist = abs(leftFinValues[i] - 90)
                rightDist = abs(rightFinValues[i] - 90)

                if (leftDist < errorRange and rightDist < errorRange) and checkConfidence(spine, i, spineAcceptedConfidence, spineAcceptedBrokenPoints):
                    if onPeak:
                        if (leftDist + rightDist < currentClosestDist):
                            currentClosestDist = leftDist + rightDist
                            currentClosestIndex = i
                        else:
                            onPeak = False
                            currentSpineRows.append(currentClosestIndex)
                    else:
                        currentClosestDist = leftDist + rightDist
                        currentClosestIndex = i
                        onPeak = True
            spineRowsByBout.append(currentSpineRows)
        imageTag = "byParallelFins"

    currentBout = 0
    if splitByBout:
        figures = []
        labels = []

        for spineRows in spineRowsByBout:
            fig = go.Figure()
            currentOffset = 0
            currentSpineNum = 0

            spinesWithGaps = []
            spinesWithMissingEndpoints = []

            plotColors = [(1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
                          (0., 1., 1.), (0., 0., 1.), (1., 0., 1.)]

            printToOutput("Spine frames: [")
            if len(spineRows):
                printToOutput(f"{spineRows[0]}")
            for i in range(1, len(spineRows)):
                printToOutput(f", {spineRows[i]}")
            printToOutput("]\n")

            for row in spineRows:
                currentSpineNum += 1
                x = []
                y = []

                baseColorPos = float(currentSpineNum) / \
                    len(spineRows) * len(plotColors)
                color1 = plotColors[int(baseColorPos) % len(plotColors)]
                color2 = plotColors[(int(baseColorPos) + 1) % len(plotColors)]
                colorBetweenPercent = baseColorPos - int(baseColorPos)
                finalColor = (color1[0] * colorBetweenPercent + color2[0] * (1. - colorBetweenPercent),
                              color1[1] * colorBetweenPercent +
                              color2[1] * (1. - colorBetweenPercent),
                              color1[2] * colorBetweenPercent + color2[2] * (1. - colorBetweenPercent))

                dx = spine[2][row]['x'] - spine[0][row]['x']
                dy = spine[2][row]['y'] - spine[0][row]['y']
                headAngle = np.arctan2(dy, dx)

                gapSize = 0
                maxGap = 0
                lastX = spine[0][row]["x"]
                lastY = spine[0][row]["y"]

                for spinePointType in range(len(spine)):
                    if spine[spinePointType][row]["conf"] >= spineRemoveConfidence:
                        # X point, centered by origin, with offset
                        nextX = spine[spinePointType][row]["x"] - \
                            spine[0][row]['x'] + currentOffset
                        nextY = spine[spinePointType][row]["y"] - \
                            spine[0][row]['y']
                        nextX, nextY = rotateAroundOrigin(
                            nextX, nextY, currentOffset, 0, headAngle)
                        nextX = flipAcrossOriginX(nextX, currentOffset)
                        if gapSize != 0:
                            for i in range(gapSize):
                                inbetweenX = lastX + \
                                    (nextX - lastX) * ((i + 1) / (gapSize + 1))
                                inbetweenY = lastY + \
                                    (nextY - lastY) * ((i + 1) / (gapSize + 1))
                                x.append(inbetweenX)
                                y.append(inbetweenY)
                        x.append(nextX)
                        y.append(nextY)
                        lastX = nextX
                        lastY = nextY
                        gapSize = 0
                    else:
                        gapSize += 1
                        maxGap = max(gapSize, maxGap)

                spineOutputInfo[0].append(row)
                spineOutputInfo[1].append(maxGap)
                spineOutputInfo[2].append(gapSize)

                if (maxGap > 1):
                    spinesWithGaps.append(currentSpineNum)
                if (gapSize > 1):
                    spinesWithMissingEndpoints.append(currentSpineNum)

                if gradientSpine:
                    for i in range(0, len(x)):
                        currentLineColor = (finalColor[0] * (0.5 + (i + 1) / len(x) / 2), finalColor[1] * (
                            0.5 + (i + 1) / len(x) / 2), finalColor[2] * (0.5 + (i + 1) / len(x) / 2))
                        lineColorStr = f"rgb{tuple(currentLineColor)}"
                        fig.add_trace(go.Scatter(
                            x=x[i:i+2], y=y[i:i+2], mode='lines', line=dict(color=lineColorStr, shape='spline')))
                else:
                    for i in range(0, len(x)):
                        currentLineColor = plotColors[i % len(plotColors)]
                        lineColorStr = f"rgb{tuple(currentLineColor)}"
                        fig.add_trace(go.Scatter(
                            x=x[i:i+2], y=y[i:i+2], mode='lines', line=dict(color=lineColorStr, shape='spline')))

                currentOffset += drawOffset

            if len(spinesWithGaps) > 0:
                printToOutput("Spines with gaps more than two: ")
                for num in spinesWithGaps:
                    printToOutput(f"{num} ")
            printToOutput("\n")
            if len(spinesWithMissingEndpoints) > 0:
                printToOutput("Spines with missing endpoints: ")
                for num in spinesWithMissingEndpoints:
                    printToOutput(f"{num} ")
            printToOutput("\n")

            if currentSpineNum > 0:
                fig.update_layout(title='Spine Plot')
                figures.append(fig)
                startIndex = timeRanges[currentBout][0]
                endIndex = timeRanges[currentBout][1]
                labels.append(f"spine_plot_range_[{startIndex},_{endIndex}]")
                fig.write_image(os.path.join(
                    outputsDict['outputFolder'], f"{imageTag}Spines[{startIndex},{endIndex}].png"))
            currentBout += 1

        tabs_html = """
        <html>
        <head>
        <style>
        body {
            font-family: sans-serif;
            background-color: #f9f9f9;
        }
        #tabs {
            margin-bottom: 10px;
        }
        .tab-button {
            padding: 10px 16px;
            cursor: pointer;
            display: inline-block;
            background-color: #eee;
            border: 1px solid #ccc;
            border-bottom: none;
            margin-right: 5px;
            border-radius: 6px 6px 0 0;
            font-weight: bold;
        }
        .tab-button.active {
            background-color: #fff;
            border-bottom: 1px solid #fff;
        }
        .tab {
            display: none;
        }
        .tab.active {
            display: block;
        }
        </style>
        </head>
        <body>
        <div id="tabs">
        """

        # Create the tab buttons
        for i, label in enumerate(labels):
            active_class = "active" if i == 0 else ""
            tabs_html += f'<div class="tab-button {active_class}" onclick="showTab({i})">{label}</div>'

        tabs_html += '</div>'

        # Create the tab content divs
        for i, fig in enumerate(figures):
            fig_html = fig.to_html(include_plotlyjs=(i == 0), full_html=False)
            active_style = "active" if i == 0 else ""
            tabs_html += f'<div class="tab {active_style}">{fig_html}</div>'

        # Add script for tab functionality
        tabs_html += """
        <script>
        function showTab(index) {
            const tabs = document.getElementsByClassName('tab');
            const buttons = document.getElementsByClassName('tab-button');
            for (let i = 0; i < tabs.length; i++) {
                tabs[i].classList.remove('active');
                buttons[i].classList.remove('active');
            }
            tabs[index].classList.add('active');
            buttons[index].classList.add('active');
        }
        </script>
        </body>
        </html>
        """

        # Write to file
        outputHtmlPath = os.path.join(
            outputsDict['outputFolder'], "spine_plots_tabbed.html")
        with open(outputHtmlPath, 'w', encoding='utf-8') as f:
            f.write(tabs_html)
        if openPlots:
            webbrowser.open(outputHtmlPath)
    else:
        fig = go.Figure()

        currentOffset = 0

        currentSpineNum = 0
        spinesWithGaps = []
        spinesWithMissingEndpoints = []

        plotColors = [(1., 0., 0.), (1., 1., 0.), (0., 1., 0.),
                      (0., 1., 1.), (0., 0., 1.), (1., 0., 1.)]

        # Print row nums
        printToOutput("Spine frames: [")
        printToOutput(f"{spineRowsByBout[0][0]}")
        for rowNum in range(1, len(spineRowsByBout[0])):
            printToOutput(f", {spineRowsByBout[0][rowNum]}")
        for boutNum in range(1, len(spineRowsByBout)):
            for row in spineRowsByBout[boutNum]:
                printToOutput(f", {row}")
        printToOutput("]\n")

        for spineRows in spineRowsByBout:
            for row in spineRows:
                currentSpineNum += 1
                x = []
                y = []

                baseColorPos = float(currentSpineNum) / sum(len(spineRows)
                                                            for spineRows in spineRowsByBout) * len(plotColors)
                color1 = plotColors[int(baseColorPos) % len(plotColors)]
                color2 = plotColors[(int(baseColorPos) + 1) % len(plotColors)]
                colorBetweenPercent = baseColorPos - int(baseColorPos)
                finalColor = (color1[0] * colorBetweenPercent + color2[0] * (1. - colorBetweenPercent),
                              color1[1] * colorBetweenPercent +
                              color2[1] * (1. - colorBetweenPercent),
                              color1[2] * colorBetweenPercent + color2[2] * (1. - colorBetweenPercent))

                dx = spine[2][row]['x'] - spine[0][row]['x']
                dy = spine[2][row]['y'] - spine[0][row]['y']
                headAngle = np.arctan2(dy, dx)

                gapSize = 0
                maxGap = 0
                lastX = spine[0][row]["x"]
                lastY = spine[0][row]["y"]

                for spinePointType in range(len(spine)):
                    if spine[spinePointType][row]["conf"] >= spineRemoveConfidence:
                        # X point, centered by origin, with offset
                        nextX = spine[spinePointType][row]["x"] - \
                            spine[0][row]['x'] + currentOffset
                        nextY = spine[spinePointType][row]["y"] - \
                            spine[0][row]['y']
                        nextX, nextY = rotateAroundOrigin(
                            nextX, nextY, currentOffset, 0, headAngle)
                        nextX = flipAcrossOriginX(nextX, currentOffset)
                        if gapSize != 0:
                            for i in range(gapSize):
                                inbetweenX = lastX + \
                                    (nextX - lastX) * ((i + 1) / (gapSize + 1))
                                inbetweenY = lastY + \
                                    (nextY - lastY) * ((i + 1) / (gapSize + 1))
                                x.append(inbetweenX)
                                y.append(inbetweenY)
                        x.append(nextX)
                        y.append(nextY)
                        lastX = nextX
                        lastY = nextY
                        gapSize = 0
                    else:
                        gapSize += 1
                        maxGap = max(gapSize, maxGap)

                spineOutputInfo[0].append(row)
                spineOutputInfo[1].append(maxGap)
                spineOutputInfo[2].append(gapSize)
                if (maxGap > 1):
                    spinesWithGaps.append(currentSpineNum)
                if (gapSize > 1):
                    spinesWithMissingEndpoints.append(currentSpineNum)

                if gradientSpine:
                    for i in range(0, len(x)):
                        currentLineColor = (finalColor[0] * (0.5 + (i + 1) / len(x) / 2), finalColor[1] * (
                            0.5 + (i + 1) / len(x) / 2), finalColor[2] * (0.5 + (i + 1) / len(x) / 2))
                        lineColorStr = f"rgb{tuple(currentLineColor)}"
                        fig.add_trace(go.Scatter(
                            x=x[i:i+2], y=y[i:i+2], mode='lines', line=dict(color=lineColorStr, shape='spline')))
                else:
                    for i in range(0, len(x)):
                        currentLineColor = i % len(plotColors)
                        # lineColorStr = f"rgb{tuple(currentLineColor)}"
                        fig.add_trace(go.Scatter(
                            x=x[i:i+2], y=y[i:i+2], mode='lines', line=dict(color=currentLineColor, shape='spline')))
                currentOffset += drawOffset

        if len(spinesWithGaps) > 0:
            printToOutput("Spines with gaps more than two: ")
            for num in spinesWithGaps:
                printToOutput(f"{num} ")
        printToOutput("\n")
        if len(spinesWithMissingEndpoints) > 0:
            printToOutput("Spines with missing endpoints: ")
            for num in spinesWithMissingEndpoints:
                printToOutput(f"{num} ")
        printToOutput("\n")

        fig.update_layout(title='Spine Plot')
        output_path = f"{outputsDict['outputFolder']}/spine_plot_plotly.html"
        fig.write_html(output_path)
        fig.write_image(os.path.join(
            outputsDict['outputFolder'], f"{imageTag}Spines.png"))
        if openPlots:
            pio.show(fig)

    return spineOutputInfo


def plotMovement(headPixelsX, headPixelsY, timeRanges, videoFile, scaleFactor, openPlots):

    frameNum = timeRanges[0][1]

    video = cv2.VideoCapture(videoFile)
    video.set(cv2.CAP_PROP_POS_FRAMES, frameNum)
    success, frame = video.read()
    video.release()

    frameHeight, frameWidth = frame.shape[:2]

    if not success:
        print("Failed to read frame.")
        return

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    x = []
    y = []

    # Scale of csv doesn't seem to align with video.
    # I lined up the scale roughly by adjusting the scale factor

    for row in range(timeRanges[0][0], timeRanges[0][1]):
        x.append(headPixelsX[row] * scaleFactor)
        y.append(headPixelsY[row] * scaleFactor)

    fig = go.Figure()

    fig.add_layout_image(
        source=frame_rgb,
        xref="x",
        yref="y",
        x=0,
        y=frame_rgb.shape[0],
        sizex=frame_rgb.shape[0],
        sizey=frame_rgb.shape[1],
        sizing="stretch",
        layer="below"
    )

    fig.add_trace(
        go.Scatter(
            x=x,
            y=[frame_rgb.shape[0] - val for val in y],
            mode='lines',
            line=dict(color='red', shape='spline'),
            name='Movement Path'
        )
    )

    fig.update_layout(
        title="Zebrafish Movement",
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=False, zeroline=False,
                   scaleanchor="x", scaleratio=1),
        margin=dict(l=0, r=0, t=30, b=0)
    )

    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)

    output_path = os.path.join(
        outputsDict["outputFolder"], "Zebrafish_Movement_Plotly.html")
    fig.write_html(output_path)

    png_path = os.path.join(
        outputsDict["outputFolder"], "Zebrafish_Movement_Plotly.png")
    pio.write_image(fig, png_path, format='png', scale=3)
    if openPlots:
        pio.show(fig)


def plotMovementHeatmap(headPixelsX, headPixelsY, tailPixelsX, tailPixelsY, timeRanges, videoFile, openPlots):
    # Figure out max tail distance and crop
    bufferMult = 1.1
    maxHeadTailDist = 0
    for startIndex, endIndex in timeRanges:
        for i in range(startIndex, endIndex + 1):
            currentMaxDist = max(
                abs(headPixelsX[i] - tailPixelsX[i]), abs(headPixelsY[i] - tailPixelsY[i]))
            maxHeadTailDist = max(currentMaxDist, maxHeadTailDist)

    # Load video
    cropSize = int(maxHeadTailDist * 2 * bufferMult)
    video = cv2.VideoCapture(videoFile)
    frames = []
    for startIndex, endIndex in timeRanges:
        video.set(cv2.CAP_PROP_POS_FRAMES, startIndex)
        for i in range(startIndex, endIndex + 1):
            success, frame = video.read()
            if not success:
                break
            frames.append(frame)
    video.release()

    height = cropSize * 2
    width = cropSize * 2
    heatmap = np.zeros((height, width), dtype=np.float32)

    frameNum = 0
    for startIndex, endIndex in timeRanges:
        for i in range(startIndex, endIndex + 1):
            # Get head coordinates for this frame
            x_center = int(headPixelsX[i] * 1.825)
            y_center = int(headPixelsY[i] * 1.825)

            # Seek to frame and extract it
            print(frameNum)
            frame = frames[frameNum]
            frameNum += 1

            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Crop around head
            y1 = max(y_center - cropSize, 0)
            y2 = min(y_center + cropSize, gray.shape[0])
            x1 = max(x_center - cropSize, 0)
            x2 = min(x_center + cropSize, gray.shape[1])

            cropped = gray[y1:y2, x1:x2]

            # Resize cropped area to fit the heatmap shape if it goes out of bounds
            h, w = cropped.shape
            heatmap[:h, :w] += cropped.astype(np.float32)

    # Normalize heatmap
    heatmap /= np.max(heatmap)
    gamma = 0.5
    heatmap = np.power(heatmap, gamma)

    # Show heatmap
    fig = px.imshow(heatmap, color_continuous_scale='ice', origin='upper')
    fig.update_layout(title="Zebrafish Movement Heatmap",
                      coloraxis_colorbar=dict(title="Intensity"))

    output_path = os.path.join(
        outputsDict["outputFolder"], "heatmap_plotly.html")
    fig.write_html(output_path)

    png_path = os.path.join(outputsDict["outputFolder"], "Heatmap_Plotly.png")
    pio.write_image(fig, png_path, format='png', scale=3)
    if openPlots:
        pio.show(fig)


def plotFinAndTailCombined(leftFinAngles, rightFinAngles, distances, headYaw, timeRanges, settings, openPlots):
    def prepare_series(data):
        x, y = [], []
        for startIndex, endIndex in timeRanges:
            x.extend(range(startIndex, endIndex))
            y.extend([data[i] for i in range(startIndex, endIndex)])
            x.append(None)
            y.append(None)
        return x, y

    # Create subplot figure
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=("Fin Angles and Head Yaw", "Tail Distance"),
        specs=[[{}], [{"secondary_y": True}]],
        row_heights=[0.5, 0.5]
    )

    if settings["show_left_fin_angle"]:
        x, y = prepare_series(leftFinAngles)
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Left Fin Angle', line=dict(
            color='blue', shape='spline')), row=1, col=1)

    if settings["show_right_fin_angle"]:
        x, y = prepare_series(rightFinAngles)
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Right Fin Angle', line=dict(
            color='red', shape='spline')), row=1, col=1)

    if settings["show_tail_distance"]:
        x, y = prepare_series(distances)
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Tail Distance', line=dict(
            color='green', shape='spline')), row=2, col=1, secondary_y=False)

    if settings["show_head_yaw"]:
        x, y = prepare_series(headYaw)
        fig.add_trace(go.Scatter(x=x, y=y, mode='lines', name='Head Yaw', line=dict(
            color='black', shape='spline')), row=2, col=1, secondary_y=True)

    fig.update_layout(
        height=700,
        width=1000,
        title_text="Set Figures Over Time",
        showlegend=True
    )

    fig.update_xaxes(title_text="Frame", row=2, col=1)
    fig.update_yaxes(title_text="Fin Angles (deg)", row=1, col=1)
    fig.update_yaxes(title_text="Tail Distance (m)",
                     row=2, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Head Yaw (deg)",
                     row=2, col=1, secondary_y=True)

    html_path = os.path.join(
        outputsDict["outputFolder"], "FinAndTailCombined_Subplots.html")
    png_path = os.path.join(
        outputsDict["outputFolder"], "FinAndTailCombined_Subplots.png")

    fig.write_html(html_path)
    pio.write_image(fig, png_path, format='png', scale=3)
    if openPlots:
        pio.show(fig)


def plotHead(headYaw, leftFinValues, rightFinValues, timeRanges, headSettings, cutoffs, openPlots):
    leftFinCutoff = cutoffs["left_fin_angle"]
    rightFinCutoff = cutoffs["right_fin_angle"]

    drawOffset = headSettings["plot_draw_offset"]

    removeSyncedPeaks = headSettings["ignore_synchronized_fin_peaks"]
    syncTimeRange = headSettings["sync_fin_peaks_range"]

    useRightSideFinpeaks = headSettings["fin_peaks_for_right_fin"]
    splitByBout = headSettings["split_plots_by_bout"]

    headRowsByBout = []

    # Get head points at fin peaks
    if useRightSideFinpeaks:
        finValues = rightFinValues
        cutoff = rightFinCutoff
        opposingFinValues = leftFinValues
        opposingCutoff = leftFinCutoff
    else:
        finValues = leftFinValues
        cutoff = leftFinCutoff
        opposingFinValues = rightFinValues
        opposingCutoff = rightFinCutoff
    for startIndex, endIndex in timeRanges:
        currentHeadRows = []
        currentHeadRows.append(startIndex)
        onPeak = False
        for i in range(startIndex, endIndex + 1):
            if (not onPeak and finValues[i] > cutoff):  # If on new peak
                currentMaxVal = finValues[i]
                currentMaxIndex = i
                onPeak = True
            elif (onPeak and finValues[i] > cutoff):  # If already on peak
                if finValues[i] > currentMaxVal:
                    currentMaxVal = finValues[i]
                    currentMaxIndex = i
            elif (onPeak and finValues[i] <= cutoff):
                validPoint = True
                if removeSyncedPeaks:
                    for i in range(max(0, currentMaxIndex - syncTimeRange), min(currentMaxIndex + syncTimeRange, endIndex)):
                        if opposingFinValues[i] > opposingCutoff:
                            validPoint = False
                if validPoint:
                    currentHeadRows.append(currentMaxIndex)
                onPeak = False
        headRowsByBout.append(currentHeadRows)

    headXPoints = [-0.5, 0, 0.5, 0, 0, 0]
    headYPoints = [-1, 0, -1, 0, -5, -10]

    currentBout = 0
    print()
    if splitByBout:
        figures = []
        labels = []

        for headRows in headRowsByBout:
            fig = go.Figure()
            currentOffset = 0
            printToOutput("Head frames: [")
            if len(headRows):
                printToOutput(f"{headRows[0]}")
            for i in range(1, len(headRows)):
                printToOutput(f", {headRows[i]}")
            printToOutput("]\n")

            currentHeadNum = 0

            for row in headRows:
                currentHeadNum += 1
                newHeadX = []
                newHeadY = []

                for pointNum in range(len(headXPoints)):
                    nextX, nextY = rotateAroundOrigin(
                        headXPoints[pointNum], headYPoints[pointNum], headXPoints[1], headYPoints[1], -headYaw[row], inRads=False)
                    nextX = nextX + currentOffset
                    nextY = nextY
                    newHeadX.append(nextX)
                    newHeadY.append(nextY)
                currentOffset += drawOffset
                fig.add_trace(go.Scatter(x=newHeadX, y=newHeadY,
                              mode='lines', line=dict(color="black")))

            if currentHeadNum > 1:
                fig.update_layout(title='Head Plot')
                figures.append(fig)
                startIndex = timeRanges[currentBout][0]
                endIndex = timeRanges[currentBout][1]
                labels.append(f"head_plot_range_[{startIndex},_{endIndex}]")
                fig.write_image(os.path.join(
                    outputsDict['outputFolder'], f"head_plot_range_[{startIndex},_{endIndex}].png"))
            currentBout += 1

        tabs_html = """
        <html>
        <head>
        <style>
        body {
            font-family: sans-serif;
            background-color: #f9f9f9;
        }
        #tabs {
            margin-bottom: 10px;
        }
        .tab-button {
            padding: 10px 16px;
            cursor: pointer;
            display: inline-block;
            background-color: #eee;
            border: 1px solid #ccc;
            border-bottom: none;
            margin-right: 5px;
            border-radius: 6px 6px 0 0;
            font-weight: bold;
        }
        .tab-button.active {
            background-color: #fff;
            border-bottom: 1px solid #fff;
        }
        .tab {
            display: none;
        }
        .tab.active {
            display: block;
        }
        </style>
        </head>
        <body>
        <div id="tabs">
        """

        # Create the tab buttons
        for i, label in enumerate(labels):
            active_class = "active" if i == 0 else ""
            tabs_html += f'<div class="tab-button {active_class}" onclick="showTab({i})">{label}</div>'

        tabs_html += '</div>'

        # Create the tab content divs
        for i, fig in enumerate(figures):
            fig_html = fig.to_html(include_plotlyjs=(i == 0), full_html=False)
            active_style = "active" if i == 0 else ""
            tabs_html += f'<div class="tab {active_style}">{fig_html}</div>'

        # Add script for tab functionality
        tabs_html += """
        <script>
        function showTab(index) {
            const tabs = document.getElementsByClassName('tab');
            const buttons = document.getElementsByClassName('tab-button');
            for (let i = 0; i < tabs.length; i++) {
                tabs[i].classList.remove('active');
                buttons[i].classList.remove('active');
            }
            tabs[index].classList.add('active');
            buttons[index].classList.add('active');
        }
        </script>
        </body>
        </html>
        """

        # Write to file
        outputHtmlPath = os.path.join(
            outputsDict['outputFolder'], "head_plots_tabbed.html")
        with open(outputHtmlPath, 'w', encoding='utf-8') as f:
            f.write(tabs_html)
        if openPlots:
            webbrowser.open(outputHtmlPath)
    else:
        fig = go.Figure()

        currentOffset = 0

        # Print row nums
        printToOutput("Head frames: [")
        printToOutput(f"{headRowsByBout[0][0]}")
        for rowNum in range(1, len(headRowsByBout[0])):
            printToOutput(f", {headRowsByBout[0][rowNum]}")
        for boutNum in range(1, len(headRowsByBout)):
            for row in headRowsByBout[boutNum]:
                printToOutput(f", {row}")
        printToOutput("]\n")

        for headRows in headRowsByBout:
            for row in headRows:
                newHeadX = []
                newHeadY = []

                for pointNum in range(len(headXPoints)):
                    nextX, nextY = rotateAroundOrigin(
                        headXPoints[pointNum], headYPoints[pointNum], headXPoints[1], headYPoints[1], -headYaw[row], inRads=False)
                    nextX = nextX + currentOffset
                    nextY = nextY + currentOffset
                    newHeadX.append(nextX)
                    newHeadY.append(nextY)

                fig.add_trace(go.Scatter(x=newHeadX, y=newHeadY,
                              mode='lines', line=dict(color="black")))
                currentOffset += drawOffset

        fig.update_layout(title='Head Plot')
        output_path = f"{outputsDict['outputFolder']}/head_plot_plotly.html"
        fig.write_html(output_path)
        fig.write_image(os.path.join(
            outputsDict['outputFolder'], f"head_plot.png"))
        if openPlots:
            pio.show(fig)
