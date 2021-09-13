from arcpy import AddError, AddMessage, Describe, GetParameterAsText
from las_lib import list_all_las_files_in_directory
from arcpy.management import CreateLasDataset
from arcpy.mp import ArcGISProject
from pathlib import Path


def create_las_dataset_recursive(in_directory, out_lasd, spatial_reference):
    files_list = list_all_las_files_in_directory(in_directory)
    extensions = len(list(set([Path(f).suffix for f in files_list])))
    if extensions > 1:
        AddError(f"Detected more than one las format in directory. {extensions}")
        exit()
    if not Path(out_lasd).suffix == ".lasd":
        AddError(f'Error with output lasd formatting. Must end with ".lasd" extension {out_lasd}')
        exit()
    AddMessage("Generating LAS Dataset")
    CreateLasDataset(files_list, out_lasd, "NO_RECURSION", None, spatial_reference, "COMPUTE_STATS", "ABSOLUTE_PATHS", 
                     "NO_FILES")
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


if __name__ == "__main__":
    debug = False
    if debug:
        in_directory = r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\Data\ScratchTiles_All_Retiled'
        out_lasd = r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Nearmap_Processing\pointcloud_updated_retiled.lasd'
        spatial_reference = Describe(r'C:\Users\geoff.taylor\Documents\ArcGIS\Projects\Boston\Nearmap_PhoDAR_2020_1p4.lasd').spatialReference
        create_las_dataset_recursive(in_directory, out_lasd, spatial_reference)
    else:
        in_directory = GetParameterAsText(0)
        out_lasd = GetParameterAsText(1)
        spatial_reference = GetParameterAsText(2)
        create_las_dataset_recursive(in_directory, out_lasd, spatial_reference)
