import numpy as np
import pandas as pd
import pytest

from witching_hour.data import House
from witching_hour.sensors import make_sensor

GHOST_NIGHT = "2016-01-17"


def synthetic_house(days: int = 20, seed: int = 0, ghost: bool = True) -> House:
    idx = pd.date_range("2016-01-01", periods=days * 144, freq="10min")
    tod = idx.hour + idx.minute / 60
    rng = np.random.default_rng(seed)
    base = 20 + 1.5 * np.sin(2 * np.pi * (tod - 15) / 24)
    df = pd.DataFrame(index=idx)
    df.index.name = "time"
    df["T1"] = base + rng.normal(0, 0.1, len(idx))
    df["T2"] = base - 0.5 + rng.normal(0, 0.1, len(idx))
    df["RH_1"] = 45 + rng.normal(0, 0.5, len(idx))
    df["RH_2"] = 47 + rng.normal(0, 0.5, len(idx))
    df["Appliances"] = 50 + rng.gamma(2, 10, len(idx))
    df["T_out"] = 5 + 3 * np.sin(2 * np.pi * (tod - 15) / 24) + rng.normal(0, 0.3, len(idx))
    if ghost:
        a = pd.Timestamp(f"{GHOST_NIGHT} 03:00")
        mask = (df.index >= a) & (df.index < a + pd.Timedelta(minutes=40))
        df.loc[mask, "T1"] += 3.0
    sensors = [
        make_sensor("T1", "kitchen", "temperature"),
        make_sensor("T2", "bathroom", "temperature"),
        make_sensor("RH_1", "kitchen", "humidity"),
        make_sensor("RH_2", "bathroom", "humidity"),
        make_sensor("Appliances", "house", "energy"),
    ]
    return House(df=df, sensors=sensors, context=["T_out"], name="synthetic house", attribution="synthetic")


@pytest.fixture
def house():
    return synthetic_house()
