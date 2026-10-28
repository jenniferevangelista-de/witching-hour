"""Plain rules that sit next to the model: a room that stays cold for too long.

The WHO Housing and Health Guidelines (2018) recommend an indoor temperature of
at least 18 °C in cold seasons, and higher for older people and young children.
A home that drops below that at night matters most for someone who lives alone.
https://www.who.int/publications/i/item/9789241550376
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

WHO_MIN_C = 18.0
WHO_SOURCE = "WHO Housing and Health Guidelines (2018): at least 18 °C indoors in cold seasons"
# Utility spaces are left out: nobody sleeps in the laundry room.
UTILITY_ROOMS = {"laundry room", "ironing room", "garage", "attic", "basement", "outside", "house"}


@dataclass
class Check:
    id: str
    sensor: str
    room: str
    rule: str
    threshold: float
    start: str
    end: str
    minutes: int
    coldest: float
    coldest_time: str

    def facts(self) -> tuple[list[str], list[float]]:
        return [self.start, self.end, self.coldest_time], [self.threshold, self.minutes, self.minutes / 60, self.coldest,
                                                           round(self.threshold - self.coldest, 2)]

    def to_dict(self) -> dict:
        return asdict(self)


def _end_time(hhmm: str) -> str:
    h, m = int(hhmm[:2]), int(hhmm[3:]) + 10
    h, m = h + m // 60, m % 60
    return f"{h:02d}:{m:02d}"


def cold_checks(series: dict, sensors: dict, threshold: float = WHO_MIN_C, min_minutes: int = 60,
                skip_rooms: set[str] = UTILITY_ROOMS) -> list[Check]:
    """Runs of at least `min_minutes` where a living-space temperature stays below `threshold`."""
    out: list[Check] = []
    for sid, meta in sensors.items():
        if meta.get("kind") != "temperature" or sid not in series:
            continue
        if meta.get("room") in skip_rooms:
            continue
        s = series[sid]
        run: list[int] = []
        for i, v in enumerate(s["y"] + [None]):
            if v is not None and v < threshold:
                run.append(i)
                continue
            if run and len(run) * 10 >= min_minutes:
                low = min(run, key=lambda j: s["y"][j])
                out.append(Check(
                    id="", sensor=sid, room=meta["room"], rule=f"stayed below {threshold:.1f} °C",
                    threshold=threshold, start=s["t"][run[0]], end=_end_time(s["t"][run[-1]]),
                    minutes=len(run) * 10, coldest=round(float(s["y"][low]), 1), coldest_time=s["t"][low],
                ))
            run = []
    out.sort(key=lambda c: (c.start, c.coldest))
    for i, c in enumerate(out, 1):
        c.id = f"C{i}"
    return out
