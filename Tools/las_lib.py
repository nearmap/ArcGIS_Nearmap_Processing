from arcpy.management import LasDatasetStatistics, CreateFeatureclass, Delete, AddField
from arcpy import Describe, da, Exists, AddMessage, AddError
from os.path import split, exists
from os import remove, walk
from common_lib import _get_path_info
from pathlib import Path


def generate_extent_polygon(in_feature, out_polygon):
    desc = Describe(in_feature)
    extent = desc.extent
    coordinates = [(extent.XMin, extent.YMin), (extent.XMin, extent.YMax), (extent.XMax, extent.YMax), (extent.XMax, extent.YMin)]
    out_fc_head, out_fc_tail = _get_path_info(out_polygon)
    CreateFeatureclass(out_fc_head, out_fc_tail, "POLYGON", None, "DISABLED", "DISABLED", desc.spatialReference, '', 0,
                       0, 0, out_fc_tail.replace(".shp", ""))
    for field in [["Id", "Long"]]:
        AddField(out_polygon, field[0], field[1], None, None, None, '', "NON_NULLABLE", "NON_REQUIRED", '')
    with da.InsertCursor(out_polygon, ['SHAPE@', 'Id']) as cursor:
        cursor.insertRow([coordinates, 0])
    return out_polygon


def check_consistent_sr(in_file1, in_file2):
    in_file1_sr = Describe(in_file1).spatialReference
    in_file2_sr = Describe(in_file2).spatialReference
    if in_file1_sr.factoryCode == in_file2_sr.factoryCode:
        AddMessage(f"Detected Consistent Spatial References Between Datasets: {in_file1_sr.name}")
    else:
        AddError(f"Spatial References are not consistent between datasets. \n Reproject the data so both datasets "
                 f"share the same Spatial Reference. \n Dataset 1 SR = {in_file1_sr.name} \n Dataset 2 SR = "
                 f"{in_file2_sr.name} \n The process may require LASTools to reproject one datasets Spatial Reference "
                 f"to aligns with the other dataset")
        exit()
    if in_file1_sr.linearUnitName == in_file2_sr.linearUnitName:
        AddMessage(f"Detected Consistent Linear Units of Measure Between Datasets: {in_file1_sr.linearUnitName}")
    else:
        AddError(f"Linear Units of Measure are not consistent between datasets. \n "
                 f"Reproject the data so both datasets share the same Spatial Reference and the necessary Linear Unit. "
                 f"\n Dataset 1 SR = {in_file1_sr.name} current units: "
                 f"{in_file1_sr.linearUnitName} \n Dataset 2 SR = {in_file2_sr.name} \n "
                 f"The process may require LASTools to reproject one datasets Spatial Reference to aligns with the "
                 f"other dataset")
        exit()
    if in_file1_sr.VCS.factoryCode == in_file2_sr.VCS.factoryCode:
        AddMessage(f"Detected Consistent Vertical Coordinate Systems Between Datasets: {in_file1_sr.VCS.name}")
    else:
        AddError(f"Vertical Coordinate Systems are not consistent between datasets. \n Reproject the data so both "
                 f"datasets share the same Spatial Reference. \n Dataset 1 SR = {in_file1_sr.VCS.name} "
                 f"{in_file1_sr.VCS.factoryCode} \n Dataset 2 SR = {in_file2_sr.VCS.name} {in_file2_sr.VCS.factoryCode}"
                 f"\n You may be able to simply update the VCS in ArcGIS Pro under for the specific las dataset under "
                 f"the las dataset properties in the catalog panel.")
        exit()
    return True


def list_all_las_files_in_directory(out_folder):
    files_list = []
    for root, dirs, files in walk(out_folder):
        for f in files:
            if Path(f).suffix in [".las", ".laz", ".zlas"] and Path(f).suffix not in [".lasx"]:
                files_list.append(f"{root}\\{f}")
    return files_list


def get_las_tiles_from_lasd(in_lasd):
    temp_file = f'{Describe(in_lasd).path}\\las_stats_temp.txt'
    if exists(temp_file):
        remove(temp_file)
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


def las_files_extents(in_lasd, out_fc):
    sr = Describe(in_lasd).spatialReference
    if Exists(out_fc):
        Delete(out_fc)
    out_fc_head, out_fc_tail = _get_path_info(out_fc)
    CreateFeatureclass(out_fc_head, out_fc_tail, "POLYGON", None, "DISABLED", "ENABLED", sr, '', 0, 0, 0,
                       out_fc_tail.replace(".shp", ""))
    for field in [["LAS", "STRING"], ["ZMIN", "DOUBLE"], ["ZMAX", "DOUBLE"]]:
        AddField(out_fc, field[0], field[1], None, None, None, '', "NON_NULLABLE", "NON_REQUIRED", '')
    las_files = get_las_tiles_from_lasd(in_lasd)
    extent_list = []
    for _ in las_files:
        extent = Describe(_).extent
        extent_list.append([_, extent.XMin, extent.YMin, extent.XMax, extent.YMax, extent.ZMin, extent.ZMax])
    if out_fc.startswith("memory") or out_fc.startswith("in_memory"):  # If processing in "memory" requires adding Id
        AddField(out_fc, "Id", "LONG", None, None, None, '', "NON_NULLABLE", "NON_REQUIRED", '')
    with da.InsertCursor(out_fc, ['SHAPE@', 'SHAPE@Z', 'LAS', 'ZMIN', 'ZMAX', 'Id']) as cursor:
        count = 0
        for i in extent_list:
            coordinates = [(i[1], i[2]), (i[1], i[4]), (i[3], i[4]), (i[3], i[2])]
            cursor.insertRow([coordinates, i[5], i[0], i[5], i[6], count])
            count += 1
    return out_fc
