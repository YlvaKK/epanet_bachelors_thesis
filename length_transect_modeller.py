import sys
import argparse
from epanet import toolkit as et
import epanet_actions
from csv_writer import CSVWriter

output_file = 'training_data.csv'
LEAK_COEFF = 0.1
use_elev = True


def main():
    args = parse()

    # this bit creates the project, but can certainly be improved
    # and moved partially to epanet_actions
    ph = et.createproject()
    project = epanet_actions.ProjectActions(ph, use_elev)

    # could probably be called in project.__init__ instead
    project.initialize_subsys(args)

    project.add_leakage_suite()
    results = project.move_one_leak_along_transect(leak_base=LEAK_COEFF, iterations=args.iter)
    write_to_csv(results)


# parses all input arguments, all have defaults except the reports
def parse():
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

    args = parser.parse_args()
    return args


def write_to_csv(results):
    writer = CSVWriter(output_file)
    writer.write_lines(results)
    writer.close()


if __name__ == "__main__":
    sys.exit(main())
