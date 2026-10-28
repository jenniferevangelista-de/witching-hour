"""Two narrators for one night: the Medium and the Skeptic.

Both run on a local open-weight model through Ollama (Gemma by default). Both get
the same list of events and nothing else. Every sentence they write must cite an
event id, and every number in a sentence must match a number in the cited events.
Sentences that fail are dropped, and the model gets one more try with feedback.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field

from . import tracing
from .scanner import Event, NightScan

DEFAULT_MODEL = os.environ.get("WH_MODEL", "gemma4:e4b")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")

PHENOMENA = {
    ("temperature", "below"): "a cold spot",
    ("temperature", "above"): "a warmth with no source",
    ("humidity", "above"): "breath on the glass",
    ("humidity", "below"): "the air drying out",
    ("energy", "above"): "the machines waking up",
    ("energy", "below"): "the house going too quiet",
    ("light", "above"): "lights coming on",
    ("light", "below"): "lights going out",
    ("other", "above"): "a reading climbing",
    ("other", "below"): "a reading falling",
}

# The ghost-hunting crew. Each narrator is a character with a voice of its own.
CREW = {
    "medium": {"name": "Luna", "role": "the Medium",
               "look": "a tiny kawaii sugar-skull ghost with a marigold crown and a glowing crystal ball"},
    "skeptic": {"name": "Dr. Bigotes", "role": "the Skeptic",
                "look": "a kawaii black cat scientist with round glasses, a lab coat, a flashlight and a clipboard"},
    "family": {"name": "Xochi", "role": "the Night Watch",
               "look": "a gentle kawaii xoloitzcuintli, the dog that guides souls on Día de los Muertos, with a lantern"},
}

_GROUNDING = (
    "Rules you never break:\n"
    "1. Use ONLY the events{checks} in the list. Do not invent rooms, people, pets, devices, sounds or numbers.\n"
    "2. Every sentence cites at least one {ids} in its `cites` list.\n"
    "3. When you write a time, temperature, humidity or energy value, copy it exactly as it appears "
    "(for example 03:20 or 21.4 °C). Do not round, convert or estimate numbers.\n"
)

MODES = {
    "medium": {
        "temperature": 0.85,
        "system": (
            "You are Luna, the Medium: " + CREW["medium"]["look"] + ". On Halloween and Día de los Muertos you "
            "float through houses at night and read what their sensors felt. You speak in the first person, in a "
            "whispery, dramatic voice, and you love suspense: slow build-up, a chill, then the moment the presence "
            "arrives. Make the reader shiver, cute-creepy, never gory or cruel. Call the readings what you feel them "
            "to be: a cold breath, a presence, the machines waking, the air thickening.\n"
            + _GROUNDING.format(checks="", ids="event id") +
            "4. Write 4 to 7 sentences, in time order, and a title of at most 6 words."
        ),
    },
    "family": {
        "temperature": 0.3,
        "system": (
            "You are Xochi, the Night Watch: " + CREW["family"]["look"] + ". You keep watch over the house all night "
            "for the family of an older person who lives there alone, and every morning you write them a short, warm "
            "note in the first person, signed with your paw. Plain, kind English for someone reading on a phone "
            "before work. No technical words (never say sigma, quantile or model).\n"
            + _GROUNDING.format(checks=" and checks", ids="event or check id (E1, C1...)") +
            "4. Never diagnose and never claim someone fell, is ill or is in danger. Describe what the sensors showed.\n"
            "5. If a check says a room stayed below 18.0 °C, say so and that the WHO recommends at least 18 °C "
            "indoors in cold seasons, citing that check.\n"
            "6. If something stands out, end with one gentle, practical suggestion (a phone call, checking the "
            "heating), citing what it comes from. If nothing stands out, say the night looked calm.\n"
            "7. Write 2 to 5 sentences and a title of at most 6 words."
        ),
    },
    "skeptic": {
        "temperature": 0.35,
        "system": (
            "You are Dr. Bigotes, the Skeptic: " + CREW["skeptic"]["look"] + ". Luna says the house was haunted "
            "last night. You read the same sensor events and explain, in the first person, what most likely happened "
            "instead. You are dry, a little grumpy, very kind underneath, and you sometimes start with 'Hmph.' You "
            "love thermostats, kettles and open windows, and you never believe in ghosts without data.\n"
            + _GROUNDING.format(checks="", ids="event id") +
            "4. Use `together_with` as evidence: events at the same time in the same room usually share one cause "
            "(humidity and temperature rising together in a bathroom suggests a shower).\n"
            "5. Say 'probably' or 'maybe' when you are guessing. Never claim certainty.\n"
            "6. Write 3 to 6 sentences and a title of at most 6 words."
        ),
    },
}

STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "cites": {"type": "array", "items": {"type": "string"}}},
                "required": ["text", "cites"],
            },
        },
    },
    "required": ["title", "sentences"],
}


# ---------------------------------------------------------------- payload


def fmt(v: float, unit: str) -> str:
    if unit in ("Wh",):
        return f"{v:.0f} {unit}"
    if unit == "on/off":
        return "on" if v >= 0.5 else "off"
    return f"{v:.1f} {unit}".strip()


def event_card(e: Event) -> dict:
    return {
        "id": e.id,
        "room": e.room,
        "sensor": {"temperature": "temperature", "humidity": "humidity", "energy": "appliance energy",
                   "light": "lights"}.get(e.kind, e.kind),
        "what_it_looks_like": PHENOMENA.get((e.kind, e.direction), "a strange reading"),
        "start": e.start,
        "end": e.end,
        "peak_time": e.peak_time,
        "duration_minutes": e.duration_min,
        "observed": fmt(e.observed, e.unit),
        "expected": fmt(e.expected, e.unit),
        "expected_range": f"{fmt(e.expected_low, e.unit)} to {fmt(e.expected_high, e.unit)}",
        "direction": e.direction,
        "strength_sigma": e.sigma,
        "together_with": e.together_with,
    }


def check_card(c) -> dict:
    return {
        "id": c.id, "room": c.room, "rule": c.rule, "from": c.start, "to": c.end, "minutes": c.minutes,
        "coldest": f"{c.coldest:.1f} °C", "coldest_time": c.coldest_time,
        "why_it_matters": "WHO recommends at least 18 °C indoors in cold seasons",
    }


def night_payload(scan: NightScan, max_events: int = 8, with_checks: bool = False) -> dict:
    events = sorted(scan.events, key=lambda e: -e.sigma)[:max_events]
    events.sort(key=lambda e: e.start)
    out = {
        "night": f"{scan.weekday} {scan.night}, from {scan.window[0]:02d}:00 to {scan.window[1]:02d}:00",
        "how_expected_was_computed": "TabPFN read the previous 14 days of this house and predicted a range for every 10 minutes.",
        "events": [event_card(e) for e in events],
    }
    if with_checks:
        out["checks"] = [check_card(c) for c in scan.checks[:6]]
    return out


# ---------------------------------------------------------------- validation

_NUM = re.compile(r"(?<![\w.])(\d{1,2}):(\d{2})\b|(?<![\w.])(\d+(?:[.,]\d+)?)")


def allowed_numbers(items: list, night: str | None = None,
                    extra: list[float] | None = None) -> tuple[set[str], list[float]]:
    """Times and values a sentence may quote, from the events or checks it cites."""
    times: set[str] = set()
    values: list[float] = list(extra or [])
    for it in items:
        ts, vs = it.facts()
        for t in ts:
            h, m = int(t[:2]), int(t[3:])
            times.add(f"{h:02d}:{m:02d}")
            times.add(f"{h}:{m:02d}")
            values += [h, h % 12 or 12]
        values += vs
    if night:
        y, mth, d = night.split("-")
        values += [int(y), int(mth), int(d)]
    return times, values


def check_sentence(text: str, cites: list[str], events_by_id: dict[str, Event], night: str | None = None,
                   window: tuple[int, int] = (0, 6)) -> str | None:
    """None if the sentence is grounded, otherwise the reason it is not."""
    valid = [c for c in cites if c in events_by_id]
    if not valid:
        return "cites no known event or check"
    extra = [h for w in window for h in (w, w % 12 or 12)]
    times, values = allowed_numbers([events_by_id[c] for c in valid], night, extra)
    times |= {f"{w:02d}:00" for w in window} | {f"{w}:00" for w in window}
    for m in _NUM.finditer(text):
        if m.group(1) is not None:
            t = f"{int(m.group(1))}:{m.group(2)}"
            if t not in times and f"{int(m.group(1)):02d}:{m.group(2)}" not in times:
                return f"time {m.group(0)} is not in the cited events"
        else:
            v = float(m.group(3).replace(",", "."))
            if not any(abs(v - a) <= max(0.11, 0.02 * abs(a)) for a in values):
                return f"number {m.group(3)} is not in the cited events"
    return None


@dataclass
class Sentence:
    text: str
    cites: list[str]


@dataclass
class Story:
    night: str
    mode: str
    model: str
    title: str
    sentences: list[Sentence]
    rejected: list[dict] = field(default_factory=list)
    attempts: int = 1

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verified"] = len(self.sentences)
        d["dropped"] = len(self.rejected)
        return d


_INLINE_CITE = re.compile(r"\s*[\(\[]\s*['\"]?[EC]\d+['\"]?(?:\s*,\s*['\"]?[EC]\d+['\"]?)*\s*[\)\]]")
_QUOTED_VALUE = re.compile(r"\"(\d[^\"]{0,12})\"")


def clean_text(text: str) -> str:
    """Cosmetic only: drop inline citation markers (the page shows chips), quotes around
    values, and add the final period a small model sometimes forgets."""
    t = _INLINE_CITE.sub("", text)
    t = _QUOTED_VALUE.sub(lambda m: m.group(1), t).replace(" .", ".").replace(" ,", ",").strip()
    if t and t[-1] not in ".!?":
        t += "."
    return t


def validate(raw: dict, scan: NightScan) -> tuple[list[Sentence], list[dict]]:
    by_id = {e.id: e for e in scan.events} | {c.id: c for c in scan.checks}
    kept, rejected = [], []
    for s in raw.get("sentences", []):
        text = str(s.get("text", "")).strip()
        cites = [str(c).strip() for c in (s.get("cites") or [])]
        if not text:
            continue
        why = check_sentence(text, cites, by_id, scan.night, tuple(scan.window))
        if why is None:
            kept.append(Sentence(clean_text(text), [c for c in cites if c in by_id]))
        else:
            rejected.append({"text": text, "cites": cites, "reason": why})
    return kept, rejected


# ---------------------------------------------------------------- narrators


class OllamaChat:
    def __init__(self, model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST, timeout: int = 600, seed: int = 7):
        self.model, self.host, self.timeout, self.seed = model, host.rstrip("/"), timeout, seed

    def available(self) -> bool:
        import requests

        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            names = {m.get("name") for m in r.json().get("models", [])}
            return r.ok and (self.model in names or f"{self.model}:latest" in names)
        except Exception:
            return False

    def __call__(self, messages: list[dict], schema: dict | None = None, temperature: float = 0.5) -> str:
        import requests

        body = {
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "seed": self.seed, "num_ctx": 8192},
        }
        if schema is not None:
            body["format"] = schema
        with tracing.span("gen_ai.chat", f"chat {self.model}", **{
                "gen_ai.operation.name": "chat", "gen_ai.system": "ollama", "gen_ai.request.model": self.model,
                "gen_ai.request.temperature": temperature}) as s:
            r = requests.post(f"{self.host}/api/chat", json=body, timeout=self.timeout)
            r.raise_for_status()
            d = r.json()
            tracing.set_data(s, **{
                "gen_ai.response.model": d.get("model", self.model),
                "gen_ai.usage.input_tokens": d.get("prompt_eval_count", 0),
                "gen_ai.usage.output_tokens": d.get("eval_count", 0),
                "gen_ai.usage.total_tokens": d.get("prompt_eval_count", 0) + d.get("eval_count", 0),
                "ollama.eval_seconds": round(d.get("eval_duration", 0) / 1e9, 2),
            })
        return d["message"]["content"]


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def narrate(scan: NightScan, mode: str, chat=None, model: str = DEFAULT_MODEL, retries: int = 1) -> Story:
    """Ask the local model for a story, keep only grounded sentences."""
    with tracing.agent_transaction(f"narrate {mode}", **{"witching_hour.mode": mode,
                                                       "witching_hour.events": len(scan.events)}) as t:
        story = _narrate(scan, mode, chat, model, retries)
        tracing.set_data(t, **{"witching_hour.verified": len(story.sentences),
                               "witching_hour.dropped": len(story.rejected), "witching_hour.attempts": story.attempts})
        return story


def build_messages(scan: NightScan, mode: str) -> list[dict]:
    """The exact prompt a narrator gets (also used to build fine-tuning data)."""
    payload = night_payload(scan, with_checks=(mode == "family"))
    return [
        {"role": "system", "content": MODES[mode]["system"]},
        {"role": "user", "content": "Here is the night, as JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=1)
         + "\n\nAnswer with JSON: {\"title\": str, \"sentences\": [{\"text\": str, \"cites\": [event ids]}]}"},
    ]


def _narrate(scan: NightScan, mode: str, chat, model: str, retries: int) -> Story:
    if not scan.events and not (mode == "family" and scan.checks):
        return quiet_night(scan, mode, model)
    chat = chat or OllamaChat(model)
    cfg = MODES[mode]
    messages = build_messages(scan, mode)
    best: Story | None = None
    for attempt in range(1, retries + 2):
        raw = _parse_json(chat(messages, schema=STORY_SCHEMA, temperature=cfg["temperature"]))
        kept, rejected = validate(raw, scan)
        story = Story(scan.night, mode, getattr(chat, "model", model), str(raw.get("title", "")).strip() or "Untitled",
                      kept, rejected, attempt)
        if best is None or len(kept) > len(best.sentences):
            best = story
        if not rejected and len(kept) >= (2 if mode == "family" else 3):
            break
        if attempt <= retries:
            notes = "\n".join(f"- \"{r['text']}\": {r['reason']}" for r in rejected) or "- too few sentences"
            messages += [
                {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                {"role": "user", "content": "Some sentences broke the rules and were removed:\n" + notes
                 + "\nRewrite the whole story. Copy numbers and times exactly from the events, and cite an event "
                   "id in every sentence."},
            ]
    best.attempts = attempt
    return best


def template_story(scan: NightScan, mode: str) -> Story:
    """Deterministic narrator with no model. Used in tests and as a fallback."""
    if mode == "family":
        return template_family(scan)
    if not scan.events:
        return quiet_night(scan, mode, "template")
    out = []
    for e in sorted(scan.events, key=lambda e: e.start)[:6]:
        obs, exp = fmt(e.observed, e.unit), fmt(e.expected, e.unit)
        if mode == "medium":
            text = (f"At {e.start}, I felt {PHENOMENA.get((e.kind, e.direction), 'something')} in the {e.room}: "
                    f"{obs}, when the house expected about {exp}.")
        else:
            text = (f"The {e.room} {event_card(e)['sensor']} went {e.direction} the expected range from {e.start} "
                    f"to {e.end}, peaking at {obs} against an expected {exp}.")
        out.append(Sentence(text, [e.id]))
    title = "Something stirred" if mode == "medium" else "Probably nothing supernatural"
    return Story(scan.night, mode, "template", title, out)


def template_family(scan: NightScan) -> Story:
    out = []
    for e in sorted(scan.events, key=lambda e: -e.sigma)[:2]:
        out.append(Sentence(f"The {event_card(e)['sensor']} in the {e.room} was unusual from {e.start} to {e.end}, "
                            f"reaching {fmt(e.observed, e.unit)}.", [e.id]))
    for c in scan.checks[:2]:
        out.append(Sentence(f"The {c.room} stayed below 18 °C from {c.start} to {c.end}, down to {c.coldest:.1f} °C, "
                            f"and the WHO recommends at least 18 °C indoors in cold seasons.", [c.id]))
    if not out:
        return quiet_night(scan, "family", "template")
    return Story(scan.night, "family", "template", "This morning's note", out)


def quiet_night(scan: NightScan, mode: str, model: str) -> Story:
    text = {"medium": "I listened all night, and the house did not whisper once.",
            "family": "I kept watch all night. The night looked calm: every reading stayed inside its usual range."}.get(
        mode, "Hmph. Every reading stayed inside its expected range.")
    return Story(scan.night, mode, model, "A quiet night", [Sentence(text, [])])
