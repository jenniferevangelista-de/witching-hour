"""Loading a house: the public UCI house, or your own Home Assistant export."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from .sensors import UCI_CONTEXT, UCI_SENSORS, Sensor, infer_sensor

UCI_URL = "https://archive.ics.uci.edu/static/public/374/appliances+energy+prediction.zip"
UCI_ATTRIBUTION = (
    "Appliances energy prediction (UCI Machine Learning Repository, CC BY 4.0). "
    "Candanedo, Feldheim & Deramaix (2017), Energy and Buildings 140. "
    "A real house in Stambruges, Belgium, January to May 2016."
)
STEP = pd.Timedelta(minutes=10)


@dataclass
class House:
    """A wide table of readings every 10 minutes, plus what each column means."""

    df: pd.DataFrame
    sensors: list[Sensor]
    context: list[str] = field(default_factory=list)
    name: str = "house"
    attribution: str = ""

    def sensor(self, sensor_id: str) -> Sensor:
        for s in self.sensors:
            if s.id == sensor_id:
                return s
        raise KeyError(f"unknown sensor {sensor_id!r}")

    @property
    def sensor_ids(self) -> list[str]:
        return [s.id for s in self.sensors]


# ---------------------------------------------------------------- loaders


def fetch_uci(dest: str | Path) -> Path:
    """Download the UCI zip once. Returns the zip path."""
    import requests

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "appliances_energy_prediction.zip"
    if not out.exists():
        r = requests.get(UCI_URL, timeout=120)
        r.raise_for_status()
        out.write_bytes(r.content)
    return out


def _read_uci_csv(path: Path) -> pd.DataFrame:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            return pd.read_csv(io.BytesIO(z.read(name)), dtype=str)
    return pd.read_csv(path, dtype=str)


def load_uci(path: str | Path) -> House:
    raw = _read_uci_csv(Path(path))
    df = pd.DataFrame(index=pd.to_datetime(raw["date"].str.strip()))
    df.index.name = "time"
    for col in raw.columns:
        if col in ("date", "rv1", "rv2"):
            continue
        df[col] = pd.to_numeric(raw[col].str.strip(), errors="coerce").to_numpy()
    df = df.sort_index()
    df = df[~df.index.duplicated()]
    df = df.asfreq(STEP).interpolate(limit=3)
    return House(df=df, sensors=list(UCI_SENSORS), context=list(UCI_CONTEXT), name="UCI house", attribution=UCI_ATTRIBUTION)


def load_home_assistant(path: str | Path, tz: str = "UTC", entities: list[str] | None = None) -> House:
    """Home Assistant history export (columns entity_id, state, last_changed).

    States are step functions: a value holds until the next change. We hold it,
    then average into 10 minute buckets. "on"/"off" become 1/0 so a light can haunt.
    """
    raw = pd.read_csv(path, dtype=str)
    need = {"entity_id", "state", "last_changed"}
    if not need.issubset(raw.columns):
        raise ValueError(f"expected columns {sorted(need)}, got {list(raw.columns)}")
    raw["state"] = raw["state"].str.strip().str.lower().replace({"on": "1", "off": "0", "true": "1", "false": "0"})
    raw["value"] = pd.to_numeric(raw["state"], errors="coerce")
    raw = raw.dropna(subset=["value"])
    t = pd.to_datetime(raw["last_changed"], utc=True, format="mixed")
    raw["time"] = t.dt.tz_convert(tz).dt.tz_localize(None)
    if entities:
        raw = raw[raw["entity_id"].isin(entities)]
    if raw.empty:
        raise ValueError("no numeric states found in the export")

    start = raw["time"].min().floor("10min")
    end = raw["time"].max().ceil("10min")
    grid = pd.date_range(start, end, freq="1min")
    cols = {}
    for ent, g in raw.groupby("entity_id"):
        s = g.set_index("time")["value"].sort_index()
        s = s[~s.index.duplicated(keep="last")]
        held = s.reindex(s.index.union(grid)).ffill().reindex(grid)
        cols[ent] = held.resample("10min").mean()
    df = pd.DataFrame(cols)
    df.index.name = "time"
    df = df.dropna(how="all")
    sensors = [infer_sensor(c) for c in df.columns]
    return House(df=df, sensors=sensors, context=[], name=Path(path).stem, attribution="Your own Home Assistant export.")


# ---------------------------------------------------------------- nights


def night_bounds(night: date, start_hour: int = 0, end_hour: int = 6) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The witching window of a night: [night start_hour, night end_hour)."""
    d = pd.Timestamp(datetime(night.year, night.month, night.day))
    return d + pd.Timedelta(hours=start_hour), d + pd.Timedelta(hours=end_hour)


def night_rows(df: pd.DataFrame, night: date, start_hour: int = 0, end_hour: int = 6) -> pd.DataFrame:
    a, b = night_bounds(night, start_hour, end_hour)
    return df[(df.index >= a) & (df.index < b)]


def context_rows(df: pd.DataFrame, night: date, days: int = 14, start_hour: int = 0) -> pd.DataFrame:
    """The house's memory: every reading of the `days` days before the night starts."""
    a, _ = night_bounds(night, start_hour)
    return df[(df.index >= a - pd.Timedelta(days=days)) & (df.index < a)]


def eligible_nights(house: House, start_hour: int = 0, end_hour: int = 6, context_days: int = 14) -> list[date]:
    """Nights with a complete window and enough memory before them."""
    df = house.df
    if df.empty:
        return []
    first = df.index.min() + pd.Timedelta(days=context_days)
    expected_rows = int((end_hour - start_hour) * 6)
    out = []
    day = first.normalize().date()
    last = df.index.max().date()
    while day <= last:
        a, b = night_bounds(day, start_hour, end_hour)
        if a >= first:
            rows = night_rows(df, day, start_hour, end_hour)
            if len(rows) == expected_rows and rows[house.sensor_ids].notna().all().all():
                out.append(day)
        day += timedelta(days=1)
    return out


# ---------------------------------------------------------------- features


def peer_columns(house: House, target: str) -> list[str]:
    """Other rooms of the same kind. Same room is left out on purpose: a shower
    raises bathroom humidity AND bathroom temperature, and we don't want one to
    explain the other away."""
    t = house.sensor(target)
    if t.kind not in ("temperature", "humidity"):
        return []
    return [s.id for s in house.sensors if s.kind == t.kind and s.room != t.room and s.id != target]


def features(house: House, rows: pd.DataFrame, target: str) -> pd.DataFrame:
    idx = rows.index
    tod = idx.hour + idx.minute / 60.0
    X = pd.DataFrame(index=idx)
    X["tod"] = tod
    X["tod_sin"] = np.sin(2 * np.pi * tod / 24)
    X["tod_cos"] = np.cos(2 * np.pi * tod / 24)
    X["dow"] = idx.day_of_week
    X["weekend"] = (idx.day_of_week >= 5).astype(int)
    for c in house.context:
        if c in rows.columns:
            X[c] = rows[c].to_numpy()
    for c in peer_columns(house, target):
        X[c] = rows[c].to_numpy()
    return X
