from arcpy.ddd import ExtractLas
from arcpy import env, GetParameterAsText, GetParameter, CheckExtension, CheckOutExtension, CheckInExtension, ExecuteError, GetMessages
from arcpy.management import Dissolve, Delete, LasPointStatsAsRaster, EliminatePolygonPart, CopyFeatures, GetCount, \
    PolygonToLine, AddField, CalculateField, DeleteField, RepairGeometry, Sort, CreateLasDataset
from arcpy.analysis import Intersect, SpatialJoin, Select, Union
from arcpy.conversion import RasterToPolygon
from arcpy.sa import IsNull, ExtractByMask
from arcpy import da, Describe, AddMessage, AddError, AddWarning, CreateUniqueName
from arcpy.mp import ArcGISProject
from las_lib import las_files_extents, generate_extent_polygon, list_all_las_files_in_directory
from os.path import join, dirname, isdir
from os import replace
from pathlib import Path
from re import sub
from common_lib import delete_if_exists, unitsCalc, gen_tile_grid, unique_values, extent_of_all_datasets
from las_lib import check_consistent_sr
from glob import glob
from shutil import copyfile, rmtree
from tempfile import gettempdir


# error classes

class LicenseError3D(Exception):
    pass


class LicenseErrorSpatial(Exception):
    pass


######################################
# PointCloud Cookie Cutter Functions
####################################


def rename_las_tiles(tile_folder, source_file_basename="Source", updated_file_basename="Updated"):
    source_count = 0
    updated_count = 0
    files = glob(f"{tile_folder}/*")
    for f in files:
        file_extension = Path(f).suffix
        file_name = Path(f).stem
        if file_extension in [".las", ".laz", ".zlas"] and file_extension not in [".lasx"]:
            if sub('[^a-zA-Z]+', '', file_name).endswith(source_file_basename):
                new_file = f"{tile_folder}\\{source_file_basename}_{source_count}{file_extension}"
                replace(f, new_file)
                source_count += 1
            elif sub('[^a-zA-Z]+', '', file_name).endswith(updated_file_basename):
                new_file = f"{tile_folder}\\{updated_file_basename}_{updated_count}{file_extension}"
                replace(f, new_file)
                updated_count += 1
        elif file_extension in ".lasx":  # Delete all .lasx auxillary files
            Path(f).unlink()


def retile_las_grid(in_lasd, out_folder, in_source_tile_extents, in_id, num_splits, spatial_reference):
    in_memory_geom = "memory/in_memory_geom"
    Select(in_source_tile_extents, in_memory_geom, f"Id = {in_id}")
    in_memory_tiled_geom = "memory/in_memory_tiled_geom"
    gen_tile_grid(in_memory_geom, num_splits, in_memory_tiled_geom)
    AddMessage(f"Re-Tiling pointclouds for Tile: {in_id}")
    # Use Recursive "ExtractLas" as "TileLas" GP tool won't work correctly
    with da.SearchCursor(in_memory_tiled_geom,
                         ["Id", "SHAPE@"], sql_clause=(None, 'ORDER BY Id DESC')) as tile_cursor:
        for grid_tile in tile_cursor:
            grid_id, grid_geom = grid_tile
            ExtractLas(in_lasd, out_folder, "DEFAULT", grid_geom, "PROCESS_EXTENT",
                       f"Updated_{grid_id}", "REMOVE_VLR", "REARRANGE_POINTS", "COMPUTE_STATS", None,
                       "SAME_AS_INPUT")
    delete_if_exists([in_memory_geom, in_memory_tiled_geom])
    return


