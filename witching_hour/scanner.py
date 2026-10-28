"""The scan: for every sensor, ask a model what the house expected tonight,
then mark the moments that fell outside that expectation.

The default model is TabPFN, a pretrained tabular foundation model. It reads the
last two weeks of the house as context (in-context learning, no training loop)
and returns a full predictive distribution for each 10 minute slot of the night.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Protocol

import numpy as np
import pandas as pd

from .data import House, context_rows, features, night_rows

QUANTILES = [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
Q05, Q50, Q95 = QUANTILES.index(0.05), QUANTILES.index(0.5), QUANTILES.index(0.95)
Z90 = 1.6448536269514722  # half-width of a 90% normal interval, in sigmas


class Backend(Protocol):
    name: str

    def predict_quantiles(
        self, X_ctx: pd.DataFrame, y_ctx: np.ndarray, X_q: pd.DataFrame, quantiles: list[float]
    ) -> np.ndarray:  # shape (len(X_q), len(quantiles))
        ...


class TabPFNBackend:
    """TabPFN regressor, CPU friendly defaults. Weights are open (Prior Labs License).

    version "v2" downloads without an account. Newer versions (v3.5) ask for a
    one-time license acceptance at priorlabs.ai; set WH_TABPFN_VERSION to use them.
    """

    def __init__(self, version: str | None = None, n_estimators: int = 4, device: str = "cpu",
                 max_context: int = 1000, seed: int = 0):
        self.version = version or os.environ.get("WH_TABPFN_VERSION", "v2")
        self.n_estimators = n_estimators
        self.device = device
        self.max_context = max_context
        self.seed = seed
        self.name = f"tabpfn-{self.version}"

    def _model(self):
        from tabpfn import TabPFNRegressor
        from tabpfn.constants import ModelVersion

        return TabPFNRegressor.create_default_for_version(
            ModelVersion(self.version), n_estimators=self.n_estimators, device=self.device, random_state=self.seed
        )

    def predict_quantiles(self, X_ctx, y_ctx, X_q, quantiles):
        X_ctx, y_ctx = _subsample(X_ctx, y_ctx, self.max_context, self.seed)
        model = self._model()
        model.fit(X_ctx.to_numpy(dtype=float), np.asarray(y_ctx, dtype=float))
        out = model.predict(X_q.to_numpy(dtype=float), output_type="quantiles", quantiles=list(map(float, quantiles)))
        return np.sort(np.column_stack(out), axis=1)


class LightGBMBackend:
    """Classic comparison: one gradient boosted quantile model per quantile."""

    name = "lightgbm-quantile"

    def __init__(self, n_estimators: int = 200, seed: int = 0):
        self.n_estimators = n_estimators
        self.seed = seed

    def predict_quantiles(self, X_ctx, y_ctx, X_q, quantiles):
        import lightgbm as lgb

        cols = []
        for q in quantiles:
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, n_estimators=self.n_estimators, learning_rate=0.05,
                                  num_leaves=15, min_child_samples=20, random_state=self.seed, verbose=-1)
            m.fit(X_ctx, y_ctx)
            cols.append(m.predict(X_q))
        return np.sort(np.column_stack(cols), axis=1)


class SeasonalBackend:
    """The rule of thumb: tonight at 03:10 should look like the last two weeks at 03:10 (plus or minus 30 min)."""

    name = "seasonal-same-hour"

    def __init__(self, half_window_hours: float = 0.5):
        self.h = half_window_hours

    def predict_quantiles(self, X_ctx, y_ctx, X_q, quantiles):
        tod_c = X_ctx["tod"].to_numpy()
        y_ctx = np.asarray(y_ctx, dtype=float)
        out = np.empty((len(X_q), len(quantiles)))
        for i, t in enumerate(X_q["tod"].to_numpy()):
            d = np.abs(tod_c - t)
            d = np.minimum(d, 24 - d)
            sel = y_ctx[d <= self.h]
            if sel.size == 0:
                sel = y_ctx
            out[i] = np.quantile(sel, quantiles)
        return out


def make_backend(name: str, **kw) -> Backend:
    name = name.lower()
    if name.startswith("tabpfn"):
        return TabPFNBackend(**kw)
    if name in ("lightgbm", "lgbm", "lightgbm-quantile"):
        return LightGBMBackend(**kw)
    if name in ("seasonal", "seasonal-same-hour"):
        return SeasonalBackend(**kw)
    raise ValueError(f"unknown backend {name!r}")


def _subsample(X: pd.DataFrame, y: np.ndarray, n: int, seed: int):
    if len(X) <= n:
        return X, y
    rng = np.random.default_rng(seed)
    keep = np.sort(rng.choice(len(X), size=n, replace=False))
    return X.iloc[keep], np.asarray(y)[keep]


# ---------------------------------------------------------------- surprise


def surprise(y: np.ndarray, q: np.ndarray, min_spread: float) -> np.ndarray:
    """Signed distance from the expected median, in 'sigmas' of the predicted band.

    Asymmetric on purpose: energy readings have a long upper tail and a hard floor
    at zero, so the upper and lower halves of the band get their own scale."""
    q05, q50, q95 = q[:, Q05], q[:, Q50], q[:, Q95]
    up = np.maximum(q95 - q50, min_spread) / Z90
    dn = np.maximum(q50 - q05, min_spread) / Z90
    up = np.maximum(up, 1e-9)
    dn = np.maximum(dn, 1e-9)
    return np.where(y >= q50, (y - q50) / up, (y - q50) / dn)


@dataclass
class Event:
    id: str
    sensor: str
    room: str
    kind: str
    unit: str
    direction: str  # above | below
    start: str  # HH:MM
    end: str  # HH:MM, end of the last flagged 10 minute slot
    peak_time: str
    observed: float
    expected: float  # median at the peak
    expected_low: float  # 5th percentile at the peak
    expected_high: float  # 95th percentile at the peak
    sigma: float  # |surprise| at the peak
    duration_min: int
    together_with: list[str] = field(default_factory=list)

    @property
    def delta(self) -> float:
        return self.observed - self.expected

    def facts(self) -> tuple[list[str], list[float]]:
        """Times and values a narrator may quote when it cites this event."""
        return [self.start, self.end, self.peak_time], [
            self.observed, self.expected, self.expected_low, self.expected_high, abs(self.delta), self.sigma,
            self.duration_min, self.duration_min / 60]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["delta"] = round(self.delta, 2)
        return d


def find_events(times: pd.DatetimeIndex, y: np.ndarray, q: np.ndarray, z: np.ndarray, sensor, *,
                z_event: float = 4.0, z_single: float = 6.0, max_gap: int = 1) -> list[Event]:
    """Runs of |z| >= z_event with the same sign. A run needs 2+ slots, unless a
    single slot is very loud (z_single). Gaps of `max_gap` quiet slots are bridged."""
    flagged = np.abs(z) >= z_event
    sign = np.sign(z)
    runs: list[list[int]] = []
    cur: list[int] = []
    for i in range(len(z)):
        if flagged[i] and (not cur or sign[i] == sign[cur[-1]]) and (not cur or i - cur[-1] - 1 <= max_gap):
            cur.append(i)
        elif flagged[i]:
            if cur:
                runs.append(cur)
            cur = [i]
        if cur and not flagged[i] and i - cur[-1] > max_gap:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)

    events = []
    for run in runs:
        peak = max(run, key=lambda i: abs(z[i]))
        if len(run) < 2 and abs(z[peak]) < z_single:
            continue
        end_t = times[run[-1]] + pd.Timedelta(minutes=10)
        events.append(Event(
            id="",
            sensor=sensor.id, room=sensor.room, kind=sensor.kind, unit=sensor.unit,
            direction="above" if z[peak] > 0 else "below",
            start=times[run[0]].strftime("%H:%M"), end=end_t.strftime("%H:%M"),
            peak_time=times[peak].strftime("%H:%M"),
            observed=round(float(y[peak]), 2), expected=round(float(q[peak, Q50]), 2),
            expected_low=round(float(q[peak, Q05]), 2), expected_high=round(float(q[peak, Q95]), 2),
            sigma=round(float(abs(z[peak])), 1),
            duration_min=int((run[-1] - run[0] + 1) * 10),
        ))
    return events


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def link_events(events: list[Event], slack_min: int = 20) -> None:
    """Mark events that happened at the same time in different sensors."""
    for a in events:
        a.together_with = [
            b.id for b in events
            if b.id != a.id
            and _minutes(b.start) <= _minutes(a.end) + slack_min
            and _minutes(a.start) <= _minutes(b.end) + slack_min
        ]


@dataclass
class NightScan:
    night: str  # YYYY-MM-DD
    weekday: str
    backend: str
    window: tuple[int, int]
    events: list[Event]
    series: dict[str, dict]  # sensor -> {t, y, q05, q50, q95, z}
    sensors: dict[str, dict]
    checks: list = field(default_factory=list)  # rule-based notes (checks.Check), ids C1, C2...

    @property
    def score(self) -> float:
        return max((e.sigma for e in self.events), default=0.0)

    def to_dict(self) -> dict:
        return {
            "night": self.night, "weekday": self.weekday, "backend": self.backend, "window": list(self.window),
            "score": round(self.score, 1), "n_events": len(self.events),
            "events": [e.to_dict() for e in self.events], "checks": [c.to_dict() for c in self.checks],
            "series": self.series, "sensors": self.sensors,
        }

    @staticmethod
    def from_dict(d: dict) -> "NightScan":
        evs = []
        for e in d["events"]:
            e = dict(e)
            e.pop("delta", None)
            evs.append(Event(**e))
        from .checks import Check, cold_checks

        scan = NightScan(d["night"], d["weekday"], d["backend"], tuple(d["window"]), evs, d["series"], d["sensors"])
        scan.checks = [Check(**c) for c in d["checks"]] if "checks" in d else cold_checks(scan.series, scan.sensors)
        return scan


@dataclass
class ScanConfig:
    start_hour: int = 0
    end_hour: int = 6
    context_days: int = 14
    z_event: float = 4.0
    z_single: float = 6.0


def predict_night(house: House, night: date, target: str, backend: Backend, cfg: ScanConfig):
    ctx = context_rows(house.df, night, cfg.context_days, cfg.start_hour)
    rows = night_rows(house.df, night, cfg.start_hour, cfg.end_hour)
    X_ctx = features(house, ctx, target)
    ok = X_ctx.notna().all(axis=1).to_numpy() & ctx[target].notna().to_numpy()
    X_q = features(house, rows, target).ffill().bfill()
    q = backend.predict_quantiles(X_ctx[ok], ctx[target].to_numpy()[ok], X_q, QUANTILES)
    return rows.index, rows[target].to_numpy(dtype=float), q


def scan_night(house: House, night: date, backend: Backend, sensors: list[str] | None = None,
               cfg: ScanConfig | None = None) -> NightScan:
    cfg = cfg or ScanConfig()
    events: list[Event] = []
    series: dict[str, dict] = {}
    for sid in sensors or house.sensor_ids:
        s = house.sensor(sid)
        times, y, q = predict_night(house, night, sid, backend, cfg)
        z = surprise(y, q, s.min_spread)
        events += find_events(times, y, q, z, s, z_event=cfg.z_event, z_single=cfg.z_single)
        series[sid] = {
            "t": [t.strftime("%H:%M") for t in times],
            "y": _r(y), "q05": _r(q[:, Q05]), "q50": _r(q[:, Q50]), "q95": _r(q[:, Q95]), "z": _r(z, 1),
        }
    events.sort(key=lambda e: (_minutes(e.start), -e.sigma))
    for i, e in enumerate(events, 1):
        e.id = f"E{i}"
    link_events(events)
    from .checks import cold_checks

    sensors_meta = {sid: house.sensor(sid).to_dict() for sid in series}
    return NightScan(
        night=night.isoformat(), weekday=pd.Timestamp(night).day_name(), backend=backend.name,
        window=(cfg.start_hour, cfg.end_hour), events=events, series=series,
        sensors=sensors_meta, checks=cold_checks(series, sensors_meta),
    )


def _r(a: np.ndarray, nd: int = 2) -> list[float]:
    return [round(float(v), nd) for v in a]
