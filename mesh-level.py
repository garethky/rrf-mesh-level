# mesh-level.py
#
# This program converts probing records from irregular x/y coordinate locations into a heightmap.csv file that RRF can use.
# The primary use is moving probing points away from magnets in magnetic beds.
# It uses Radial Basis Functions to interpolate a surface from the set of probed points and to compute the heightmap.

import argparse
import sys
import re
import os
import datetime

# Dependencies
# on the pi, these can be installed with:
# $ sudo apt-get install python3-scipy
import numpy as np
from scipy.interpolate import Rbf


colonSeparatedNumbersPattern = re.compile('-?\\d+:-?\\d+')

def colonSeparatedNumbersArgType(arg_value):
    if not colonSeparatedNumbersPattern.match(arg_value):
        raise argparse.ArgumentTypeError
    return arg_value

parser = argparse.ArgumentParser(description='Process a bed probing log and generate a heightmap.csv')
# Add the arguments

parser.add_argument('-X',
                       '--x-extents',
                       metavar='X_EXTENTS',
                       type=colonSeparatedNumbersArgType,
                       action='store',
                       required=True,
                       help='Minimum and maximum X coordinates of the final reported grid, separated by \':\'. E.g. -X -10:200. This is required.')

parser.add_argument('-Y',
                       '--y-extents',
                       metavar='Y_EXTENTS',
                       type=colonSeparatedNumbersArgType,
                       action='store',
                       required=True,
                       help='Minimum and maximum Y coordinates of the final reported grid, separated by \':\'. E.g. -Y 3:305. This is required.')

parser.add_argument('-L',
                       '--probe-log-file',
                       metavar='POINTS_FILE',
                       type=str,
                       action='store',
                       default='meshbedprobe.log',
                       help='The path to the probed points log file, defaults to meshbedprobe.log')

parser.add_argument('-H',
                       '--heightmap-file',
                       metavar='MESH_FILE',
                       type=str,
                       default='heightmap.csv',
                       action='store',
                       help='The path to save the heightmap, defaults to heightmap.csv')

parser.add_argument('-P',
                       '--num-points',
                       metavar='NUM_POINTS',
                       type=colonSeparatedNumbersArgType,
                       action='store',
                       help='Number of evenly spaced points to sample in the X and Y axis directions, separated by \':\'. E.g. -P 21:21. Optional, --max-points is used if this is omitted.')

parser.add_argument('-M',
                       '--max-points',
                       metavar='MAX_POINTS',
                       type=int,
                       default=441,
                       action='store',
                       help='The maximum number of points that can be sampled in the heightmap file. The optimal sample point spacing is determined from this value if --num-points is omitted. Optional, Defaults to 441.')

parser.add_argument('-dsf',
                       '--dsf-path-mode',
                       action='store_true',
                       help='Enable DSF path compatibility mode. Treats file paths as M98 would in RRF. The script assumes the working directory is the root of the virtual SD card.')

# convert a raw path to its DSF equivalent path as required
def dsfPath(rawPath, isDsfMode):
    dsfConvertedPath = rawPath
    if isDsfMode:
        # slice off any leading drive designation
        if dsfConvertedPath.startswith('0:') or dsfConvertedPath.startswith('1:'):
            dsfConvertedPath = dsfConvertedPath[2:]

        if dsfConvertedPath.startswith('/'):
            # absolute paths become relative paths to the virtual SD card root
            dsfConvertedPath = '.' + dsfConvertedPath
        else:
            # relative paths are relative to the /sys/ directory on the virtual SD card
            dsfConvertedPath = './sys/' + dsfConvertedPath

    return dsfConvertedPath

# return the optimal point sampling density for the given bed dimensions
def selectMeshInterval(xMin, xMax, yMin, yMax, maxSamplePoints):
    xSideLength = xMax - xMin
    ySideLength = yMax - yMin
    # start with a minimum of 2 points per side
    u = v = x = y = 2

    # add points to the side with the widest spacing until we exhaust the points available
    while (u * v) <= maxSamplePoints:
        x = u
        y = v
        if (xSideLength / x) > (ySideLength / y):
            u += 1
        else:
            v += 1
    return (x, y)

def splitIntArgs(intArgs):
  return [int(val) for val in intArgs.split(':')]

