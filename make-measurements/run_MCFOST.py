import sys
import os
import subprocess
import pickle
import time
import numpy as np
from astropy.io import fits
from write_MCFOST_parafile import *
from physics import *
import matplotlib.pyplot as plt
# HI LUCI
def build_parameters(free_parameters, default_parameters_filename):
    ''' Start with the default parameters as specified in default_parameters,
    and override the values of the parameters in free_parameters
    '''

    # load in the default parameter file
    print(default_parameters_filename)
    dp = __import__(default_parameters_filename)

    parameters = dp.Default_parameters()

    for para, new_value in free_parameters.items():

        # check to see that the parameter we want to override exists
        # additional parameters: asp (aspect ratio)
        if para not in list(parameters.__dict__.keys()) + ["asp", "spots", "rhoexp"]:
            sys.exit("...\nERROR in run_MCFOST.\nAttempted to specify a parameter ({}). Parameter does not exist in default_parameters.\nCheck that all new parameters have been spelt correctly.\n...".format(para))
        else:
            # override the old parameter with the new value
            parameters.__dict__[para] = str(new_value)

    return parameters


def make_dust_spot_multiplier(grid, spot):

    # Theta and phi are the coordinates of the spot amp and sigma are parameters of the gaussian
    amp, sigma, theta, phi = spot
    theta = np.radians(theta)
    phi = np.radians(phi)

    r_coords = grid[0].data[0,:,:,:]
    z_coords = grid[0].data[1,:,:,:]
    theta_coords = grid[0].data[2,:,:,:]

    # make a distance grid (psi)
    # calculate the angle phi
    phi_coords = np.arctan(r_coords/z_coords)
    z_mask = np.pi * (z_coords < 0).astype(int)
    phi_coords += z_mask

    cos_psi = np.sin(phi_coords) * np.sin(phi) * np.cos(theta_coords - theta) + np.cos(phi_coords) * np.cos(phi)
    psi_coords = np.arccos(cos_psi)

    # set up the gaussian
    exponent = -np.power(psi_coords, 2) / (2 * sigma)
    gaussian = amp * np.exp(exponent) + 1

    gaussian = np.maximum(gaussian, 0)

    return gaussian

def make_density_file(parameters, free_parameters, MCFOST_path):

    # load grid
    fn_grid = "{}data_disk/grid.fits.gz".format(MCFOST_path)
    hdul_grid = fits.open(fn_grid)

    r = hdul_grid[0].data[0,:,:,:]
    z = hdul_grid[0].data[1,:,:,:]

    if "asp" in free_parameters.keys():
        theta = hdul_grid[0].data[2,:,:,:]

        x =  r * abs(np.cos(theta))
        y =  r * abs(np.sin(theta))

    r = np.power(np.power(r, 2) + np.power(z, 2), 0.5)

    if "rhoexp" in free_parameters.keys():
        r = np.power(r, free_parameters["rhoexp"])
    else:
        r = np.power(r, -2)

    # deal with the aspect ratio
    if "asp" in free_parameters.keys():


        # Rin: inner semi-minor axis (z)
        # rx: inner semi-major axis (x, y)

        # Rz: outer semi-minor axis (z)
        # Rout : outer semi-major axis (x, y)

        Rin = float(parameters.Rin)
        Rout = float(parameters.Rout)

        rx = Rin / free_parameters["asp"]
        Rz = free_parameters["asp"] * Rout

        inner = np.add(np.add(np.power(x/rx, 2), np.power(y/rx, 2)), np.power(z/Rin, 2))
        outer = np.add(np.add(np.power(x/Rout, 2), np.power(y/Rout, 2)), np.power(z/Rz, 2))

        mask = np.invert(np.add(inner < 1, outer > 1))
        mask = mask.astype(int)

        r = np.multiply(r, mask)

    if "spots" in free_parameters.keys():
        for spot in free_parameters["spots"]:
            gaussian = make_dust_spot_multiplier(hdul_grid, spot)
            r = np.multiply(r, gaussian)

    r = np.expand_dims(r, axis=0)

    # load grain sizes
    fn_grains = "{}data_disk/grain_sizes.fits.gz".format(MCFOST_path)
    hdul_grains = fits.open(fn_grains)
    grains = hdul_grains[0].data

    # load grain masses
    hdu1 = fits.PrimaryHDU(r)
    density_file = fits.HDUList([hdu1])
    density_file[0].header["read_n_a"] = 0

    density_file.writeto(MCFOST_path + "density.fits", overwrite=True)


