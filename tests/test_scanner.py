from datetime import date

import numpy as np
import pandas as pd

from tests.conftest import GHOST_NIGHT
from witching_hour.scanner import QUANTILES, NightScan, SeasonalBackend, find_events, scan_night, surprise
from witching_hour.sensors import make_sensor


def test_surprise_is_asymmetric_and_floored():
    q = np.array([[0, 10, 20, 30, 40, 80, 90]], dtype=float)  # q05=10, q50=30, q95=80
    z_up = surprise(np.array([80.0]), q, 0.0)
    z_dn = surprise(np.array([10.0]), q, 0.0)
    assert abs(z_up[0] - 1.6449) < 1e-3 and abs(z_dn[0] + 1.6449) < 1e-3
    flat = np.zeros((1, len(QUANTILES)))
    assert abs(surprise(np.array([10.0]), flat, 10.0)[0] - 1.6449) < 1e-3


def _times(n):
    return pd.date_range("2016-01-01 00:00", periods=n, freq="10min")


def test_find_events_runs_gaps_and_single_spikes():
    s = make_sensor("T1", "kitchen", "temperature")
    z = np.zeros(36)
    z[[3, 4, 6]] = 5.0  # run with a one-slot gap
    z[20] = 4.5  # lonely, not loud enough
    z[30] = -7.0  # lonely but very loud
    y = np.full(36, 20.0)
    q = np.tile(np.linspace(19, 21, len(QUANTILES)), (36, 1))
    ev = find_events(_times(36), y, q, z, s)
    assert [(e.start, e.end, e.direction) for e in ev] == [("00:30", "01:10", "above"), ("05:00", "05:10", "below")]
    assert ev[0].duration_min == 40


def test_seasonal_scan_finds_the_planted_ghost(house):
    scan = scan_night(house, date.fromisoformat(GHOST_NIGHT), SeasonalBackend(), sensors=["T1", "T2"])
    t1 = [e for e in scan.events if e.sensor == "T1"]
    assert t1, "the 3 degree ghost in the kitchen should be found"
    assert t1[0].start == "03:00" and t1[0].direction == "above"
    assert not [e for e in scan.events if e.sensor == "T2"]
    assert scan.events[0].id == "E1"
    rt = NightScan.from_dict(scan.to_dict())
    assert rt.events[0].observed == scan.events[0].observed and rt.score == scan.score


def test_quiet_night_has_no_temperature_events(house):
    scan = scan_night(house, date(2016, 1, 16), SeasonalBackend(), sensors=["T1", "T2"])
    assert scan.events == []
    assert len(scan.series["T1"]["t"]) == 36
