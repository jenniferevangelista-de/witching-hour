"""Tonight: live weather from SerpApi, and TabPFN's guess of how each room will feel.

The weather comes from a live Google search through SerpApi (hourly forecast for
the house's town). TabPFN reads the house's own past nights (outdoor conditions
-> indoor temperature) and predicts each room for tonight, 00:00 to 06:00. The
family gets a heads-up before the cold night, not after it.
"""
from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from .checks import UTILITY_ROOMS, WHO_MIN_C
from .data import House
from .scanner import Q05, Q50, Q95, QUANTILES

FEATURES = ["tod_sin", "tod_cos", "T_out", "RH_out", "Windspeed", "Tdewpoint"]


def dewpoint(t_c: float, rh: float) -> float:
    a, b = 17.62, 243.12
    g = math.log(max(rh, 1.0) / 100.0) + a * t_c / (b + t_c)
    return round(b * g / (a - g), 1)


def _num(s) -> float:
    m = re.search(r"-?\d+(?:\.\d+)?", str(s))
    return float(m.group(0)) if m else float("nan")


def parse_hourly(answer_box: dict) -> list[dict]:
    """The next 00:00 to 06:00 from SerpApi's hourly forecast."""
    hourly = answer_box.get("hourly_forecast") or []
    start = next((i for i, h in enumerate(hourly) if str(h.get("time", "")).endswith("00:00") and i > 0), None)
    if start is None:
        raise ValueError("no midnight in the hourly forecast")
    out = []
    for h in hourly[start:start + 7]:
        day, _, hhmm = str(h["time"]).rpartition(" ")
        t, rh = _num(h.get("temperature")), _num(h.get("humidity"))
        out.append({"day": day, "time": hhmm, "temp_c": t, "humidity": rh,
                    "wind_ms": round(_num(h.get("wind")) / 3.6, 1), "weather": h.get("weather", ""),
                    "dewpoint_c": dewpoint(t, rh)})
    return out


def fetch_forecast(place: str, api_key: str | None = None) -> dict:
    import requests

    key = api_key or os.environ.get("SERPAPI_KEY")
    if not key:
        raise RuntimeError("SERPAPI_KEY is not set")
    r = requests.get("https://serpapi.com/search.json", timeout=60, params={
        "engine": "google", "q": f"weather {place} tonight", "hl": "en", "api_key": key})
    r.raise_for_status()
    ab = r.json().get("answer_box") or {}
    if ab.get("type") != "weather_result":
        raise ValueError("no weather answer box in the search results")
    return {
        "place": ab.get("location", place), "query": f"weather {place} tonight",
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Google weather results via SerpApi", "hours": parse_hourly(ab),
    }


def night_training_rows(house: House, max_rows: int = 1000, seed: int = 0) -> pd.DataFrame:
    df = house.df[house.df.index.hour < 7].dropna(subset=["T_out", "RH_out", "Windspeed", "Tdewpoint"])
    if len(df) > max_rows:
        df = df.iloc[np.sort(np.random.default_rng(seed).choice(len(df), max_rows, replace=False))]
    return df


def _features(tod: np.ndarray, t_out, rh, wind, dew) -> pd.DataFrame:
    return pd.DataFrame({"tod_sin": np.sin(2 * np.pi * tod / 24), "tod_cos": np.cos(2 * np.pi * tod / 24),
                         "T_out": t_out, "RH_out": rh, "Windspeed": wind, "Tdewpoint": dew})


def p_below(q_row: np.ndarray, threshold: float) -> float:
    """P(reading < threshold), read off the predicted quantiles (linear between them)."""
    qs = np.asarray(QUANTILES)
    if threshold <= q_row[0]:
        return round(float(qs[0]) * 0.5, 3)
    if threshold >= q_row[-1]:
        return round(float(1 - (1 - qs[-1]) * 0.5), 3)
    return round(float(np.interp(threshold, q_row, qs)), 3)


def forecast_house(house: House, forecast: dict, backend) -> dict:
    train = night_training_rows(house)
    tod_tr = np.asarray(train.index.hour + train.index.minute / 60, dtype=float)
    X_tr = _features(tod_tr, *(train[c].to_numpy(dtype=float) for c in ("T_out", "RH_out", "Windspeed", "Tdewpoint")))
    hours = forecast["hours"]
    tod_q = np.array([int(h["time"][:2]) for h in hours], dtype=float)
    X_q = _features(tod_q, [h["temp_c"] for h in hours], [h["humidity"] for h in hours],
                    [h["wind_ms"] for h in hours], [h["dewpoint_c"] for h in hours])
    rooms = []
    for s in house.sensors:
        if s.kind != "temperature" or s.room in UTILITY_ROOMS:
            continue
        q = backend.predict_quantiles(X_tr, train[s.id].to_numpy(dtype=float), X_q, QUANTILES)
        i = int(np.argmin(q[:, Q50]))
        rooms.append({
            "sensor": s.id, "room": s.room, "coldest_time": hours[i]["time"],
            "expected": round(float(q[i, Q50]), 1), "low": round(float(q[i, Q05]), 1), "high": round(float(q[i, Q95]), 1),
            "p_below_18": p_below(q[i], WHO_MIN_C),
            "hourly": [{"time": h["time"], "q05": round(float(q[j, Q05]), 1), "q50": round(float(q[j, Q50]), 1),
                        "q95": round(float(q[j, Q95]), 1)} for j, h in enumerate(hours)],
        })
    rooms.sort(key=lambda r: r["expected"])
    return {**forecast, "backend": backend.name, "trained_on": f"{len(train)} night-time readings of this house",
            "rooms": rooms}