def cut_tile(in_source_lasd, in_update_lasd, in_cookie_cutter_fc, in_source_tile_extents, out_folder, out_lasd, retile,
             num_splits):
    copied_list = []
    modified_tile_ids = []
    num_features = GetCount(in_cookie_cutter_fc)[0]
    sr = Describe(in_source_lasd).spatialReference
    out_tile_folder = None
    scratch_tile_folder = None
    id_list = []

    with da.SearchCursor(in_cookie_cutter_fc, ["Id", "STATUS", "DATASET", "SHAPE@", "LAS"],
                         sql_clause=(None, 'ORDER BY Id DESC')) as cursor:
        count = 0
        current_id = 0
        for row in cursor:
            Id, status, dataset, geom, las = row
            AddMessage(f"Processing PointCloud Tile: {Id} | Conducting PointCloud Clipping Operations on on shape "
                       f"{count} of {int(num_features)-1}")
            if int(current_id) != int(Id):
                current_id = int(Id)
            out_tile_folder = f"{out_folder}/tiles/tile_{Id}"
            if dataset == "Source" and status != "Source":
                if Id not in id_list:
                    id_list.append(Id)
                AddMessage(f"Clipped Source Dataset Tile")
                Path(out_tile_folder).mkdir(parents=True, exist_ok=True)  # Make folder if not exist
                scratch_tile_folder = out_tile_folder
                if retile:
                    scratch_tile_folder = f"{out_tile_folder}_scratch"
                    Path(scratch_tile_folder).mkdir(parents=True, exist_ok=True)
                ExtractLas(in_source_lasd, scratch_tile_folder, "DEFAULT", geom, "PROCESS_EXTENT", f"Source",
                           "REMOVE_VLR", "REARRANGE_POINTS", "COMPUTE_STATS", None, "SAME_AS_INPUT")
                modified_tile_ids.append(Id)

            elif dataset == "Updated" and status != "Source":
                if Id not in id_list:
                    id_list.append(Id)
                AddMessage(f"Clipped Updated Dataset Tile")
                Path(out_tile_folder).mkdir(parents=True, exist_ok=True)  # Make folder if not exist
                scratch_tile_folder = out_tile_folder
                if retile:
                    scratch_tile_folder = f"{out_tile_folder}_scratch"
                    Path(scratch_tile_folder).mkdir(parents=True, exist_ok=True)
                Path(scratch_tile_folder).mkdir(parents=True, exist_ok=True)  # Make folder if not exist
                ExtractLas(in_update_lasd, scratch_tile_folder, "DEFAULT", geom, "PROCESS_EXTENT", f"Updated",
                           "REMOVE_VLR", "REARRANGE_POINTS", "COMPUTE_STATS", None, "SAME_AS_INPUT")
                modified_tile_ids.append(Id)
            elif dataset == "Source" and status == "Source":
                AddMessage(f"Copied Source Tile")
                file_extension = Path(las).suffix
                out_las_file = f"{dirname(out_tile_folder)}\\Source_{Id}{file_extension}"
                copyfile(las, out_las_file)
                copied_list.append(las)
            else:
                AddWarning(f"unknown issue processing file: {las}")
            count += 1
    if retile:  # Deal with last feature if retile is enabled
        AddMessage("Begin Re-tiling Processed Data")
        files_list = list_all_las_files_in_directory(out_folder)
        temp_lasd = CreateUniqueName('temp.lasd', gettempdir())
        CreateLasDataset(files_list, temp_lasd, "NO_RECURSION", None, sr, "COMPUTE_STATS", "ABSOLUTE_PATHS", "NO_FILES")
        id_values = unique_values(in_source_tile_extents, "Id")
        for my_id in id_list:
            if my_id in id_values:
                out_tile_folder = f"{out_folder}/tiles/tile_{my_id}"
                scratch_tile_folder = f"{out_folder}/tiles/tile_{my_id}_scratch"
                retile_las_grid(in_lasd=temp_lasd, out_folder=out_tile_folder,
                                in_source_tile_extents=in_source_tile_extents, in_id=my_id, num_splits=num_splits,
                                spatial_reference=sr)
        rmtree(scratch_tile_folder)
        delete_if_exists(temp_lasd)
    # Rename Tiles
    folders_to_process = [d for d in glob(f"{out_folder}\\tiles\\*") if isdir(d)]
    AddMessage("Renaming Resulting Tiles")
    for f in folders_to_process:
        rename_las_tiles(f, source_file_basename="Source", updated_file_basename="Updated")
    if out_lasd:
        AddMessage("Generating LAS Dataset")
        files_list = list_all_las_files_in_directory(out_folder)
        CreateLasDataset(files_list, out_lasd, "NO_RECURSION", None, sr, "COMPUTE_STATS", "ABSOLUTE_PATHS", "NO_FILES")
        try:
            # Add results to the display
            AddMessage('Adding las dataset to contents...')
            aprx = ArcGISProject("CURRENT")
            for m in aprx.listMaps():
                if m.mapType == "MAP":
                    # arcpy.AddMessage('map={}'.format(m.name))
                    m.addDataFromPath(out_lasd)
                elif m.maptype == "SCENE":
                    m.addDataFromPath(out_lasd)
        except:
            pass