def run_MCFOST(wavelength, parameters, free_parameters, MCFOST_path, file_name = "star.para", verbose = False, scale_fact = False):
    ''' Runs MCFOST. It needs a wavelength and a parameter file.
    It will output a data_th file and a data_<wavelength> file.'''

    # delete previous files
    subprocess.call("rm -r data_*", shell = True)
    start = time.time()

    basic_cmd = ["mcfost", MCFOST_path + file_name]
    grid_cmd = basic_cmd + ["-output_density_grid"]
    if int(parameters.n_az) > 1:
        grid_cmd += ["-3D"]
    rt_cmd = basic_cmd + ["-img", str(wavelength), "-rt"]
    # I believe the following flags are equivalent:
        # -output_density_grid
        # -disk_struct
        # -density_struct

    rt_cmd += ["-density_file", MCFOST_path + "density.fits"]
    if int(parameters.n_az) > 1:
        rt_cmd += ["-3D"]

    if verbose:
        subprocess.call(basic_cmd)
        subprocess.call(grid_cmd)
        make_density_file(parameters, free_parameters, MCFOST_path)
        subprocess.call(rt_cmd)
    else:
        subprocess.call(basic_cmd, stdout = subprocess.PIPE)
        subprocess.call(grid_cmd, stdout=subprocess.PIPE)
        subprocess.call(rt_cmd, stdout = subprocess.PIPE)

    # subprocess.call(["scp", "-rp", "data_th", MCFOST_path], stdout=subprocess.PIPE)
    # subprocess.call(["rm", "-fr", "data_th"], stdout=subprocess.PIPE)
    #
    # subprocess.call(["scp", "-rp", "data_"+ str(wavelength), MCFOST_path], stdout=subprocess.PIPE)
    # subprocess.call(["rm", "-fr", "data_" + str(wavelength)], stdout=subprocess.PIPE)
    # subprocess.call(["mv", "_dust_prop_th.tmp", MCFOST_path], stdout=subprocess.PIPE)
    # subprocess.Popen("mv star_parameters " + MCFOST_path, shell = True)
    #
    # subprocess.call(["scp", "-rp", "data_disk", MCFOST_path], stdout=subprocess.PIPE)
    # subprocess.call(["rm", "-fr", "data_disk"], stdout=subprocess.PIPE)

    finish = time.time()
    total_time = finish - start
    return total_time

def load_data(MCFOST_path, data_dir, fits_file):
    ''' This will open data_<wavelength> and load the fits file in data. File is stored is the same directory where the code is run. '''

    # if the data hasn't been loaded from a previous run, we need to unzip the files
    print(MCFOST_path + data_dir + fits_file)
    try:
        f = open(MCFOST_path + data_dir + fits_file)
        f.close()
        subprocess.call(['scp', MCFOST_path + data_dir + fits_file, MCFOST_path + fits_file])
    except OSError as e:
        print("...\nERROR in load_data.\nAttempted to open " + fits_file[:-3] + ".\nFile does not exist.\nCheck that parameters are valid.\n...")
        return None

    subprocess.call(['gunzip', '-f', MCFOST_path + fits_file])
    data = fits.getdata(MCFOST_path + fits_file[:-3])   # -3 gets rid of .gz

    return data

def check_constraints(parameters):

    if int(parameters.grid_nx) != int(parameters.grid_ny):
        print("...\nWARNING: The grid is not square.\nCalculations may not be accurate\n...")

    if int(parameters.grid_nx) % 2 != 1 or int(parameters.grid_ny) % 2 != 1:
        print("...\nWARNING: Image should be an odd number of pixels across so that the star is centered.\nCalculations may not be accurate\n...")

    # Check constraints: ie star is valid
    epsilon = 0.015	# small buffer
    radius_m = AU_to_m(sr_to_AU(float(parameters.radius)))
    rin_m = AU_to_m(float(parameters.Rin))
    rout_m = AU_to_m(float(parameters.Rout))

    if radius_m >= rin_m:
        print("""...
ERROR: stellar radius is larger than the inner radius of the dust shell.
stellar radius (m): {}
inner radius (m): {}
...""".format(radius_m, rin_m))


    if rin_m >= rout_m:
        print("""...
ERROR: inner radius of the dust shell is greater than the outer radius of the dust shell.
inner radius (AU): {}
outer radius (AU): {}
...""".format(parameters.Rin, parameters.Rout))



def build_model(free_parameters, default_parameters_filename, wavelength, MCFOST_path, verbose = False, scale_fact = False, density_file = False):
    ''' Free_parameters as a dictionary.
    The wavelength must be a string, and the MCFOST_path is the location
    where everything will be created.

    This function returns the contents of the fits file stored in arrays'''

    # obtain a dictionary containing all the parameter values required to write a parameter file for MCFOST
    os.chdir(MCFOST_path)
    parameters = build_parameters(free_parameters, default_parameters_filename)

    pickle.dump(parameters, open("star_parameters", "wb"))

    # constraints are checked here so that we can check that default values are valid, not just the free_parameters
    check_constraints(parameters)

    # write the parameter file
    print("Writing parameter file...")
    write_MCFOST_parafile(parameters, MCFOST_path)


    # run MCFOST and produce a folder with the data_th and data_<wavelength> files
    print("Deleting old data files...")
    print("Running MCFOST...")
    time = run_MCFOST(wavelength, parameters, free_parameters, MCFOST_path, verbose = verbose)

    print("Loading ray tracing data...")
    data = load_data(MCFOST_path, "data_{}/".format(wavelength), 'RT.fits.gz')

    return data, time


