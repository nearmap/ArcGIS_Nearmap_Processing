import arcpy
import os
import sys


def rename_file_extension(data_dir, from_extentsion, to_extension):
    try:
        files = os.listdir(data_dir)
        for filename in files:
            infilename = os.path.join(data_dir, filename)
            if os.path.isfile(infilename):
                file_ext = os.path.splitext(filename)[1]
                if from_extentsion == file_ext:
                    newfile = infilename.replace(from_extentsion, to_extension)
                    os.rename(infilename, newfile)

    except arcpy.ExecuteWarning:
        print((arcpy.GetMessages(1)))
        arcpy.AddWarning(arcpy.GetMessages(1))

    except arcpy.ExecuteError:
        print((arcpy.GetMessages(2)))
        arcpy.AddError(arcpy.GetMessages(2))

    # Return any other type of error
    except:
        # By default any other errors will be caught here
        #
        e = sys.exc_info()[1]
        print((e.args[0]))
        arcpy.AddError(e.args[0])