######################
# Cut Tile Functions
####################


def las_data_boundary(in_lasd, scratch_folder, out_fc, clipping_geom, simplify=True):
    # TODO: describe lidar to determine appropriate pixel size
    Path(scratch_folder).mkdir(parents=True, exist_ok=True)
    # Extract actual point-cloud extent from lasd as raster
    if clipping_geom:
        env.extent = clipping_geom
    temp_pt_stats_raster = join(scratch_folder, "temp_pt_stats_raster.tif")
    delete_if_exists(temp_pt_stats_raster)
    LasPointStatsAsRaster(in_lasd, temp_pt_stats_raster, "INTENSITY_RANGE", "CELLSIZE", 0.5)
    # Mask Raster by clipping geom if input by user
    out_raster = IsNull(temp_pt_stats_raster)
    if clipping_geom:
        out_raster = IsNull(ExtractByMask(temp_pt_stats_raster, clipping_geom))
    # Convert point-cloud extent raster to polygonPolygon
    simplify_polygon = "SIMPLIFY"
    if not simplify:
        simplify_polygon = "NO_SIMPLIFY"
    temp_polygon = join("memory", "temp_polygon")
    RasterToPolygon(out_raster, temp_polygon, simplify_polygon, "Value", "SINGLE_OUTER_PART", None)
    delete_if_exists([out_raster, temp_pt_stats_raster])
    hole_area = 10
    temp_polygon_holes_resolved = join("memory", "temp_polygon_holes_resolved")
    EliminatePolygonPart(temp_polygon, temp_polygon_holes_resolved, "AREA", f"{hole_area} SquareMeters", 0, "CONTAINED_ONLY")
    Delete(temp_polygon)
    units = unitsCalc(temp_polygon_holes_resolved)
    hole_area_convert = hole_area
    if units == "Foot":
        hole_area_convert = hole_area*3.28084
    with da.UpdateCursor(temp_polygon_holes_resolved, ["SHAPE@AREA"]) as cursor:
        for row in cursor:
            if row[0] <= hole_area_convert*hole_area_convert:
                cursor.deleteRow()
    extent_polygon = join("memory", "extent_polygon")
    delete_if_exists(extent_polygon)
    generate_extent_polygon(temp_polygon_holes_resolved, extent_polygon)
    extent_line = join("memory", "extent_line")
    delete_if_exists(extent_line)
    PolygonToLine(extent_polygon, extent_line, "IDENTIFY_NEIGHBORS")
    extent_boundary = out_fc
    delete_if_exists(extent_boundary)
    SpatialJoin(temp_polygon_holes_resolved, extent_line, extent_boundary, "JOIN_ONE_TO_ONE", "KEEP_ALL", "",
                "INTERSECT", "1 Meters", '')
    AddField(extent_boundary, "DATASET", "STRING", None, None, None, '', "NULLABLE", "NON_REQUIRED", '')
    with da.UpdateCursor(extent_boundary, ["Join_Count", "gridcode", "DATASET"]) as cursor:
        for row in cursor:
            if row[0] == 1 and row[1] == 1:
                cursor.deleteRow()
            elif row[1] == 0:
                row[2] = "Updated"
                cursor.updateRow(row)
            elif row[1] == 1:
                row[2] = "Source"
                cursor.updateRow(row)
    DeleteField(extent_boundary, ['Join_Count', 'TARGET_FID', 'gridcode', 'ORIG_FID', 'LEFT_FID', 'RIGHT_FID'])
    delete_if_exists([temp_polygon_holes_resolved, extent_polygon, extent_line])
    RepairGeometry(extent_boundary, "DELETE_NULL", "OGC")
    return extent_boundary