# Process arguments
parsedArgs = parser.parse_args()
xMin, xMax = splitIntArgs(parsedArgs.x_extents)
yMin, yMax = splitIntArgs(parsedArgs.y_extents)
xPoints = 0
yPoints = 0
maxSamplePoints = parsedArgs.max_points
if parsedArgs.num_points is not None:
    xPoints, yPoints = splitIntArgs(parsedArgs.num_points)
else :
    # if the number of points was unspecified, select the optimal values
    xPoints, yPoints = selectMeshInterval(xMin, xMax, yMin, yMax, maxSamplePoints)
maxSamplePoints = parsedArgs.max_points
isDsfPathMode = parsedArgs.dsf_path_mode
probeLogPath = dsfPath(parsedArgs.probe_log_file, isDsfPathMode)
heightmapPath = dsfPath(parsedArgs.heightmap_file, isDsfPathMode)

# Matches: Mesh Point: X20.485 Y-13 Z0.025
probePointPattern = re.compile('Mesh Point: X(-?\\d*\\.?\\d*) Y(-?\\d*\\.?\\d*) Z(-?\\d*\\.?\\d*)')
# read input file and extract probed coordinates from matching lines
def parseProbedPoints() -> {}:
    # open the bed sample file and read all lines
    lines = []
    with open(probeLogPath, 'r') as bedFile:
        lines = bedFile.readlines()

    probedPoints = {}

    for line in lines:
        match = probePointPattern.search(line)
        if match != None:
            captured = match.groups()
            xyCoordinate = (float(captured[0]), float(captured[1]))
            zOffset = float(captured[2])

            # group points with identical X/Y coordinates so the Z values can be averaged in the next step
            if xyCoordinate not in probedPoints:
                probedPoints[xyCoordinate] = [];

            probedPoints[xyCoordinate].append(zOffset)

    return probedPoints

# Average Z values and produce the 3-array x/y/z structure required for the RBF
def averageZOffset(probedPoints):
    x = []
    y = []
    z = []

    for xyCoordinate, zOffsets in probedPoints.items():
        x.append(xyCoordinate[0])
        y.append(xyCoordinate[1])
        z.append(sum(zOffsets) / len(zOffsets))
    
    return (x, y, z)

# Return a mesh grid of x/y values that RRF expects to have been probed in the heightmap
def buildMeshPoints():
    minval = -1
    maxval =  1
    return np.meshgrid(np.linspace(xMin, xMax, xPoints), np.linspace(yMin, yMax, yPoints))

# Use RBF and mesh grid to compute the Z values at all heightmap sample points
def upsampleBedMesh(averagedPoints):
    # Use Radial Basis Functions (RBF) to interpolate the bed surface from random sample points
    # To see how RBF compare to other techniques: https://stackoverflow.com/questions/37872171/how-can-i-perform-two-dimensional-interpolation-using-scipy
    # Reference: https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.Rbf.html
    rbfInterpolator = Rbf(averagedPoints[0], averagedPoints[1], averagedPoints[2], smooth=0)
    return rbfInterpolator(*buildMeshPoints())   # sample the interpolated surface for the final bed mesh

# Write a RRF compatible heightmap.csv file
def writeHeightmap(upsampledBedMesh):
    # this header line is necessary to convince RRF that the file is genuine
    str_out = 'RepRapFirmware height map file v2 generated at '
    str_out += datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    str_out += '\n'
    # this line also needs to be exactly as-is to pass the parser
    str_out += 'xmin,xmax,ymin,ymax,radius,xspacing,yspacing,xnum,ynum\n'
    # numbers here seem to be rounded to 2 decimal places
    settingsLine = [xMin, xMax, yMin, yMax, -1.00, round((xMax - xMin) / (xPoints - 1), 2), round((yMax - yMin) / (yPoints - 1), 2), xPoints, yPoints]
    str_out += ','.join(str(val) for val in settingsLine)
    str_out += '\n'

    # write one line in the settings file for row of points
    for row in upsampledBedMesh:
        #note: these lines start with a space in the RRF code, which appears to be a bug, but leaving it out still works
        # Z-values seem to be rounded to 3 decimal places
        str_out += ', '.join(str(round(val, 3)) for val in row)
        str_out += '\n'

    print(str_out)

    # create the heightmap file & write contents
    with open(heightmapPath, 'w') as meshFile:
        meshFile.write(str_out)
    
    # allow all users to read/write/execute the file, so DSF can have access
    os.chmod(heightmapPath, 0o777)

# Preform processing of probe data to heightmap file
writeHeightmap(upsampleBedMesh(averageZOffset(parseProbedPoints())))
