

# Dependencies, compile WISDEM
import os
import numpy as np
from scipy.interpolate import PchipInterpolator
import wisdem.inputs as sch
from wisdem.ccblade.ccblade import CCBlade, CCAirfoil
# import wisdem.ccblade._bem as _bem
from wisdem.commonse.utilities import arc_length
# from wisdem.commonse.csystem import DirectionVector


# Load wind turbine geometry yaml
run_dir = os.path.dirname( os.path.realpath(__file__) ) + os.sep
fname_input_wt = os.path.join(run_dir, "IEA-15-240-RWT.yaml")
wt_init = sch.load_geometry_yaml(fname_input_wt)

# Set CCBlade flags
tiploss = True # Tip loss model True/False
hubloss = True # Hub loss model, True/False
wakerotation = True # Wake rotation, True/False
usecd = True # Use drag coefficient within BEMT, True/False

# Set environmental conditions, these must be arrays except for yaw
# Uhub = np.array([3.        ,  4.22088938,  5.22742206,  6.0056444 ,  6.54476783,
#         6.83731843,  6.87924056,  7.08852808,  7.54612388,  8.24568427,
#         9.17751118, 10.32868661, 10.89987023, 13.22242806, 14.9248779 ,
#        16.76700002, 18.72325693, 20.76652887, 22.86848978, 25. ]) # m/s
# Omega_rpm = np.array([5.        , 5.        , 5.        , 5.        , 5.        ,
#        5.        , 5.        , 5.03607599, 5.36117694, 5.8581827 ,
#        6.52020323, 7.33806089, 7.49924093, 7.49924093, 7.49924093,
#        7.49924093, 7.49924093, 7.49924093, 7.49924093, 7.49924093]) # rpm
# pitch_deg = np.array([3.8770757 ,  3.58018171,  2.63824381,  1.62701287,  0.81082407,
#         0.32645039,  0.25491167,  0.        ,  0.        ,  0.        ,
#         0.        ,  0.        ,  0.        ,  8.14543778, 11.02202702,
#        13.61534727, 16.04700926, 18.3599078 , 20.5677456 , 22.67114154]) # deg

Uhub = np.array([9.])
Omega_rpm = np.array([6.39408964])
pitch_deg = np.array([0.])

yaw = 0.

# Set discretization parameters
nSector = 4 # [-] - number of equally spaced azimuthal positions where CCBlade should be interrogated. The results are averaged across the n positions. 4 is a good first guess
n_span = 30 # [-] - number of blade stations along span
grid = np.linspace(0., 1., n_span) # equally spaced grid along blade span, root=0 tip=1
n_aoa = 200 # [-] - number of angles of attack to discretize airfoil polars



##########################################
#  No need to change anything after this #
##########################################

# Conversion of the yaml inputs into CCBlade inputs
Rhub = 0.5 * wt_init["components"]["hub"]["diameter"] # [m] - hub radius
precone = np.rad2deg(wt_init["components"]["hub"]["cone_angle"]) # [deg] - rotor precone angle
tilt = np.rad2deg(wt_init["components"]["nacelle"]["drivetrain"]["uptilt"]) # [deg] -  nacelle uptilt angle
B = wt_init["assembly"]["number_of_blades"] # [-] - number of blades
blade = wt_init["components"]["blade"]["outer_shape_bem"]

# Blade quantities
rotor_diameter = wt_init["assembly"]["rotor_diameter"]
blade_ref_axis = np.zeros((n_span, 3))
blade_ref_axis[:, 0] = np.interp(grid, blade["reference_axis"]["x"]["grid"], blade["reference_axis"]["x"]["values"])
blade_ref_axis[:, 1] = np.interp(grid, blade["reference_axis"]["y"]["grid"], blade["reference_axis"]["y"]["values"])
blade_ref_axis[:, 2] = np.interp(grid, blade["reference_axis"]["z"]["grid"], blade["reference_axis"]["z"]["values"])
if rotor_diameter != 0.0:
    blade_ref_axis[:, 2] = (blade_ref_axis[:, 2] * rotor_diameter / ((arc_length(blade_ref_axis)[-1] + Rhub) * 2.0))
