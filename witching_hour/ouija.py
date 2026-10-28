"""Luna's spirit board: a short Ouija message for every case file.

Fiction on top of evidence. Gemma plays the spirit Luna summons: it picks an
archetype and spells a message of at most 3 words, and it must cite the
apparition that inspired it. The validator only accepts board characters
(A-Z, 0-9, space), and any number on the board must be a time or a value of
the cited apparition (05:40 is spelled 0540). A night without apparitions gets
no invented spirit: the glass goes to NO.

The glass movement is deterministic (the page maps each character to a fixed
spot on the board); the model only chooses the words.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .narrator import PHENOMENA, _parse_json, event_card
from .scanner import NightScan

ARCHETYPES = {
    "guardian": "The Guardian: protective, short warnings",
    "watcher": "The Watcher: observant, quiet hints about the room",
    "trickster": "The Trickster: playful riddles",
    "lost_one": "The Lost One: sad, fragmented memories",
}
BOARD = re.compile(r"^[A-Z0-9 ]{2,24}$")

SYSTEM = (
    "You are the spirit that answers Luna's spirit board in a haunted-house game. It is fiction for Halloween and "
    "Día de los Muertos, built on real sensor evidence. Choose one archetype: " + "; ".join(ARCHETYPES.values()) + ".\n"
    "Spell ONE message of at most 3 words, in CAPITAL letters, digits and spaces only. It must be inspired by the "
    "apparitions in the list, and you must cite the apparition ids it comes from. If you use a number, it must be a "
    "time from a cited apparition written without the colon (05:40 becomes 0540) or one of its values without units. "
    "No threats, no real-world danger, no names of people. Answer only with JSON: "
    '{"archetype": "guardian|watcher|trickster|lost_one", "message": str, "cites": [ids], "why": str}'
)
SCHEMA = {
    "type": "object",
    "properties": {"archetype": {"type": "string", "enum": list(ARCHETYPES)}, "message": {"type": "string"},
                   "cites": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}},
    "required": ["archetype", "message", "cites", "why"],
}


def allowed_tokens(events) -> set[str]:
    out: set[str] = set()
    for e in events:
        for t in (e.start, e.end, e.peak_time):
            out |= {t.replace(":", ""), t.replace(":", "").lstrip("0") or "0"}
        for v in (e.observed, e.expected):
            out |= {str(int(round(v))), f"{v:.1f}".replace(".", "")}
    return out


def check_message(msg: dict, scan: NightScan) -> str | None:
    """None when the board message is acceptable, otherwise why not."""
    text = str(msg.get("message", "")).strip().upper()
    if not BOARD.match(text) or len(text.split()) > 3:
        return "not a board message (A-Z, 0-9, space, at most 3 words)"
    if msg.get("archetype") not in ARCHETYPES:
        return "unknown archetype"
    by_id = {e.id: e for e in scan.events}
    cited = [by_id[c] for c in msg.get("cites", []) if c in by_id]
    if not cited:
        return "cites no apparition"
    ok = allowed_tokens(cited)
    for num in re.findall(r"\d+", text):
        if num not in ok:
            return f"number {num} is not in the cited apparitions"
    return None


def template_message(scan: NightScan) -> dict:
    """Deterministic fallback: the strongest apparition, as a word and its time."""
    if not scan.events:
        return {"archetype": None, "message": "NO", "cites": [], "why": "No apparitions tonight, so no spirit answers.",
                "fiction": True, "by": "template"}
    e = max(scan.events, key=lambda e: e.sigma)
    word = {("temperature", "below"): "COLD", ("temperature", "above"): "WARM", ("humidity", "above"): "BREATH",
            ("humidity", "below"): "DRY", ("energy", "above"): "WAKE", ("energy", "below"): "HUSH",
            ("light", "above"): "LIGHT", ("light", "below"): "DARK"}.get((e.kind, e.direction), "HERE")
    return {"archetype": "watcher", "message": f"{word} {e.peak_time.replace(':', '')}", "cites": [e.id],
            "why": f"{PHENOMENA.get((e.kind, e.direction), 'something')} in the {e.room} at {e.peak_time}.",
            "fiction": True, "by": "template"}


def spirit_message(scan: NightScan, chat=None, retries: int = 1) -> dict:
    if not scan.events:
        return template_message(scan)
    if chat is None:
        return template_message(scan)
    events = sorted(scan.events, key=lambda e: -e.sigma)[:5]
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": "Apparitions, as JSON:\n" + json.dumps([event_card(e) for e in events], ensure_ascii=False, indent=1)}]
    for _ in range(retries + 1):
        try:
            raw = _parse_json(chat(messages, schema=SCHEMA, temperature=0.9))
        except Exception:
            continue
        raw["message"] = str(raw.get("message", "")).strip().upper()
        why = check_message(raw, scan)
        if why is None:
            return {"archetype": raw["archetype"], "message": raw["message"],
                    "cites": [c for c in raw["cites"] if c in {e.id for e in scan.events}],
                    "why": str(raw.get("why", "")).strip(), "fiction": True, "by": getattr(chat, "model", "model")}
        messages += [{"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                     {"role": "user", "content": f"Rejected: {why}. Try again with the same rules."}]
    return template_message(scan)


def save(night: str, msg: dict, data_dir: str | Path) -> Path:
    p = Path(data_dir) / "ouija" / f"{night}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(msg, ensure_ascii=False, indent=1), encoding="utf-8")
    return p
