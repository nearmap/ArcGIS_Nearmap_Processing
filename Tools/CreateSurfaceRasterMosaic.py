# -------------------------------------------------------------------------------
# Name:        CreateSurfaceRasterMosaic.py
# Purpose:     Process for creating a 8 bit unsigned mosaic raster from tiles
# Authors:     Geoff Taylor | 3D Solutions Engineer | Esri (Framework)
#              Arthur Crawford | Content Product Engineer | Esri (Concept and improvement using raster functions)
#              Andrew Watson | 2017 Esri TWI Program 
# Created:     04/19/2017

# Updated:  Geoff Taylor | Sr Solutions Architect | Nearmap | 9/8/2021

# Copyright:   (c) Esri 2017
# Licence:
# -------------------------------------------------------------------------------

from arcpy import GetParameterAsText, AddMessage
from arcpy.management import CreateMosaicDataset, AddRastersToMosaicDataset, CalculateStatistics, GetRasterProperties, \
    SetMosaicDatasetProperties
from arcpy.mp import ArcGISProject
import os

inTileFolder = GetParameterAsText(0)
gdb = GetParameterAsText(1)
spatialRef = GetParameterAsText(2)
mosaicName = GetParameterAsText(3)

# Create mosaic dataset
CreateMosaicDataset(gdb, mosaicName, spatialRef, None, "32_BIT_FLOAT", "CUSTOM", None)
mosaicDS = os.path.join(gdb, mosaicName)
AddMessage('Mosaic dataset {} created...'.format(mosaicName))

# Add rasters to mosaic and set cell size
AddMessage('Adding rasters to mosaic dataset...')
AddRastersToMosaicDataset(mosaicDS, "Raster Dataset", inTileFolder,
                          "UPDATE_CELL_SIZES", "UPDATE_BOUNDARY", "NO_OVERVIEWS", None, 0, 1500,
                          None, None, "SUBFOLDERS", "ALLOW_DUPLICATES", "NO_PYRAMIDS", "NO_STATISTICS",
                          "NO_THUMBNAILS", None, "NO_FORCE_SPATIAL_REFERENCE", "NO_STATISTICS", None)

AddMessage('Calculating Statistics...')
CalculateStatistics(mosaicDS, 1, 1, [], "OVERWRITE")

# Update mosaic cell size
AddMessage('Updating mosaic cell size...')
cellSize = GetRasterProperties(mosaicDS, "CELLSIZEX")
newSize = float(float(cellSize.getOutput(0))/2)
SetMosaicDatasetProperties(mosaicDS, cell_size=newSize)

# Add results to the display
AddMessage('Adding results to map views...')
aprx = ArcGISProject("CURRENT")
for m in aprx.listMaps():
    if m.mapType == "MAP":
        m.addDataFromPath(mosaicDS)
    elif m.mapType == "SCENE":
        m.addDataFromPath(mosaicDS)

AddMessage("Process complete")
