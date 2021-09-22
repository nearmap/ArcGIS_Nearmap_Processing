# -------------------------------------------------------------------------------
# Name:        CreateSurfaceRasterTilesFromLiDAR.py
# Purpose:     Create surface raster tiles from LiDAR data
# Author:      Geoff Taylor | 3D Solutions Engineer | Esri
#
# Created:     07/06/2019

# Updated:  Geoff Taylor | Sr Solutions Architect | Nearmap | 9/8/2021

# Copyright:   (c) Esri 2019
# Licence:     Apache v2.0
# -------------------------------------------------------------------------------

from arcpy import Describe, AddError, AddMessage, Exists, da, env, SetProgressor, SetProgressorLabel, \
    SetProgressorPosition, ResetProgressor, GetParameterAsText, CheckExtension, CheckOutExtension, CheckInExtension, \
    ExecuteError, GetMessages
from arcpy.analysis import Buffer
from arcpy.management import LasDatasetStatistics, CreateFileGDB, Delete
from arcpy.conversion import LasDatasetToRaster
from arcpy.ddd import PointFileInformation
from os.path import join, splitext, exists
from os import makedirs, remove
from math import ceil

env.overwriteOutput = True

# error classes


class LicenseError3D(Exception):
    pass


class LicenseErrorSpatial(Exception):
    pass


class LicenseError(Exception):
    pass


def get_las_tiles_from_lasd(in_lasd):
    temp_file = f'{Describe(in_lasd).path}\\las_stats_temp.txt'
    LasDatasetStatistics(in_lasd, "SKIP_EXISTING_STATS", temp_file, "LAS_FILES", "COMMA", "DECIMAL_POINT")
    las_list = []
    count = 0
    with open(temp_file) as f:
        for line in f:
            if count > 1:
                las_file = line.strip().split(",")[0]
                if las_file not in las_list:
                    las_list.append(las_file)
            count += 1
    remove(temp_file)
    return [x for x in las_list if x]


def unitsCalc(inFeature):
    SpatialRef = Describe(inFeature).spatialReference
    obtainunits = SpatialRef.linearUnitName
    try:
        if obtainunits == "Foot_US":
            units = "Foot"
            return units
        if obtainunits == "Foot":
            units = "Foot"
            return units
        if obtainunits == "Meter":
            units = "Meter"
            return units
        if obtainunits not in ["Foot_US", "Foot", "Meter"]:
            AddError("Units Not Detected on {0} \n Terminating Process".format(inFeature))
            exit()
    except:
        AddError("Units Not Detected on {0} \n Terminating Process".format(inFeature))
        exit()


def createFolder(folder):
    """Create folder"""
    folder = join(outFolder, folder)
    if not exists(folder):
        makedirs(folder)
    return folder


def createGDB(gdbName):
    """Create geodatabase"""
    gdb = join(outFolder, gdbName)
    if not Exists(gdb):
        AddMessage('Creating geodatabase: {}'.format(gdbName))
        CreateFileGDB(outFolder, gdbName)
    return gdb


def getBufferDist(inFeature):
    if unitsCalc(inFeature) == 'Foot':
        return '{}'.format(ceil(float(cellSize) * 10))
    else:
        return '{}'.format(ceil(float(cellSize) * 3.048))


def createLasFootprints(filesToProcess, lasExtent, suffix, spatialRef, lasExtentBuff):
    """Create LAS footprints"""
    AddMessage('Creating LAS Footprints...')
    PointFileInformation(';'.join(filesToProcess), lasExtent, "LAS", suffix, spatialRef, "NO_RECURSION",
                                  "NO_EXTRUSION", "DECIMAL_POINT", "NO_SUMMARIZE", "NO_LAS_SPACING")
    bufferDistance = getBufferDist(lasExtent)
    Buffer(lasExtent, lasExtentBuff, bufferDistance)
    Delete(lasExtent)
    return


def createRasters(lasExtentBuff, RasterFolder, filesToProcess):
    """Create DEM Raster"""
    AddMessage('Creating Raster Tile data...')
    with da.UpdateCursor(lasExtentBuff, ["FileName", "shape@"]) as cursor:
        for i, row in enumerate(cursor):
            fileName = splitext(row[0])[0]
            env.extent = row[1].extent
            # Create DEM
            outRaster = join(RasterFolder, '{0}_{1}.tif'.format(rasterName, fileName))
            AddMessage('    Creating {0} {1} of {2}  ({3})'.format(rasterName, i + 1, len(filesToProcess),
                                                                         fileName))
            LasDatasetToRaster(inLasDataset, outRaster, "ELEVATION", None, "FLOAT", "CELLSIZE", cellSize, 1)
            env.snapRaster = outRaster
            SetProgressorPosition()
    return


def main_op():
    ext_list = ["3D"]
    try:
        for ext in ext_list:
            if CheckExtension(ext) == "Available":
                CheckOutExtension(ext)
            else:
                raise LicenseError

        if not exists(outFolder):
            makedirs(outFolder)

        # Obtain LiDAR tile Info from Folder
        fileNames = []
        lasCount = 0
        zlasCount = 0

        las_files = get_las_tiles_from_lasd(inLasDataset)
        for fileName in las_files:
            if fileName.endswith('.zlas'):
                zlasCount = zlasCount + 1
                fileNames.append(fileName)
            if fileName.endswith('.las'):
                lasCount = lasCount + 1
                fileNames.append(fileName)

        # Check that LiDAR tiles exist in folder directory location
        SetProgressor("step", "Processing Tiles...", 0, len(fileNames), 1)
        if lasCount == 0 and zlasCount == 0:
            AddMessage("Cancelling Process as 0 LAS or zLAS tiles detected")
            exit()
        elif lasCount > 0 and zlasCount > 0:
            AddMessage("Cancelling Process as {0} zLAS and {1} LAS files detected in process".format(zlasCount, lasCount))
            exit()
        else:
            # Process the LAS files
            spatialRef = Describe(inLasDataset).SpatialReference
            filesToProcess = las_files
            suffix = splitext(fileNames[0])[1].replace('.', '')

            # Set names/values
            outGDB = createGDB('Mosaic.gdb')
            lasExtent = join(outGDB, 'tempTiles')
            lasExtentBuff = join(outGDB, 'Tiles')
            RasterFolder = createFolder('{0}_Tiles'.format(rasterName))

            #processingSteps = (len(fileNames) * 2) + 3  # 2x las files [UPDATE T] + 1 for creating fps, lasDatasets, mosaics
            processingSteps = (len(fileNames))
            SetProgressor('step', 'Processing Files...', 0, processingSteps, 1)

            SetProgressorLabel('Creating footprints')
            createLasFootprints(filesToProcess, lasExtent, suffix, spatialRef, lasExtentBuff)
            SetProgressorPosition()

            SetProgressorLabel('Creating Rasters')
            createRasters(lasExtentBuff, RasterFolder, filesToProcess)

        ResetProgressor()
        AddMessage('Script Complete')

    except LicenseError3D:
        AddError("3D Analyst license is unavailable")

    except ExecuteError:
        AddError(GetMessages(2))

    finally:
        [CheckInExtension(ext) for ext in ext_list]


if __name__ == "__main__":

    # Capture input; create outFolder
    inLasDataset = GetParameterAsText(0)
    outFolder = GetParameterAsText(1)
    cellSize = GetParameterAsText(2)
    rasterName = GetParameterAsText(3)

    main_op()
