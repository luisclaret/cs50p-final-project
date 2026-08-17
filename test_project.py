"""
Tests for the ABB SPAJ inverse overcurrent trip evaluation.
"""

import os

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from project import (
    CurrentData,
    RelaySpaj,
    downsample,
    plot_current,
    plot_trip_window,
    read_current_csv,
)

EXAMPLE_CSV = os.path.join(os.path.dirname(__file__), "corrientes_ejemplo.csv")


def test_read_current_csv():
    data = read_current_csv(EXAMPLE_CSV)

    # 5 data rows in the example file
    assert len(data.time) == 5
    assert len(data.ia) == 5
    assert len(data.ib) == 5
    assert len(data.ic) == 5

    # Time starts at zero and ends at ~805 ms (200 ms sampling)
    assert data.time[0] == 0.0
    assert data.time[1] == pytest.approx(200.0)
    assert data.time[-1] == pytest.approx(805.0)

    # First and last phase currents match the file
    assert data.ia[0] == pytest.approx(212.658)
    assert data.ia[-1] == pytest.approx(211.416)
    assert data.ib[0] == pytest.approx(216.351)
    assert data.ic[0] == pytest.approx(206.133)


def test_downsample():
    data = CurrentData(
        time=[0.0, 100.0, 200.0, 300.0],
        ia=[1.0, 2.0, 3.0, 4.0],
        ib=[5.0, 6.0, 7.0, 8.0],
        ic=[9.0, 10.0, 11.0, 12.0],
    )

    result = downsample(data, step=2)

    assert result.time == [0.0, 200.0]
    assert result.ia == [1.0, 3.0]
    assert result.ib == [5.0, 7.0]
    assert result.ic == [9.0, 11.0]

    # The original data is left untouched
    assert data.time == [0.0, 100.0, 200.0, 300.0]


def test_downsample_invalid_step():
    data = CurrentData([0.0], [1.0], [2.0], [3.0])
    with pytest.raises(ValueError):
        downsample(data, step=0)


def test_multiple():
    relay = RelaySpaj("141C")  # primary pickup = 0.5 * 5 * 120 = 300 A

    assert relay.primary_pickup == 300.0
    assert relay.multiple(600.0) == pytest.approx(2.0)
    assert relay.multiple(300.0) == pytest.approx(1.0)
    assert relay.multiple(150.0) == pytest.approx(0.5)


def test_trip_time():
    vi = RelaySpaj("141C", k=1.0, curve="VI")
    assert vi.trip_time(600.0) == pytest.approx(13.5)  # M=2, very inverse

    ni = RelaySpaj("141C", k=1.0, curve="NI")
    assert ni.trip_time(600.0) == pytest.approx(10.03, abs=0.01)  # M=2, normal inverse

    # At or below pickup the relay never trips
    assert vi.trip_time(300.0) == float("inf")
    assert vi.trip_time(100.0) == float("inf")


def test_trip_time_invalid_curve():
    relay = RelaySpaj("141C", curve="XX")
    with pytest.raises(ValueError):
        relay.trip_time(600.0)


def test_evaluate_trip():
    relay = RelaySpaj("141C", k=0.285, curve="VI")

    # Constant 600 A (M=2) on phase A; other phases below pickup
    n = 40
    time = [i * 200.0 for i in range(n)]
    ia = [600.0] * n
    ib = [100.0] * n
    ic = [100.0] * n

    result = relay.evaluate_trip(CurrentData(time, ia, ib, ic))

    assert result["tripped"] is True
    assert result["phase"] == 0
    assert result["trip_ms"] == pytest.approx(3800.0)
    assert result["pickup_ms"][0] == 0.0


def test_evaluate_trip_no_trip():
    relay = RelaySpaj("141C", k=0.285, curve="VI")

    time = [0.0, 200.0, 400.0, 600.0, 800.0]
    ia = [100.0] * 5
    ib = [100.0] * 5
    ic = [100.0] * 5

    result = relay.evaluate_trip(CurrentData(time, ia, ib, ic))

    assert result["tripped"] is False
    assert result["phase"] is None
    assert result["trip_ms"] is None


def test_plot_current():
    data = CurrentData(
        time=[0.0, 200.0, 400.0],
        ia=[300.0, 500.0, 400.0],
        ib=[300.0, 500.0, 400.0],
        ic=[300.0, 500.0, 400.0],
    )
    trip_info = {
        "tripped": True,
        "phase": 0,
        "trip_ms": 200.0,
        "pickup_ms": [0.0, 0.0, 0.0],
    }

    assert plot_current(data, trip_info) is None
    plt.close("all")


def test_plot_trip_window():
    data = CurrentData(
        time=[0.0, 200.0, 400.0, 600.0, 800.0, 1000.0],
        ia=[500.0] * 6,
        ib=[500.0] * 6,
        ic=[500.0] * 6,
    )
    trip_info = {
        "tripped": True,
        "phase": 0,
        "trip_ms": 800.0,
        "pickup_ms": [200.0, 0.0, 0.0],
    }

    assert plot_trip_window(data, trip_info, pickup_current=300.0) is None
    plt.close("all")
