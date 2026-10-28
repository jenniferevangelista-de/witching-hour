"""Planted ghosts: how often does each model notice a ghost we put there ourselves?

For a sample of real nights and sensors we fit each backend once, then score two
versions of the same night: the real readings, and the real readings plus a
planted ghost (a smooth bump of known size, time and length). The question is
whether the planted night scores higher than the real nights do.

Real nights are not guaranteed to be ghost free, so some 'clean' nights score
high for real reasons. That hurts every backend the same way.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import House
from .scanner import Q05, Q95, Backend, ScanConfig, predict_night, surprise

# Size of the planted ghost, as a multiple of the sensor's typical night-time
# wobble (median of the per-night standard deviation in the data).
STRENGTHS = (1.0, 2.0, 3.0)


def night_wobble(house: House, sid: str, nights, cfg: ScanConfig) -> float:
    vals = []
    for n in nights:
        a = pd.Timestamp(n) + pd.Timedelta(hours=cfg.start_hour)
        b = pd.Timestamp(n) + pd.Timedelta(hours=cfg.end_hour)
        v = house.df.loc[(house.df.index >= a) & (house.df.index < b), sid].to_numpy()
        if v.size > 2:
            vals.append(np.std(v))
    w = float(np.median(vals)) if vals else 1.0
    return max(w, house.sensor(sid).min_spread)


def plant(y: np.ndarray, start: int, length: int, size: float) -> np.ndarray:
    """A smooth bump (half sine) so it looks like a physical change, not a glitch."""
    out = y.copy()
    shape = np.sin(np.linspace(0, np.pi, length + 2)[1:-1])
    out[start:start + length] += size * shape
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """Probability that a planted night outscores a clean one (ties count half)."""
    pos, neg = np.asarray(pos), np.asarray(neg)
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return float(gt + 0.5 * eq)


def recall_at_fpr(pos: np.ndarray, neg: np.ndarray, fpr: float) -> float:
    thr = np.quantile(neg, 1 - fpr)
    return float((np.asarray(pos) > thr).mean())


@dataclass
class EvalResult:
    backend: str
    auc: float
    recall_fpr5: float
    recall_fpr5_by_strength: dict
    located: float  # share of detected ghosts whose loudest slot falls inside the planted window
    coverage90: float  # share of real readings inside the 5% to 95% band
    seconds: float
    n_cases: int

    def to_dict(self):
        return self.__dict__


def evaluate(house: House, backends: list[Backend], nights, sensors: list[str], cfg: ScanConfig | None = None,
             seed: int = 0) -> list[EvalResult]:
    cfg = cfg or ScanConfig()
    rng = np.random.default_rng(seed)
    n_slots = (cfg.end_hour - cfg.start_hour) * 6
    # Same planted ghosts for every backend.
    plan = []
    for n in nights:
        for sid in sensors:
            length = int(rng.integers(3, 7))  # 30 to 60 minutes
            start = int(rng.integers(0, n_slots - length))
            strength = float(rng.choice(STRENGTHS))
            sign = 1.0 if house.sensor(sid).kind in ("energy", "light") else float(rng.choice([-1.0, 1.0]))
            plan.append((n, sid, start, length, strength, sign))
    wobble = {sid: night_wobble(house, sid, nights, cfg) for sid in sensors}

    results = []
    for be in backends:
        t0 = time.time()
        clean, planted, strengths, located, inside, total = [], [], [], [], 0, 0
        for n, sid, start, length, strength, sign in plan:
            s = house.sensor(sid)
            _, y, q = predict_night(house, n, sid, be, cfg)
            z0 = np.abs(surprise(y, q, s.min_spread))
            y1 = plant(y, start, length, sign * strength * wobble[sid])
            z1 = np.abs(surprise(y1, q, s.min_spread))
            clean.append(z0.max())
            planted.append(z1.max())
            strengths.append(strength)
            located.append(start <= int(np.argmax(z1)) < start + length)
            inside += int(((y >= q[:, Q05]) & (y <= q[:, Q95])).sum())
            total += y.size
        clean, planted, strengths, located = map(np.asarray, (clean, planted, strengths, located))
        thr = np.quantile(clean, 0.95)
        hit = planted > thr
        results.append(EvalResult(
            backend=be.name,
            auc=round(auc(planted, clean), 3),
            recall_fpr5=round(float(hit.mean()), 3),
            recall_fpr5_by_strength={str(k): round(float(hit[strengths == k].mean()), 3) for k in STRENGTHS
                                     if (strengths == k).any()},
            located=round(float(located[hit].mean()) if hit.any() else 0.0, 3),
            coverage90=round(inside / max(total, 1), 3),
            seconds=round(time.time() - t0, 1),
            n_cases=len(plan),
        ))
    return results
