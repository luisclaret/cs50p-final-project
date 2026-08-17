"""
ABB SPAJ inverse overcurrent trip evaluation from sampled current data.
"""

import numpy as np
import matplotlib.pyplot as plt
import csv
import datetime as dt
import argparse
import math
import textwrap
from dataclasses import dataclass

@dataclass
class CurrentData:
    """Dataclass holding the sampled time and three phase currents."""

    time: list[float]
    ia: list[float]
    ib: list[float]
    ic: list[float]

class RelaySpaj:
    """Represent an ABB SPAJ relay with inverse overcurrent settings."""

    def __init__(self, reference, i_nominal=5, ctr=120, i_pickup=0.5, k=0.285, curve="VI"):
        """
        Initialize the relay with its settings.

        :param reference: Relay model reference (e.g. "141C")
        :type reference: str
        :param i_nominal: Nominal secondary current connection in amperes
        :type i_nominal: int
        :param ctr: Current transformer ratio (primary/secondary)
        :type ctr: float
        :param i_pickup: Pickup current as multiple of nominal secondary current
        :type i_pickup: float
        :param k: Time dial (time multiplier) of the curve
        :type k: float
        :param curve: Inverse-time curve type ("NI", "VI", "EI" or "LTI")
        :type curve: str
        """
        self.reference = reference
        self.i_nominal = i_nominal
        self.ctr = ctr
        self.i_pickup = i_pickup
        self.k = k # Time dial
        self.curve = curve

    def __str__(self):
        """
        Return a human-readable summary of the relay settings.

        :return: Formatted string with the relay settings
        :rtype: str
        """
        return textwrap.dedent(f"""
            Relay SPAJ {self.reference} created with the following settings:
                - Inom = {self.i_nominal}
                - CTR = {self.ctr}
                - Ipickup = {self.i_pickup}
                - Curve = {self.curve}
                - k = {self.k}
            """).strip()

    @property
    def i_nominal(self):
        """Return the nominal secondary current connection."""
        return self._i_nominal

    @i_nominal.setter
    def i_nominal(self, i_nominal):
        if i_nominal not in (1, 5):
            raise ValueError("Not available connection to the nominal value current input")
        self._i_nominal = i_nominal

    @property
    def primary_pickup(self):
        """Return the pickup current on the primary side in amperes."""
        return self.i_pickup * self.i_nominal * self.ctr

    def multiple(self, primary_current: float) -> float:
        """
        Return the current as a multiple of the primary pickup current.

        :param primary_current: Primary-side current in amperes
        :type primary_current: float
        :return: Current multiple M = primary_current / primary_pickup
        :rtype: float
        """
        return primary_current / self.primary_pickup

    def trip_time(self, primary_current: float, m: float | None = None) -> float:
        """
        Return the relay trip time in seconds for a given primary current.

        :param primary_current: Primary-side current in amperes
        :type primary_current: float
        :param m: Precomputed multiple M = primary_current / primary_pickup
        :type m: float or None
        :return: Trip time in seconds, or inf if the current is at/below pickup
        :rtype: float
        :raise ValueError: If the curve is not one of "NI", "VI", "EI" or "LTI"
        """
        if m is None:
            m = self.multiple(primary_current)
        if m <= 1:
            return math.inf
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

    def evaluate_trip(self, data: CurrentData) -> dict:
        """
        Evaluate whether the relay would trip for a sampled current profile.

        Accumulates dt / trip_time per phase while the current is above pickup
        and resets to zero whenever it falls back below pickup.

        :param data: Sampled time and three phase currents
        :type data: CurrentData
        :return: Dictionary with tripped, phase, trip_ms and pickup_ms keys
        :rtype: dict
        """
        acc = [0.0, 0.0, 0.0]
        pickup_time = [0.0, 0.0, 0.0]
        for i in range(len(data.time) - 1):
            dt_ms = (data.time[i+1] - data.time[i])
            for j, phase in enumerate([data.ia, data.ib, data.ic]):
                m = self.multiple(phase[i])
                if m > 1:
                    if acc[j] == 0:
                        pickup_time[j] = data.time[i]
                    acc[j] += dt_ms / (self.trip_time(phase[i], m) * 1000)
                    if acc[j] >= 1:
                        return {"tripped": True, "phase": j, "trip_ms": data.time[i], "pickup_ms": pickup_time}
                else:
                    acc[j] = 0.0
                    pickup_time[j] = 0.0
        return {"tripped": False, "phase": None, "trip_ms": None, "pickup_ms": None}



def read_current_csv(path: str) -> CurrentData:
    """
    Read tab-separated current samples from a CSV file.

    :param path: Path to the CSV file
    :type path: str
    :return: Dataclass with time (ms) and the three phase currents
    :rtype: CurrentData
    """
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

def downsample(samples: CurrentData, step: int = 2) -> CurrentData:
    """
    Return a downsampled copy of the samples.

    :param samples: Sampled time and three phase currents
    :type samples: CurrentData
    :param step: Keep every step-th sample
    :type step: int
    :return: Downsampled dataclass
    :rtype: CurrentData
    :raise ValueError: If step is less than 1
    """
    if step < 1:
        raise ValueError("Step must be a positive integer")
    return CurrentData(samples.time[::step], samples.ia[::step], samples.ib[::step], samples.ic[::step])

