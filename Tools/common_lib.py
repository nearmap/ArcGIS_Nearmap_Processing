from arcpy import Exists, Describe, GetMessages, AddMessage, AddError, AddWarning, ExecuteWarning, ExecuteError, da
from arcpy.management import Delete, AddField, CreateFeatureclass
from os import rename, listdir
from os.path import splitext, isfile, join, split
from sys import exc_info


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


def rename_file_extension(data_dir, from_extension, to_extension):
    try:
        files = listdir(data_dir)
        for filename in files:
            infilename = join(data_dir, filename)
            if isfile(infilename):
                file_ext = splitext(filename)[1]
                if from_extension == file_ext:
                    newfile = infilename.replace(from_extension, to_extension)
                    rename(infilename, newfile)

    except ExecuteWarning:
        print(GetMessages(1))
        AddWarning(GetMessages(1))

    except ExecuteError:
        print(GetMessages(2))
        AddError(GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = exc_info()[1]
        print(e.args[0])
        AddError(e.args[0])


def delete_if_exists(in_feature):
    if isinstance(in_feature, str):
        if Exists(in_feature):
            Delete(in_feature)
    if isinstance(in_feature, list):
        [Delete(i) for i in in_feature if Exists(i)]


def _get_path_info(in_file):
    if ".gdb" in in_file:
        f = in_file.split(".gdb\\")
        return [f"{f[0]}.gdb", f[1]]
    elif in_file.endswith(".shp"):
        return split(in_file)
    elif split(in_file)[0] in ["memory", "in_memory"]:
        return split(in_file)
    if ".gdb" in in_file:
        f = in_file.split(".gdb\\")
        return [f"{f[0]}.gdb", f[1]]
    elif in_file.endswith(".shp"):
        return split(in_file)
    elif split(in_file)[0] in ["memory", "in_memory"]:
        return split(in_file)


def gen_tile_grid(in_fc, num_splits, out_file="Bounds"):
    x_list = []
    y_list = []
    for row in da.SearchCursor(in_fc, ['Id', 'SHAPE@']):
        AddMessage(f"Generating Tile Grid Tile {row[0]}")
        array1 = row[1].getPart()
        for vert in range(row[1].pointCount):
            pnt = array1.getObject(0).getObject(vert)
            x_list.append(pnt.X)
            y_list.append(pnt.Y)
    x_min = min(x_list)
    x_max = max(x_list)
    y_min = min(y_list)
    y_max = max(y_list)
    x_interval = (x_max - x_min) / (num_splits+1)  # Must add 1 to the splits
    y_interval = (y_max - y_min) / (num_splits+1)  # Must add 1 to the splits

    x_intervals = [x_min]
    [x_intervals.append(i) for i in [(x_min + x_interval * (_+1)) for _ in range(num_splits)]]
    x_intervals.append(x_max)

    y_intervals = [y_min]
    [y_intervals.append(i) for i in [(y_min + y_interval * (_+1)) for _ in range(num_splits)]]
    y_intervals.append(y_max)

    x_min_max_coords = list(zip(x_intervals, x_intervals[1:]))
    y_min_max_coords = list(zip(y_intervals, y_intervals[1:]))

    row_count = 0
    count = 0
    bounds_list = []
    for row in x_min_max_coords:
        column_count = 0
        for column in y_min_max_coords:
            #print(f"count: {count} row: {row_count} column: {column_count}", row, column)
            bounds_list.append(list(zip(row, column)))
            count += 1
            column_count += 1
        row_count += 1

    if out_file.lower() == "bounds_list":
        return bounds_list

    if ".gdb" in out_file.lower() or "memory" in out_file.lower() or out_file.lower().endswith(".shp"):
        desc = Describe(in_fc)
        delete_if_exists(out_file)
        out_fc_head, out_fc_tail = _get_path_info(out_file)
        CreateFeatureclass(out_fc_head, out_fc_tail, "POLYGON", None, "DISABLED", "DISABLED", desc.spatialReference, '',
                           0, 0, 0, out_fc_tail.replace(".shp", ""))
        for field in [["Id", "Long"]]:
            AddField(out_file, field[0], field[1], None, None, None, '', "NON_NULLABLE", "NON_REQUIRED", '')
        count = 0

        with da.InsertCursor(out_file, ['SHAPE@', 'Id']) as cursor:
            for i in bounds_list:
                x_min = i[0][0]
                y_min = i[0][1]
                x_max = i[1][0]
                y_max = i[1][1]
                coordinates = [(x_min, y_min), (x_min, y_max), (x_max, y_max), (x_max, y_min)]
                cursor.insertRow([coordinates, count])
                count += 1
        return out_file


def unique_values(table, field):
    with da.SearchCursor(table, [field]) as cursor:
        return sorted({row[0] for row in cursor})


def extent_of_all_datasets(in_dataset_list):
    extent_cds = [[Describe(f).extent.XMin, Describe(f).extent.XMax, Describe(f).extent.YMin, Describe(f).extent.YMax]
                  for f in in_dataset_list]
    x_min = sorted([i[0] for i in extent_cds])[0]
    x_max = sorted([i[1] for i in extent_cds])[-1]
    y_min = sorted([i[2] for i in extent_cds])[0]
    y_max = sorted([i[3] for i in extent_cds])[-1]
    print(extent_cds)
    return [x_min, x_max, y_min, y_max]
