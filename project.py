import numpy as np
import matplotlib.pyplot as plt
import csv
import datetime as dt
import argparse
import math
from dataclasses import dataclass

@dataclass
class CurrentData:
    time: list
    ia: list
    ib: list
    ic: list

class RelaySpaj:
    '''
    Relay ABB SPAJ class
    '''
    def __init__(self, reference, i_nominal=5, ctr=120, i_pickup=0.5, k=0.285, curve="VI"):
        self.reference = reference
        self.i_nominal = i_nominal
        self.ctr = ctr
        self.i_pickup = i_pickup
        self.k = k # Time dial
        self.curve = curve

    def __str__(self):
        return f"""
        Relay SPAJ {self.reference} created with the following settings:
            - Inom = {self.i_nominal}
            - CTR = {self.ctr}
            - Ipickup = {self.i_pickup}
            - Curve = {self.curve}
            - k = {self.k}
        """

    @property
    def i_nominal(self):
        return self._i_nominal

    @i_nominal.setter
    def i_nominal(self, i_nominal):
        if i_nominal not in (1, 5):
            raise ValueError("Not available connection to the nominal value current input")
        self._i_nominal = i_nominal

    def multiple(self, primary_current):
        primary_pickup = self.i_pickup * self.i_nominal * self.ctr
        M = primary_current / primary_pickup
        return M
      
    def trip_time(self, primary_current):
        m = self.multiple(primary_current)
        if m <= 1:
            return math.inf
        else:
            match self.curve:
                case "NI":
                    time_to_trip = self.k * 0.14 / ((m ** 0.02) - 1)
                case "VI":
                    time_to_trip = self.k * 13.5 / (m - 1)
                case "EI":
                    time_to_trip = self.k * 80 / ((m ** 2) - 1)
                case "LTI":
                    time_to_trip = self.k * 120 / (m - 1)
                case _:
                    raise ValueError("No such curve available on the relay")
            return time_to_trip

    def evaluate_trip(self, data):
        acc = [0.0, 0.0, 0.0]
        for i in range(len(data.time) - 1):
            dt = (data.time[i+1] - data.time[i])
            for j, phase in enumerate([data.ia, data.ib, data.ic]):
                if self.multiple(phase[i]) > 1:
                    acc[j] += dt / (self.trip_time(phase[i]) * 1000)
                    if acc[j] >= 1:
                        return [True, data.time[i]]
                else:
                    acc[j] = 0.0
        return [False, 0]



def read_current_csv(path):
    '''
    Function to read current data
    '''
    inside_data = False # This will help us skip the first metadata rows
    time = [] # Time in miliseconds
    current_ia = [] # Ia list
    current_ib = [] # Ib list
    current_ic = [] # Ic list
    with open(path) as f:
        t0 = None
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if not row:
                continue
            if row[0] == "Date":
                inside_data = True
                continue
            if inside_data:
                date = row[0].split(".")
                date_time = dt.datetime.fromisoformat(f"{date[2]}-{date[1]}-{date[0]} {row[1]}")

                if t0 is None:
                    t0 = date_time

                ms = (date_time - t0).total_seconds() * 1000

                time.append(ms)
                current_ia.append(float(row[2]))
                current_ib.append(float(row[3]))
                current_ic.append(float(row[4]))
    return CurrentData(time, current_ia, current_ib, current_ic)

def downsample(samples, step=2):
    '''
    Function to create a downsample sample
    '''
    return CurrentData(samples.time[::step], samples.ia[::step], samples.ib[::step], samples.ic[::step])

def plot_current(samples, trip_info=None): 
    '''
    Function to plot the current
    '''
    # Preparing data
    x = np.array(samples.time)
    y1 = np.array(samples.ia)
    y2 = np.array(samples.ib)
    y3 = np.array(samples.ic)

    # Plotting
    fig, ax = plt.subplots()

    ax.plot(x, y1, color="red")
    ax.plot(x, y2, color="blue")
    ax.plot(x, y3, color="green")

    plt.show()

def plot_trip_window(samples, trip_info):
    '''
    Function to plot the trip window
    '''
    ...

def parser_commands():
    parser = argparse.ArgumentParser(prog="Time Overcurrent Trip Calculation", description="It test if an inverse overcurrent protection would trip under a certain current behavior of the load")
    parser.add_argument("-p", "--path", default=argparse.SUPPRESS, required=True, help="Path of the CSV file", type=str)
    parser.add_argument("-pu", "--pickup", default=0.5, help="Pick up (times of nominal secondary current)", type=float)
    parser.add_argument("-td", "--time_dial", default=0.285, help="Time dial of the curve", type=float)
    parser.add_argument("-c", "--curve", default="VI", help="Type of curve (NI, VI, EI, LTI)", type=str)
    parser.add_argument("-ctr", "--transformation_ratio", default=120, help="Transformation ratio of the CT connected", type=float)
    parser.add_argument("-inom", "--nominal_current", default=5, help="Secondary nominal current connection on the relay", type=float)
    parser.add_argument("-s", "--step", default=2, help="Step for downsample full plot", type=int)
    args = parser.parse_args()
    return args


def main():
    args = parser_commands()
    car_dumper_relay = RelaySpaj("141C", i_nominal=args.nominal_current, ctr=args.transformation_ratio, i_pickup=args.pickup, k=args.time_dial, curve=args.curve)
    print(car_dumper_relay)

    data_file_path = args.path
    data = read_current_csv(data_file_path)

    downsample_data = downsample(data, args.step)
    plot_current(downsample_data)

    trip = car_dumper_relay.evaluate_trip(data)
    print(trip)

if __name__ == "__main__":
    main()
