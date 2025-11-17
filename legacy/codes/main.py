# External Imports:
import pandas as pd
import os
import re
import json

# Internal Imports:
from utils.configSetup import getConfig
from utils.mainFuncs import *
import utils.outputDisplay as out
from utils.mainCalculation import getCalculated, setupValueStructs

CONFIG_PATH = "C:\\Users\\Finn\\Downloads\\SLU\\Fall_2025\\CSCI_4961\\CV_Zebrafish\\bruce\\codes\\configs\\BaseConfig.json"

# Initialize arrays for storing values:
# config = getConfig()
config = json.load(open(CONFIG_PATH, 'r'))
out.getOutputFile(config)  # save at results n

if not config["bulk_input"]:
    """ MAIN DATA CALCULATIONS """
    df = pd.read_csv(config["file_inputs"]["data"], header=1)

    out.printToOutput("Input file: {}".format(config["file_inputs"]["data"]))

    # intialization
    calculatedValues, inputValues = setupValueStructs(config, df)

    # For final conversion to pandas dataframe
    resultsList, timeRanges = getCalculated(
        inputValues, calculatedValues, config, df)

    # =================================================================
    out.runAllOutputs(timeRanges, config, resultsList,
                      inputValues, calculatedValues, df)

else:
    # Get input
    inputFolder = config["file_inputs"]["bulk_input_path"]
    inputFileNames = os.listdir(inputFolder)

    # Get bulk output
    outputBasePath = 'bulk_results'
    os.makedirs(outputBasePath, exist_ok=True)

    pattern = re.compile(r'^Results (\d+)$')
    existingNumbers = []

    for name in os.listdir(outputBasePath):
        fullPath = os.path.join(outputBasePath, name)
        match = pattern.match(name)
        if os.path.isdir(fullPath) and match:
            existingNumbers.append(int(match.group(1)))

    nextIndex = max(existingNumbers) + 1 if existingNumbers else 1
    newFolderName = f"Results {nextIndex}"
    bulkOutputFolder = os.path.join(outputBasePath, newFolderName)
    os.makedirs(bulkOutputFolder)

    # print results in seperate output folders for
    for fileName in inputFileNames:
        if fileName[-4:len(fileName)] != ".csv":
            continue
        cutFileName = fileName[0:-4]
        if len(cutFileName) > 41:
            cutFileName = cutFileName[0:35] + "_short"

        # Get output folder and log path
        inputFile = os.path.join(inputFolder, fileName)
        df = pd.read_csv(inputFile, header=1)

        newOutputFolder = os.path.join(bulkOutputFolder, cutFileName)
        os.makedirs(newOutputFolder)
        out.outputsDict["outputFolder"] = newOutputFolder

        out.outputsDict["log"] = os.path.join(newOutputFolder, "log.txt")
        out.printToOutput(
            f"Bulk Output folder: {newFolderName}\\{cutFileName}")

        # Run calculations
        calculatedValues, inputValues = setupValueStructs(config, df)

        # For final conversion to pandas dataframe
        resultsList, timeRanges = getCalculated(
            inputValues, calculatedValues, config, df)

        # Write output
        out.runAllOutputs(timeRanges, config, resultsList,
                          inputValues, calculatedValues, df)