def check_extents_intersect(file_1, file_2):
    file_1_extent_poly = join("memory", "file_1_extent_poly")
    generate_extent_polygon(file_1, file_1_extent_poly)
    file_2_extent_poly = join("memory", "file_2_extent_poly")
    generate_extent_polygon(file_2, file_2_extent_poly)
    intersect_geom = join("memory", "intersect_geom")
    Intersect([file_1_extent_poly, file_2_extent_poly], intersect_geom, "ALL", None, "INPUT")
    intersects = False
    if int(GetCount(intersect_geom)[0]) > 0:
        intersects = True
    [Delete(i) for i in [file_1_extent_poly, file_2_extent_poly, intersect_geom]]  # Deletes intermediate data
    if intersects:
        AddMessage(f"Detected the two las datasets intersect... continuing process")
    else:
        AddError(f"Detected the two las datasets do not intersect... terminating process")
        exit()


def las_tiles_to_update(source_lasd, update_lasd, out_folder, out_lasd=None):
    source_lasd_geom = join("memory", "source_lasd_geom")
    delete_if_exists(source_lasd_geom)
    las_files_extents(in_lasd=source_lasd, out_fc=source_lasd_geom)
    update_lasd_geom = join("memory", "update_lasd_geom")
    delete_if_exists(update_lasd_geom)
    las_files_extents(in_lasd=update_lasd, out_fc=update_lasd_geom)
    update_lasd_geom_dissolved = join("memory", "update_lasd_geom_dissolved")
    delete_if_exists(update_lasd_geom_dissolved)
    Dissolve(update_lasd_geom, update_lasd_geom_dissolved, None, None, "MULTI_PART", "DISSOLVE_LINES")
    delete_if_exists(update_lasd_geom)
    intersect_boundary_pre = join("memory", "difference_lasd_tile_bounds")
    delete_if_exists(intersect_boundary_pre)
    Intersect([source_lasd_geom, update_lasd_geom_dissolved], intersect_boundary_pre, "ALL", None, "INPUT")
    delete_if_exists([source_lasd_geom, update_lasd_geom_dissolved])
    values = [[row[0], row[1]] for row in da.SearchCursor(intersect_boundary_pre, ["Id", "LAS"])]
    AddMessage(f"Detected {len(values)} source tiles to be augmented with updated tiles")
    delete_if_exists(intersect_boundary_pre)
    return values


