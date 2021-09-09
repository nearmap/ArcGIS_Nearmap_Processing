from arcpy.management import LasDatasetStatistics, CreateFeatureclass, Delete, AddField
from arcpy import Describe, da, Exists
from os.path import split, exists
from os import remove


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
                    print(las_file)
                    las_list.append(las_file)
            count += 1
    remove(temp_file)
    return [x for x in las_list if x]


def las_files_extents(in_lasd, out_fc):

    def get_path_info(in_file):
        if ".gdb" in in_file:
            f = in_file.split(".gdb\\")
            return [f"{f[0]}.gdb", f[1]]
        elif in_file.endswith(".shp"):
            return split(in_file)
        elif split(in_file)[0] in ["memory", "in_memory"]:
            return split(in_file)

    sr = Describe(in_lasd).spatialReference
    if Exists(out_fc):
        Delete(out_fc)
    out_fc_head, out_fc_tail = get_path_info(out_fc)
    CreateFeatureclass(out_fc_head, out_fc_tail, "POLYGON", None, "DISABLED", "ENABLED", sr, '', 0, 0, 0,
                       out_fc_tail.replace(".shp", ""))
    for field in [["LAS", "STRING"], ["ZMIN", "DOUBLE"], ["ZMAX", "DOUBLE"]]:
        AddField(out_fc, field[0], field[1], None, None, None, '', "NON_NULLABLE", "NON_REQUIRED", '')
    las_files = get_las_tiles_from_lasd(in_lasd)
    extent_list = []
    for _ in las_files:
        extent = Describe(_).extent
        extent_list.append([_, extent.XMin, extent.YMin, extent.XMax, extent.YMax, extent.ZMin, extent.ZMax])

    with da.InsertCursor(out_fc, ['SHAPE@', 'SHAPE@Z', 'LAS', 'ZMIN', 'ZMAX', 'Id']) as cursor:
        count = 0
        for i in extent_list:
            coordinates = [(i[1], i[2]), (i[1], i[4]), (i[3], i[4]), (i[3], i[2])]
            cursor.insertRow([coordinates, i[5], i[0], i[5], i[6], count])
            count += 1
    return out_fc
