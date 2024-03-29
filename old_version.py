import sys
import argparse
from epanet import toolkit as epanet_toolkit
import dcritsim
import math

output_file = 'training_data.csv'
LEAK = "leakage_node"
UPSTREAM_PIPE = "upstream_pipe"
DOWNSTREAM_PIPE = "downstream_pipe"
LEAK_COEFF = 0.5
# LENGTH_STEP = 100
# PIPE_LENGTH = 1000
PIPE_DIAM = 100
PIPE_ROUGHNESS = 120
PIPE_MLOSS = 0

output = []
upstream_node_pressure = []
downstream_node_pressure = []
upstream_pipe_flow = []
downstream_pipe_flow = []
leak_elevation_value = []


def main():
    print("INFO: in main")
    # parse all arguments
    parser = argparse.ArgumentParser(description='Run an EPANET simulation.')
    parser.add_argument('input_filename', nargs='?', default='net1.inp',
                        help='An EPANET input file describing the system.')
    parser.add_argument('report_filename', nargs='?', default='', help='Report log file from the simulation run.')
    parser.add_argument('binary_filename', nargs='?', default='', help='Hydraulic analysis results file (binary).')
    parser.add_argument('--hstep', metavar='seconds', type=int, default=3600,
                        help='Hydraulic time step (default 3600s=1h).')
    parser.add_argument('--pipe', metavar='index', type=int, default=2, help='index of pipe to look at (default 2).')
    parser.add_argument('--iter', metavar='number of leakage sizes', type=int, default=1,
                        help='number of leak size iterations (default 1)')
    # initialize epanet sim project from dcritsim
    epanet = dcritsim.epanetwrap.DcritEPANET()
    global ph
    ph = epanet.get_ph()

    # initialize subsys
    args = parser.parse_args()
    global pipe_index
    pipe_index = args.pipe
    leak_iterations = args.iter

    # unpack args and initialize water distribution network
    initialize_subsys(args)

    add_leak()  # replaces a pipe with a leakage suit
    model_leak_size_iter(leak_iterations)  # moves leak along pipe and records pressure and flow
    write_to_csv(leak_iterations)  # outputs data to csv file


def initialize_subsys(args):
    epanet_toolkit.open(ph, args.input_filename, args.report_filename, args.binary_filename)
    epanet_toolkit.settimeparam(ph, epanet_toolkit.HYDSTEP, args.hstep)
    epanet_toolkit.setstatusreport(ph, epanet_toolkit.NORMAL_REPORT)
    check_units()


def check_units():
    global f_unit
    global p_unit
    global l_unit

    flow_units = epanet_toolkit.getflowunits(ph)
    if (flow_units != epanet_toolkit.GPM):
        raise Exception("input file must use GPM as flow unit")
    if (flow_units >= 0 and flow_units < 5):
        epanet_toolkit.setflowunits(ph, epanet_toolkit.GPM)
        f_unit, p_unit, l_unit = 'gpm', 'psi', 'foot'
    elif (flow_units >= 5 and flow_units < 10):
        epanet_toolkit.setflowunits(ph, epanet_toolkit.LPS)
        f_unit, p_unit, l_unit = 'lps', 'm of head', 'm'


def add_leak():
    global pipe_length  # used everywhere
    global pipe_diam
    global pipe_rough
    global pipe_mloss

    global upstream_node_elevation
    global downstream_node_elevation

    global angle

    global leakage_node_index  # used in add_leak and move_leak
    global upstream_node_index  # used in add_leak and move_leak
    global downstream_node_index  # same
    global upstream_pipe_index  # same
    global downstream_pipe_index  # same

    # get index of nodes surrounding original pipe
    upstream_node_index, downstream_node_index = epanet_toolkit.getlinknodes(ph, pipe_index)

    # save useful global variables
    pipe_length = epanet_toolkit.getlinkvalue(ph, pipe_index, epanet_toolkit.LENGTH)
    pipe_diam = epanet_toolkit.getlinkvalue(ph, pipe_index, epanet_toolkit.DIAMETER)
    pipe_rough = epanet_toolkit.getlinkvalue(ph, pipe_index, epanet_toolkit.ROUGHNESS)
    pipe_mloss = epanet_toolkit.getlinkvalue(ph, pipe_index, epanet_toolkit.MINORLOSS)
    angle, upstream_node_elevation = get_pipe_angle(upstream_node_index, downstream_node_index)

    # remove original pipe
    epanet_toolkit.deletelink(ph, pipe_index, actionCode=epanet_toolkit.UNCONDITIONAL)

    # add lekage node (as of yet unmoored)
    leakage_node_index = epanet_toolkit.addnode(ph, LEAK, nodeType=epanet_toolkit.JUNCTION)

    # create new pipes and connect them to leakage node, surrounding nodes
    upstream_pipe_index = make_pipe(UPSTREAM_PIPE, epanet_toolkit.getnodeid(ph, upstream_node_index), LEAK)
    downstream_pipe_index = make_pipe(DOWNSTREAM_PIPE, LEAK, epanet_toolkit.getnodeid(ph, downstream_node_index))