def generate_pointcloud_cookie_cutter(in_source_lasd, in_update_lasd, output_folder, update_lasd_clipping_geom):
    # Ensure las datasets have the same spatial reference
    check_consistent_sr(in_file1=in_source_lasd, in_file2=in_update_lasd)
    # Ensure las datasets Extents intersect
    check_extents_intersect(in_source_lasd, in_update_lasd)
    # Obtain Polygon Boundary where point-clouds exists in las-dataset for augmenting into source lidar dataset
    lasd_boundary = join(output_folder, "lasd_boundary.shp")
    delete_if_exists(lasd_boundary)
    las_data_boundary(in_update_lasd, output_folder, lasd_boundary, clipping_geom=update_lasd_clipping_geom,
                      simplify=True)
    # Detect the LAS Tiles in the source LiDAR dataset that will be updated.
    tiles = las_tiles_to_update(in_source_lasd, in_update_lasd, output_folder)
    source_tile_extents = join(output_folder, "source_tile_extents_clip.shp")
    #source_tile_extents = join("memory", "source_tile_extents")
    delete_if_exists(source_tile_extents)
    las_files_extents(in_lasd=in_source_lasd, out_fc=source_tile_extents)
    print(f"Process will update {len(tiles)} of {GetCount(source_tile_extents)[0]} tiles")
    AddField(source_tile_extents, "STATUS", "STRING", None, None, None, '', "NULLABLE", "NON_REQUIRED", '')
    tile_paths_for_processing = [i[1] for i in tiles]
    with da.UpdateCursor(source_tile_extents, ["LAS", "STATUS"]) as cursor:
        for row in cursor:
            if row[0] in tile_paths_for_processing:
                row[1] = "Updated"
            else:
                row[1] = "Source"
            cursor.updateRow(row)
    processed_tile_extents = join("memory", "processed_tile_extents")
    delete_if_exists(processed_tile_extents)
    Select(source_tile_extents, processed_tile_extents, "STATUS = 'Updated'")
    tile_processing_template = join("memory", "tile_processing_template")
    delete_if_exists(tile_processing_template)
    Union([source_tile_extents, lasd_boundary], tile_processing_template, "ALL", None, "GAPS")
    with da.UpdateCursor(tile_processing_template, ["STATUS", "DATASET"]) as cursor:
        for row in cursor:
            if not row[0] or row[0].rstrip() == "":  # Delete Empty Erroneous Geoms
                cursor.deleteRow()
            elif not row[1] or row[1].rstrip() == "":  # Attribute Geometries to not process
                row[1] = "Source"
                cursor.updateRow(row)
    Delete(processed_tile_extents)
    RepairGeometry(tile_processing_template, "DELETE_NULL", "OGC")
    DeleteField(tile_processing_template, ['FID_lasd_b', 'id_1', 'FID_source'])
    tile_processing_template_sorted = join(output_folder, "tile_processing_template.shp")
    #tile_processing_template_sorted = join("memory", "tile_processing_template_sorted")
    delete_if_exists(tile_processing_template_sorted)
    Sort(tile_processing_template, tile_processing_template_sorted, "Id ASCENDING", "UR")
    Delete(tile_processing_template)
    return tile_processing_template_sorted, source_tile_extents


def pointcloud_updater(in_source_lasd, in_update_lasd, output_folder, output_lasd, retile, number_splits,
                       update_lasd_clipping_geom):
    ext_list = ["3D", "Spatial"]
    try:
        for ext in ext_list:
            if CheckExtension(ext) == "Available":
                CheckOutExtension(ext)

        in_cookie_cutter_fc, in_source_tile_extents = generate_pointcloud_cookie_cutter(in_source_lasd, in_update_lasd,
                                                                                        output_folder,
                                                                                        update_lasd_clipping_geom)
        cut_tile(in_source_lasd, in_update_lasd, in_cookie_cutter_fc, in_source_tile_extents, output_folder, output_lasd,
                 retile, number_splits)
        delete_if_exists([in_cookie_cutter_fc, in_source_tile_extents])

    except LicenseError3D:
        AddError("3D Analyst license is unavailable")

    except LicenseErrorSpatial:
        AddError("Spatial Analyst license is unavailable")

    except ExecuteError:
        AddError(GetMessages(2))

    finally:
        [CheckInExtension(ext) for ext in ext_list]


if __name__ == "__main__":
    debug = False
    if debug:
        in_source_lasd = r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\ARRA_LFTNE_Massachusetts_2011.lasd'
        in_update_lasd = r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\Nearmap_PhoDAR_2020_1p4.lasd'
        output_folder = r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\Data\ScratchTest1'
        output_lasd = r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\It_Works_Yayah.lasd'
        retile = True
        number_splits = 2
        update_lasd_clipping_geom = r''
        # r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\Data\Scratch\clipping_geom.shp'
        pointcloud_updater(in_source_lasd, in_update_lasd, output_folder, output_lasd, retile, number_splits,
                           update_lasd_clipping_geom)
    else:
        in_source_lasd = GetParameterAsText(0)
        in_update_lasd = GetParameterAsText(1)
        output_folder = GetParameterAsText(2)
        output_lasd = GetParameterAsText(3)
        retile = GetParameterAsText(4)
        if retile == "true":
            retile = True
        else:
            retile = False
        number_splits = int(GetParameter(5))
        update_lasd_clipping_geom = GetParameterAsText(6)
        pointcloud_updater(in_source_lasd, in_update_lasd, output_folder, output_lasd, retile, number_splits,
                           update_lasd_clipping_geom)
