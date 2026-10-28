import numpy as np
import pandas as pd

from witching_hour.data import House
from witching_hour.scanner import QUANTILES
from witching_hour.sensors import make_sensor
from witching_hour.tonight import dewpoint, forecast_house, p_below, parse_hourly


def test_parse_hourly_takes_the_next_midnight_to_six():
    hours = [{"time": "Wednesday 22:00", "temperature": "9", "humidity": "90%", "wind": "7 km/h", "weather": "Clear"},
             {"time": "Wednesday 23:00", "temperature": "8", "humidity": "91%", "wind": "7 km/h", "weather": "Clear"}]
    hours += [{"time": f"Thursday {h:02d}:00", "temperature": str(7 - h), "humidity": "92%", "wind": "3.6 km/h",
               "weather": "Clear"} for h in range(10)]
    out = parse_hourly({"hourly_forecast": hours})
    assert [h["time"] for h in out] == [f"{h:02d}:00" for h in range(7)]
    assert out[0]["day"] == "Thursday" and out[3]["temp_c"] == 4 and out[0]["wind_ms"] == 1.0


def test_dewpoint_and_probability_from_quantiles():
    assert abs(dewpoint(20, 50) - 9.3) < 0.2
    q = np.array([16.0, 16.5, 17.2, 17.6, 18.0, 18.7, 19.2])
    assert p_below(q, 17.6) == 0.5
    assert p_below(q, 15.0) < 0.01 and p_below(q, 20.0) > 0.99


class FixedBackend:
    name = "fixed"

    def predict_quantiles(self, X_ctx, y_ctx, X_q, quantiles):
        base = X_q["T_out"].to_numpy() + 10
        return np.column_stack([base + d for d in np.linspace(-1, 1, len(QUANTILES))])


def test_forecast_ranks_rooms_and_skips_utility_rooms():
    idx = pd.date_range("2016-01-01", periods=144 * 3, freq="10min")
    df = pd.DataFrame({"T_out": 5.0, "RH_out": 90.0, "Windspeed": 2.0, "Tdewpoint": 3.0,
                       "T1": 20.0, "T3": 19.0}, index=idx)
    house = House(df, [make_sensor("T1", "kitchen", "temperature"), make_sensor("T3", "laundry room", "temperature")])
    hours = [{"day": "Thursday", "time": f"{h:02d}:00", "temp_c": 8 - h, "humidity": 90, "wind_ms": 2, "dewpoint_c": 3,
              "weather": "Clear"} for h in range(7)]
    res = forecast_house(house, {"place": "Stambruges", "hours": hours}, FixedBackend())
    assert [r["room"] for r in res["rooms"]] == ["kitchen"]
    r = res["rooms"][0]
    assert r["coldest_time"] == "06:00" and r["expected"] == 12.0 and r["p_below_18"] > 0.99


def test_parse_hourly_accepts_midnight_as_first_entry():
    hours = [{"time": f"Thursday {h:02d}:00", "temperature": "5", "humidity": "90%", "wind": "0 km/h"} for h in range(8)]
    assert parse_hourly({"hourly_forecast": hours})[0]["time"] == "00:00"


def test_parse_hourly_understands_a_12_hour_clock():
    hours = [{"time": "Wednesday 11 PM", "temperature": "6", "humidity": "90%", "wind": "0 km/h"}]
    hours += [{"time": f"Thursday {h} AM", "temperature": "5", "humidity": "90%", "wind": "0 km/h"} for h in [12, 1, 2, 3, 4, 5, 6]]
    out = parse_hourly({"hourly_forecast": hours})
    assert [h["time"] for h in out] == [f"{h:02d}:00" for h in range(7)] and out[0]["day"] == "Thursday"