def plot_current(samples: CurrentData, trip_info: dict | None = None, ax=None) -> None:
    """
    Plot the three phase currents on the given axes.

    :param samples: Sampled time and three phase currents
    :type samples: CurrentData
    :param trip_info: Trip evaluation result with trip and pickup times
    :type trip_info: dict or None
    :param ax: Matplotlib axes to draw on (a new one is created if None)
    """
    # Preparing data
    x = np.array(samples.time)
    y1 = np.array(samples.ia)
    y2 = np.array(samples.ib)
    y3 = np.array(samples.ic)

    # Plotting
    if ax is None:
        _, ax = plt.subplots()

    ax.set_title("Current load behavior")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Current (A)")
    ax.plot(x, y1, color="red", label="Ia")
    ax.plot(x, y2, color="blue", label="Ib")
    ax.plot(x, y3, color="green", label="Ic")

    # Plotting tripping moment if any
    if trip_info is not None and trip_info["trip_ms"]:
        # Tripping moment
        ax.axvline(trip_info["trip_ms"], color="black", linestyle="--", label="Trip time")
        # Pick up moments (skip phases that never picked up, marked by 0.0)
        pickup_labels = ["Pick up Ia", "Pick up Ib", "Pick up Ic"]
        pickup_colors = ["red", "blue", "green"]
        for t, label, color in zip(trip_info["pickup_ms"], pickup_labels, pickup_colors):
            if t:
                ax.axvline(t, color=color, linestyle="--", label=label)

    ax.legend()

def plot_trip_window(samples: CurrentData, trip_info: dict, pickup_current: float, ax=None, pad: int = 2000) -> None:
    """
    Plot a zoomed window around the trip moment.

    :param samples: Sampled time and three phase currents
    :type samples: CurrentData
    :param trip_info: Trip evaluation result with trip and pickup times
    :type trip_info: dict
    :param pickup_current: Pickup current on the primary side in amperes
    :type pickup_current: float
    :param ax: Matplotlib axes to draw on (a new one is created if None)
    :param pad: Milliseconds of context to show before pickup and after trip
    :type pad: int
    """
    if ax is None:
        _, ax = plt.subplots()

    # Calculation of zoom window
    start = trip_info["pickup_ms"][trip_info["phase"]] - pad
    end = trip_info["trip_ms"] + pad
    t = np.array(samples.time)
    lo, hi = np.searchsorted(t, [start, end])

    # Calculation of total tripping time
    pickup_ms = trip_info["pickup_ms"][trip_info["phase"]]
    trip_ms = trip_info["trip_ms"]
    duration_s = (trip_ms - pickup_ms) / 1000 # In seconds

    # Preparing data to plot
    x = t[lo:hi]
    y1 = np.array(samples.ia)[lo:hi]
    y2 = np.array(samples.ib)[lo:hi]
    y3 = np.array(samples.ic)[lo:hi]

    # Current behavior during the fault
    ax.set_title("Current load behavior during the fault")
    ax.set_xlabel("Time (ms)")
    ax.set_ylabel("Current (A)")
    ax.plot(x, y1, color="red", label="Ia")
    ax.plot(x, y2, color="blue", label="Ib")
    ax.plot(x, y3, color="green", label="Ic")

    # Pick up moments (skip phases that never picked up, marked by 0.0)
    pickup_labels = ["Pick up Ia", "Pick up Ib", "Pick up Ic"]
    pickup_colors = ["red", "blue", "green"]
    for t, label, color in zip(trip_info["pickup_ms"], pickup_labels, pickup_colors):
        if t:
            ax.axvline(t, color=color, linestyle="--", label=label)

    # Trip moment
    ax.axvline(trip_info["trip_ms"], color="black", linestyle="--", label="Trip time")

    # Total tripping time line
    ax.hlines(pickup_current, pickup_ms, trip_ms, color="orange", linewidth=2, label=f"Trip time: {duration_s:.2f} s")

    ax.legend()



def parser_commands() -> argparse.Namespace:
    """
    Parse the command-line arguments for the relay evaluation.

    :return: Parsed arguments
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(prog="Time Overcurrent Trip Calculation", description="It test if an inverse overcurrent protection would trip under a certain current behavior of the load")
    parser.add_argument("-p", "--path", required=True, help="Path of the CSV file", type=str)
    parser.add_argument("-pu", "--pickup", default=0.5, help="Pick up (times of nominal secondary current)", type=float)
    parser.add_argument("-td", "--time_dial", default=0.285, help="Time dial of the curve", type=float)
    parser.add_argument("-c", "--curve", default="VI", help="Type of curve (NI, VI, EI, LTI)", type=str)
    parser.add_argument("-ctr", "--transformation_ratio", default=120, help="Transformation ratio of the CT connected", type=float)
    parser.add_argument("-inom", "--nominal_current", default=5, help="Secondary nominal current connection on the relay", type=float)
    parser.add_argument("-s", "--step", default=2, help="Step for downsample full plot", type=int)
    args = parser.parse_args()
    return args


def main() -> None:
    """
    Evaluate the relay trip and plot the results.
    """
    args = parser_commands()
    car_dumper_relay = RelaySpaj("141C", i_nominal=args.nominal_current, ctr=args.transformation_ratio, i_pickup=args.pickup, k=args.time_dial, curve=args.curve)
    print(car_dumper_relay)

    data_file_path = args.path
    data = read_current_csv(data_file_path)

    trip_info = car_dumper_relay.evaluate_trip(data)

    downsample_data = downsample(data, args.step)

    fig, (ax_full, ax_zoom) = plt.subplots(2, 1, figsize=(10, 8))
    if fig.canvas.manager is not None:
        fig.canvas.manager.set_window_title("CS50P Final Project")
    fig.suptitle("ABB SPAJ 141C - Inverse Overcurrent Protection Analysis")

    plot_current(downsample_data, trip_info, ax=ax_full)
    
    # Plot zoom data only if there was a trip
    if trip_info["tripped"]:
        pickup_current = car_dumper_relay.primary_pickup
        plot_trip_window(data, trip_info, pickup_current, ax=ax_zoom)

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
