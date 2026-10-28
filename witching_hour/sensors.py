"""Sensor catalog: what each column means and how loud it is allowed to be."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# Smallest half-width of the "expected" band per kind. Without a floor, a sensor
# that is flat in the context (lights at 0 Wh every night) would turn any blip
# into an infinite surprise.
MIN_SPREAD = {
    "temperature": 0.15,  # degrees C
    "humidity": 0.8,  # % relative humidity
    "energy": 10.0,  # Wh per 10 minutes
    "light": 5.0,  # Wh per 10 minutes (or 0/1 for on/off lights)
    "other": 0.0,
}

UNITS = {"temperature": "°C", "humidity": "%", "energy": "Wh", "light": "Wh", "other": ""}


@dataclass(frozen=True)
class Sensor:
    id: str
    room: str
    kind: str  # temperature | humidity | energy | light | other
    unit: str
    min_spread: float

    @property
    def label(self) -> str:
        names = {
            "temperature": "temperature",
            "humidity": "humidity",
            "energy": "appliance energy",
            "light": "lights",
            "other": "reading",
        }
        return f"{self.room} {names[self.kind]}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label
        return d


def make_sensor(sensor_id: str, room: str, kind: str, unit: str | None = None) -> Sensor:
    return Sensor(sensor_id, room, kind, unit if unit is not None else UNITS[kind], MIN_SPREAD[kind])


# UCI "Appliances energy prediction" (Candanedo, Feldheim & Deramaix, 2017).
_UCI_ROOMS = {
    1: "kitchen",
    2: "living room",
    3: "laundry room",
    4: "office",
    5: "bathroom",
    7: "ironing room",
    8: "teenager's room",
    9: "parents' room",
}

UCI_SENSORS: list[Sensor] = (
    [make_sensor("Appliances", "house", "energy"), make_sensor("lights", "house", "light")]
    + [make_sensor(f"T{i}", room, "temperature") for i, room in _UCI_ROOMS.items()]
    + [make_sensor(f"RH_{i}", room, "humidity") for i, room in _UCI_ROOMS.items()]
)

# Outdoor readings. They describe the night, they never haunt it.
UCI_CONTEXT = ["T6", "RH_6", "T_out", "Press_mm_hg", "RH_out", "Windspeed", "Visibility", "Tdewpoint"]

_KIND_PATTERNS = [
    ("temperature", re.compile(r"temp", re.I)),
    ("humidity", re.compile(r"humid", re.I)),
    ("light", re.compile(r"^light\.|light|lux|illuminance", re.I)),
    ("energy", re.compile(r"power|energy|consumption|watt", re.I)),
]
_NOISE_WORDS = re.compile(r"(temperature|temp|humidity|humid|power|energy|consumption|illuminance|lux|sensor)", re.I)


def infer_sensor(entity_id: str) -> Sensor:
    """Best effort catalog entry for a Home Assistant entity id such as sensor.kitchen_temperature."""
    kind = "other"
    for k, pat in _KIND_PATTERNS:
        if pat.search(entity_id):
            kind = k
            break
    name = entity_id.split(".", 1)[-1]
    room = _NOISE_WORDS.sub("", name).replace("_", " ").strip() or name
    room = re.sub(r"\s+", " ", room)
    unit = "on/off" if entity_id.startswith(("light.", "switch.")) else None
    spread = 0.5 if unit == "on/off" else None
    s = make_sensor(entity_id, room, kind, unit)
    if spread is not None:
        s = Sensor(s.id, s.room, s.kind, s.unit, spread)
    return s