def make_pipe(id, node1, node2):
    pipe_index = epanet_toolkit.addlink(ph, id, epanet_toolkit.PIPE, node1, node2)
    epanet_toolkit.setpipedata(ph, pipe_index, length=1, diam=pipe_diam, rough=pipe_rough, mloss=pipe_mloss)

    return pipe_index


def model_leak_size_iter(iterations):
    base = LEAK_COEFF
    for i in range(iterations):
        leak_coefficient = base * (i + 1)
        move_leak(leak_coefficient)


def move_leak(leak_coefficient):
    this_upsteam_p = []
    this_downsteam_p = []
    this_upstream_f = []
    this_downstream_f = []
    this_leak_e = []
    for i in range(1, round(pipe_length)):
        # change length of pipes surrounding leak
        epanet_toolkit.setpipedata(ph, upstream_pipe_index, length=i, diam=pipe_diam, rough=pipe_rough,
                                   mloss=pipe_mloss)
        epanet_toolkit.setpipedata(ph, downstream_pipe_index, length=round(pipe_length) - i, diam=pipe_diam,
                                   rough=pipe_rough, mloss=pipe_mloss)

        leak_elevation = calculate_leak_elevation(upstream_node_elevation, angle, i)

        #epanet_toolkit.setnodevalue(ph, leakage_node_index, epanet_toolkit.ELEVATION, leak_elevation)
        epanet_toolkit.setnodevalue(ph, leakage_node_index, epanet_toolkit.EMITTER, leak_coefficient)

        # run simulation
        run_hydraulic_solver()

        # record pressure and flow
        this_upsteam_p.append(epanet_toolkit.getnodevalue(ph, upstream_node_index, property=epanet_toolkit.PRESSURE))
        this_downsteam_p.append(
            epanet_toolkit.getnodevalue(ph, downstream_node_index, property=epanet_toolkit.PRESSURE))
        this_upstream_f.append(epanet_toolkit.getlinkvalue(ph, upstream_pipe_index, property=epanet_toolkit.FLOW))
        this_downstream_f.append(epanet_toolkit.getlinkvalue(ph, downstream_pipe_index, property=epanet_toolkit.FLOW))
        this_leak_e.append(epanet_toolkit.getnodevalue(ph, leakage_node_index, property=epanet_toolkit.ELEVATION))

    upstream_node_pressure.append(this_upsteam_p)
    downstream_node_pressure.append(this_downsteam_p)
    upstream_pipe_flow.append(this_upstream_f)
    downstream_pipe_flow.append(this_downstream_f)
    leak_elevation_value.append(this_leak_e)


def write_to_csv(iterations):
    base_leak = LEAK_COEFF
    f = open('training_data.csv', "w")

    header1 = ""
    header2 = 'leakage_position ({}),'.format(l_unit)
    lines = [''] * (round(pipe_length))

    for i in range(iterations):
        header1 = header1 + 'leak_coeff: %s,,,,,' % (base_leak * (i + 1))
        header2 = header2 + 'upstream_pressure ({0}),downstream_pressure ({0}),upstream_flow ({1}),downstream_flow ({1}),leak_elev ({2}),'.format(
            p_unit, f_unit, l_unit)
        for j in range(round(pipe_length) - 1):
            if (i == 0):
                lines[j] = "%s," % j
            lines[j] = lines[j] + "%s,%s,%s,%s,%s," % (
            upstream_node_pressure[i][j], downstream_node_pressure[i][j], upstream_pipe_flow[i][j],
            downstream_pipe_flow[i][j], leak_elevation_value[i][j])

    header1 = header1[0:len(header1) - 1] + "\n"
    header2 = header2[0:len(header2) - 1] + "\n"
    f.write(header1)
    f.write(header2)

    for i in range(len(lines)):
        lines[i] = lines[i][0:len(lines[i]) - 1]
        if not i == len(lines) - 1:
            lines[i] = lines[i] + "\n"
        f.write(lines[i])


def run_hydraulic_solver():
    epanet_toolkit.openH(ph)
    epanet_toolkit.initH(ph, epanet_toolkit.SAVE)
    epanet_toolkit.solveH(ph)


def get_pipe_angle(upstream_index, downstream_index):
    upstream_node_elevation = epanet_toolkit.getnodevalue(ph, upstream_index, epanet_toolkit.ELEVATION)
    downstream_node_elevation = epanet_toolkit.getnodevalue(ph, downstream_index, epanet_toolkit.ELEVATION)
    elevation_diff = upstream_node_elevation - downstream_node_elevation
    angle = math.asin(elevation_diff / pipe_length)
    return angle, upstream_node_elevation


def calculate_leak_elevation(upper_elevation, angle, length_from_upper):
    elevation_diff_from_upper_elevation = math.sin(angle) * length_from_upper
    return upper_elevation - elevation_diff_from_upper_elevation


if __name__ == "__main__":
    sys.exit(main())
