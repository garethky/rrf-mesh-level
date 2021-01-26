# rrf-mesh-level
A mesh bed leveling utility for Rep Rap Firmware/DSF that allows arbitrary bed probing.

## What does this do?
If you have a Duet, an inductive probe and a magnetic bed with swappable build plates. You have probably discovered that `G29` mesh bed probing values have to be selected very carefully not to get a false reading from any of those magnets. This script was built to solve that problem.

* Sample as many points on your bed as you like in any location you want. No limits on the point spacing or pattern. Points can be repeatedly probed to average sensor jitter.
* Log those points to a file directly from GCode
* Submit the log file to mesh-level.py for processing
* mesh-level.py outputs a RRF compatible `heightmap.csv` file that you can then load and use for printing with `G29 S1`
* You can automate all of this from inside `bed.g` with [execonmcode](https://github.com/wilriker/execonmcode) and a single line of GCode.

## How
mesh-level.py uses something called Radial Basis Functions (RBF) to create a virtual model of your bed. Then, in software, it probed that model at the same points that a regular `G29` probing routine would have done and outputs the result to heightmap.csv.

The RBF technique produces a high quality bed model based on your sample points. It is interpolated without smoothing; meaning the model faithfully pases through all of the sample points exactly as you recorded them. The RBF model is generally of higher quality than an equivalent linear interpolation. As such mesh-level.py samples the final heightmap using as many points as possible (up to the duets max of 441) to minimize linear interpolation error when the printer uses the heightmap.

## Help
The scripts behavior can be customized with a number of options:

```
% python mesh-level.py -h

usage: mesh-level.py [-h] -X X_EXTENTS -Y Y_EXTENTS [-L POINTS_FILE] [-H MESH_FILE] [-P NUM_POINTS] [-M MAX_POINTS] [-dsf]

Process a bed probing log and generate a heightmap.csv

optional arguments:
  -h, --help            show this help message and exit
  -X X_EXTENTS, --x-extents X_EXTENTS
                        Minimum and maximum X coordinates of the final reported grid, separated by ':'. E.g. -X -10:200. This is required.
  -Y Y_EXTENTS, --y-extents Y_EXTENTS
                        Minimum and maximum Y coordinates of the final reported grid, separated by ':'. E.g. -Y 3:305. This is required.
  -L POINTS_FILE, --probe-log-file POINTS_FILE
                        The path to the probed points log file, defaults to meshbedprobe.log
  -H MESH_FILE, --heightmap-file MESH_FILE
                        The path to save the heightmap, defaults to heightmap.csv
  -P NUM_POINTS, --num-points NUM_POINTS
                        Number of evenly spaced points to sample in the X and Y axis directions, separated by ':'. E.g. -P 21:21. Optional, --max-points is used if this is omitted.
  -M MAX_POINTS, --max-points MAX_POINTS
                        The maximum number of points that can be sampled in the heightmap file. The optimal sample point spacing is determined from this value if --num-points is omitted. Optional, defaults to 441.
  -dsf, --dsf-path-mode
                        Enable DSF path compatibility mode. Treats file paths as M98 would in RRF. The script assumes the working directory is the root of the virtual SD card.
```

Only the -X and -Y options are required
```
python mesh-level.py -X 0:300 -Y 0:200
```

This uses the defaults for the probe log file and the heightmap output. The bed is defined as 300 x 200 and the script will determine automatically that a 25x17 point mesh is the optimal sample density for the heightmap.

## Dependencies
This script was intended to run from a Single Board Computer (SBC) connected to the Duet 3 board.

You will need NumPy and SciPy. You can get both on Raspberry Pi with 

```
sudo apt-get install python3-scipy
```

You will also need [execonmcode](https://github.com/wilriker/execonmcode) to invoke this script from GCode in your printer.

## Samples

This project comes with a set of samples in the /samples directory to help you with your probing setup. Every printer, bed, SBC and setup are different so you will have to put a solution together that meets your needs. Hopefully some of these are helpful:

[generate-grid-gcode.py](samples/generate-grid-gcode.py) - Generating all of the GCode to probe a bed can be tedious and error prone. This is an example python script that generates the gcode based on arrays of x/y coordinates that you want to probe. The coordinates are mirrored by the code about the center of the bed on the X axis and rows of similar probing points can be repeated. This saves on having to write down every x/y point pair for the whole bed.

[bed.g](samples/bed.g) - A samples bed.g macro file that performs mesh probing and saves the results to a log file. The probing operations were generated with [generate-grid-gcode.py](samples/generate-grid-gcode.py).

[probe-point.g](samples/probe-point.g) - A sample macro for probing an individual point using information available in the Duet software model. This shows how to probe multiple times using the speeds and heights defined in the model.

[meshbedprobe.log](samples/meshbedprobe.log) - A sample log from a run of bed.g that you can use to dry run the mesh-level.py script.

[execonmcode7029.service](samples/execonmcode7029.service) - A sample service definition file for [execonmcode](https://github.com/wilriker/execonmcode). This helps you pass the required parameters to mesh-level.py from the `M7029 X"0:300" Y"0:200"` custom MCode in `bed.g`. See execonmcode's documentatin for more info on setting this up.

## Performance
I have tested this on Pi 3B+ and it runs in about a second.

When running the probing routines you may find that SPI communication between the SBC and the Duet is a bottleneck. Raising the SPI frequency to 16Mhz can greatly improve SPI performance.

You may also find that logging can slow down execution. In this case upgrading to a faster SD card in the SBC improves performance.

## Resources
* Thread on the Duet Forums (TK)
* https://stackoverflow.com/questions/37872171/how-can-i-perform-two-dimensional-interpolation-using-scipy A great writeup (with pictures) on using Radial Basis Functions with Python: 