r = blade_ref_axis[1:-1, 2] + Rhub # [m] - radial position along straight blade pitch axis
Rtip = blade_ref_axis[-1, 2] + Rhub
chord = np.interp(grid[1:-1], blade["chord"]["grid"], blade["chord"]["values"]) # [m] - blade chord distributed along r
theta = np.rad2deg(np.interp(grid[1:-1], blade["twist"]["grid"], blade["twist"]["values"])) # [deg] - blade twist distributed along r
precurve = blade_ref_axis[1:-1, 0] # [m] - blade prebend distributed along r, usually negative for upwind rotors
precurveTip = blade_ref_axis[-1, 0] # [m] - prebend at blade tip
presweep = blade_ref_axis[1:-1, 1] # [m] - blade presweep distributed along r, usually positive
presweepTip = blade_ref_axis[-1, 1] # [m] - presweep at blade tip

# Hub height
if wt_init["assembly"]["hub_height"] != 0.0:
    hub_height = wt_init["assembly"]["hub_height"]
else:
    hub_height = wt_init["components"]["tower"]["outer_shape_bem"]["reference_axis"]["z"]["values"][-1] + wt_init["components"]["nacelle"]["drivetrain"]["distance_tt_hub"]

# Atmospheric boundary layer data
rho = wt_init['environment']["air_density"] # [kg/m3] - density of air
mu = wt_init['environment']["air_dyn_viscosity"] # [kg/(ms)] - dynamic viscosity of air
shearExp = wt_init['environment']["shear_exp"] # [-] - shear exponent

# Airfoil data


n_af = len(wt_init["airfoils"])
af_used = blade["airfoil_position"]["labels"]
af_position = blade["airfoil_position"]["grid"]
n_af_span = len(af_used)
if n_aoa / 4.0 == int(n_aoa / 4.0):
    # One fourth of the angles of attack from -pi to -pi/6, half between -pi/6 to pi/6, and one fourth from pi/6 to pi
    aoa = np.unique(np.hstack([np.linspace(-np.pi, -np.pi / 6.0, int(n_aoa / 4.0 + 1)),np.linspace(-np.pi / 6.0,np.pi / 6.0,int(n_aoa / 2.0),),np.linspace(np.pi / 6.0, np.pi, int(n_aoa / 4.0 + 1))]))
else:
    aoa = np.linspace(-np.pi, np.pi, n_aoa)
    print(
        "WARNING: If you like a grid of angles of attack more refined between +- 30 deg, please choose a n_aoa in the analysis option input file that is a multiple of 4. The current value of "
        + str(n_aoa)
        + " is not a multiple of 4 and an equally spaced grid is adopted."
    )

Re_all = []
for i in range(n_af):
    for j in range(len(wt_init["airfoils"][i]["polars"])):
        Re_all.append(wt_init["airfoils"][i]["polars"][j]["re"])
n_Re = len(np.unique(Re_all))

n_tab = 1

af_name = n_af * [""]
r_thick = np.zeros(n_af)
Re_all = []
for i in range(n_af):
    af_name[i] = wt_init["airfoils"][i]["name"]
    r_thick[i] = wt_init["airfoils"][i]["relative_thickness"]
    for j in range(len(wt_init["airfoils"][i]["polars"])):
        Re_all.append(wt_init["airfoils"][i]["polars"][j]["re"])

Re = np.array(sorted(np.unique(Re_all)))

cl = np.zeros((n_af, n_aoa, n_Re, n_tab))
cd = np.zeros((n_af, n_aoa, n_Re, n_tab))
cm = np.zeros((n_af, n_aoa, n_Re, n_tab))

# Interp cl-cd-cm along predefined grid of angle of attack
for i in range(n_af):
    n_Re_i = len(wt_init["airfoils"][i]["polars"])
    Re_j = np.zeros(n_Re_i)
    j_Re = np.zeros(n_Re_i, dtype=int)
    for j in range(n_Re_i):
        Re_j[j] = wt_init["airfoils"][i]["polars"][j]["re"]
        j_Re[j] = np.argmin(abs(Re - Re_j[j]))
        cl[i, :, j_Re[j], 0] = np.interp(
            aoa, wt_init["airfoils"][i]["polars"][j]["c_l"]["grid"], wt_init["airfoils"][i]["polars"][j]["c_l"]["values"]
        )
        cd[i, :, j_Re[j], 0] = np.interp(
            aoa, wt_init["airfoils"][i]["polars"][j]["c_d"]["grid"], wt_init["airfoils"][i]["polars"][j]["c_d"]["values"]
        )
        cm[i, :, j_Re[j], 0] = np.interp(
            aoa, wt_init["airfoils"][i]["polars"][j]["c_m"]["grid"], wt_init["airfoils"][i]["polars"][j]["c_m"]["values"]
        )

        if abs(cl[i, 0, j, 0] - cl[i, -1, j, 0]) > 1.0e-5:
            cl[i, 0, j, 0] = cl[i, -1, j, 0]
            print(
                "WARNING: Airfoil "
                + af_name[i]
                + " has the lift coefficient at Re "
                + str(Re_j[j])
                + " different between + and - pi rad. This is fixed automatically, but please check the input data."
            )
        if abs(cd[i, 0, j, 0] - cd[i, -1, j, 0]) > 1.0e-5:
            cd[i, 0, j, 0] = cd[i, -1, j, 0]
            print(
                "WARNING: Airfoil "
                + af_name[i]
                + " has the drag coefficient at Re "
                + str(Re_j[j])
                + " different between + and - pi rad. This is fixed automatically, but please check the input data."
            )
        if abs(cm[i, 0, j, 0] - cm[i, -1, j, 0]) > 1.0e-5:
            cm[i, 0, j, 0] = cm[i, -1, j, 0]
            print(
                "WARNING: Airfoil "
                + af_name[i]
                + " has the moment coefficient at Re "
                + str(Re_j[j])
                + " different between + and - pi rad. This is fixed automatically, but please check the input data."
            )

    # Re-interpolate cl-cd-cm along the Re dimension if less than n_Re were provided in the input yaml (common condition)
    for l in range(n_aoa):
        cl[i, l, :, 0] = np.interp(Re, Re_j, cl[i, l, j_Re, 0])
        cd[i, l, :, 0] = np.interp(Re, Re_j, cd[i, l, j_Re, 0])
        cm[i, l, :, 0] = np.interp(Re, Re_j, cm[i, l, j_Re, 0])

# Interpolate along blade span using a pchip on relative thickness
r_thick_used = np.zeros(n_af_span)
cl_used = np.zeros((n_af_span, n_aoa, n_Re, n_tab))
cl_interp = np.zeros((n_span, n_aoa, n_Re, n_tab))
cd_used = np.zeros((n_af_span, n_aoa, n_Re, n_tab))
cd_interp = np.zeros((n_span, n_aoa, n_Re, n_tab))
cm_used = np.zeros((n_af_span, n_aoa, n_Re, n_tab))
cm_interp = np.zeros((n_span, n_aoa, n_Re, n_tab))

for i in range(n_af_span):
    for j in range(n_af):
        if af_used[i] == af_name[j]:
            r_thick_used[i] = r_thick[j]
            cl_used[i, :, :, :] = cl[j, :, :, :]
            cd_used[i, :, :, :] = cd[j, :, :, :]
            cm_used[i, :, :, :] = cm[j, :, :, :]
            break

# Pchip does have an associated derivative method built-in:
# https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.PchipInterpolator.derivative.html#scipy.interpolate.PchipInterpolator.derivative
spline = PchipInterpolator
rthick_spline = spline(af_position, r_thick_used)
r_thick_interp = rthick_spline(grid[1:-1])


# Spanwise interpolation of the airfoil polars with a pchip
r_thick_unique, indices = np.unique(r_thick_used, return_index=True)
cl_spline = spline(r_thick_unique, cl_used[indices, :, :, :])
cl_interp = np.flip(cl_spline(np.flip(r_thick_interp)), axis=0)
cd_spline = spline(r_thick_unique, cd_used[indices, :, :, :])
cd_interp = np.flip(cd_spline(np.flip(r_thick_interp)), axis=0)
cm_spline = spline(r_thick_unique, cm_used[indices, :, :, :])
cm_interp = np.flip(cm_spline(np.flip(r_thick_interp)), axis=0)


af = [None] * (n_span - 2)
for i in range(n_span - 2):
    af[i] = CCAirfoil(np.rad2deg(aoa), Re, cl_interp[i, :, :, 0], cd_interp[i, :, :, 0], cm_interp[i, :, :, 0])

ccblade = CCBlade(
    r,
    chord,
    theta,
    af,
    Rhub,
    Rtip,
    B,
    rho,
    mu,
    precone,
    tilt,
    yaw,
    shearExp,
    hub_height,
    nSector,
    precurve,
    precurveTip,
    tiploss=tiploss,
    hubloss=hubloss,
    wakerotation=wakerotation,
    usecd=usecd,
    derivatives=False,
)

outputs = {}

loads, derivs = ccblade.distributedAeroLoads(Uhub, Omega_rpm, pitch_deg, 0.)


import matplotlib.pyplot as plt
plt.plot(r, loads['a'])
plt.show()

loads, derivs = ccblade.evaluate(Uhub, Omega_rpm, pitch_deg, coefficients=True)

print(loads['CP'])
print(loads['P'])