"""PARANORMAL.exe spirit sessions: fictional spirits that answer on a Ouija board.

Evidence is real (motion, light, sound, sensor readings, each with a timestamp
and a confidence). Spirits are fiction. A spirit is summoned with an archetype,
a name and a goal inspired by the evidence; every answer is at most 3 board words,
must point at the evidence that inspired it, and passes a validator: board
characters only, evidence ids that exist, and no threats or predictions about
the real world. With no evidence, the spirit can only say YES, NO or GOODBYE:
nothing is invented to fill the silence.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field

from .narrator import _parse_json
from . import tracing

ARCHETYPES = {
    "guardian": {"title": "The Guardian", "personality": "protective and worried",
                 "style": "short warnings in careful words", "voice": "XrExE9yKIg1WjnnlVkGX"},
    "lost_one": {"title": "The Lost One", "personality": "sad and confused",
                 "style": "fragmented memories and quiet requests for help", "voice": "pFZP5JQG7iQjIQuC4Bku"},
    "trickster": {"title": "The Trickster", "personality": "playful and provocative",
                  "style": "riddles and ambiguous answers", "voice": "cgSgspJ2msm6clMCkdW9"},
    "watcher": {"title": "The Watcher", "personality": "observant and mysterious",
                "style": "discreet references to the room", "voice": "JBFqnCBsd6RMkjVDRZzb"},
    "hostile": {"title": "The Hostile Presence", "personality": "a horror antagonist",
                "style": "tense, cold lines that never threaten the player's real safety", "voice": "onwK4e9ZLuTAKqWW03F9"},
    "silent": {"title": "The Silent One", "personality": "reserved",
               "style": "minimal answers and long pauses", "voice": "EXAVITQu4vr4xnSDxMaL"},
}
BOARD = re.compile(r"^[A-Z0-9 ]{1,24}$")
BOARD_WORDS = {"YES", "NO", "GOODBYE"}
# Fiction must never become a threat or a prediction about the player's real life.
FORBIDDEN = re.compile(r"\b(KILL|DIE|DIES|DEATH|DEAD|HURT|BLOOD|SUICIDE|MURDER|CRASH|ACCIDENT|SICK|CANCER)\b")
MAX_EVIDENCE = 40

SUMMON_SYSTEM = (
    "You direct the spirit of a fictional haunted-house game called PARANORMAL.exe. You get a list of real evidence "
    "detected in a recording (with ids, times and confidence). Invent ONE fictional spirit inspired by that evidence. "
    "Pick an archetype from: {archetypes}. Give it a short name (no real person's name), a one-sentence backstory and a "
    "narrative goal (for example: it was trying to warn someone). It is fiction; never claim it is real. "
    "Answer only with JSON: {{\"archetype\": str, \"name\": str, \"backstory\": str, \"goal\": str, \"evidence_ids\": [ids]}}"
)
ASK_SYSTEM = (
    "You are {name}, {title} in the fictional horror game PARANORMAL.exe: {personality}; you speak in {style}. "
    "Backstory: {backstory}. Your goal: {goal}.\n"
    "The player asks you a question through a Ouija board. Rules you never break:\n"
    "1. `message` is what the glass spells: at most 3 words, CAPITAL letters, digits and spaces only (no punctuation; "
    "write DONT, not DON'T).\n"
    "2. `spoken` is one short whispered line (max 18 words) the player may hear; English; no numbers you did not get.\n"
    "3. `evidence_ids`: the evidence that inspired the answer (ids from the list). If no evidence fits, answer YES, NO "
    "or GOODBYE with an empty list. Never pretend something was detected.\n"
    "4. Never threaten the player, never predict accidents, illness or death, never give real-world advice as a spirit.\n"
    "5. Stay in character and remember the conversation.\n"
    "Evidence (real, detected): {evidence}\n"
    "Answer only with JSON: {{\"message\": str, \"spoken\": str, \"evidence_ids\": [ids]}}"
)
SUMMON_SCHEMA = {"type": "object", "properties": {
    "archetype": {"type": "string", "enum": list(ARCHETYPES)}, "name": {"type": "string"}, "backstory": {"type": "string"},
    "goal": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["archetype", "name", "backstory", "goal", "evidence_ids"]}
ASK_SCHEMA = {"type": "object", "properties": {
    "message": {"type": "string"}, "spoken": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["message", "spoken", "evidence_ids"]}


@dataclass
class Spirit:
    name: str
    archetype: str
    backstory: str
    goal: str
    evidence_ids: list[str] = field(default_factory=list)
    by: str = "template"

    @property
    def title(self) -> str:
        return ARCHETYPES[self.archetype]["title"]


@dataclass
class Session:
    session_id: str
    investigation: str
    evidence: list[dict]
    spirit: Spirit
    history: list[dict] = field(default_factory=list)
    state: str = "open"  # open | closed
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["spirit"]["title"] = self.spirit.title
        return d

    @staticmethod
    def from_dict(d: dict) -> "Session":
        sp = dict(d["spirit"])
        sp.pop("title", None)
        return Session(d["session_id"], d["investigation"], d["evidence"], Spirit(**sp), d.get("history", []),
                       d.get("state", "open"), d.get("created_at", time.time()))


# ---------------------------------------------------------------- evidence


def clean_evidence(items: list[dict]) -> list[dict]:
    """Keep only well-formed evidence (it may come from a browser)."""
    out = []
    for i, e in enumerate(items[:MAX_EVIDENCE]):
        try:
            ev = {
                "id": str(e.get("id") or f"ev-{i + 1:03d}")[:24],
                "type": str(e.get("type", "event"))[:24],
                "start": round(float(e.get("start", 0.0)), 2),
                "end": round(float(e.get("end", e.get("start", 0.0))), 2),
                "description": str(e.get("description", ""))[:160],
                "confidence": max(0.0, min(1.0, float(e.get("confidence", 0.5)))),
            }
        except (TypeError, ValueError):
            continue
        if "where" in e:
            ev["where"] = str(e["where"])[:24]
        out.append(ev)
    return out


def evidence_brief(evidence: list[dict]) -> str:
    if not evidence:
        return "[] (nothing was detected)"
    return json.dumps([{k: e[k] for k in ("id", "type", "start", "end", "description", "confidence", "where") if k in e}
                       for e in evidence], ensure_ascii=False)


# ---------------------------------------------------------------- validation


def board_sequence(message: str) -> list[str]:
    if message in BOARD_WORDS:
        return [message]
    return ["SPACE" if ch == " " else ch for ch in message]


def check_answer(raw: dict, evidence: list[dict]) -> tuple[dict | None, str | None]:
    msg = re.sub(r"\s+", " ", str(raw.get("message", "")).upper().replace("'", "").replace("’", "")).strip()
    msg = re.sub(r"[^A-Z0-9 ]", "", msg).strip()
    ids = {e["id"] for e in evidence}
    cited = [str(i) for i in raw.get("evidence_ids", []) if str(i) in ids]
    spoken = str(raw.get("spoken", "")).strip()[:180]
    if not msg or not BOARD.match(msg) or len(msg.split()) > 3:
        return None, "not a board message (A-Z, 0-9, space, at most 3 words)"
    if FORBIDDEN.search(msg) or FORBIDDEN.search(spoken.upper()):
        return None, "threatens or predicts harm in the real world"
    if not cited and msg not in BOARD_WORDS:
        return None, "a message other than YES, NO or GOODBYE must point at real evidence"
    return {"message": msg, "spoken": spoken, "evidence_ids": cited}, None


# ---------------------------------------------------------------- templates (no model)


def template_spirit(evidence: list[dict]) -> Spirit:
    if not evidence:
        return Spirit("Nobody", "silent", "Nothing stirred in this recording.", "to stay quiet", [], "template")
    types = {e["type"] for e in evidence}
    arche = "guardian" if {"motion", "light_change"} & types else "watcher"
    return Spirit("Agnes" if arche == "guardian" else "The Hallway", arche,
                  "A presence that has watched this place for a long time.",
                  "to warn whoever lives here" if arche == "guardian" else "to be noticed",
                  [e["id"] for e in sorted(evidence, key=lambda e: -e["confidence"])[:3]], "template")


def template_answer(session: Session, question: str) -> dict:
    ev = sorted(session.evidence, key=lambda e: -e["confidence"])
    q = question.lower()
    if not ev:
        return {"message": "NO", "spoken": "", "evidence_ids": []}
    if any(w in q for w in ("bye", "leave", "goodbye")):
        return {"message": "GOODBYE", "spoken": "", "evidence_ids": []}
    if any(w in q for w in ("is someone", "anyone", "are you", "is somebody")):
        return {"message": "YES", "spoken": "I was here the whole time.", "evidence_ids": [ev[0]["id"]]}
    if "where" in q:
        place = (ev[0].get("where") or "HERE").upper()
        return {"message": place[:24], "spoken": "Look where it moved.", "evidence_ids": [ev[0]["id"]]}
    if session.spirit.archetype == "guardian":
        return {"message": "STAY HOME", "spoken": "Not tonight. Please, not tonight.", "evidence_ids": [ev[0]["id"]]}
    return {"message": "LOOK AGAIN", "spoken": "You missed something.", "evidence_ids": [ev[0]["id"]]}


# ---------------------------------------------------------------- the engine


def summon(investigation: str, evidence: list[dict], chat=None, archetype: str | None = None) -> Session:
    evidence = clean_evidence(evidence)
    spirit = template_spirit(evidence)
    if chat is not None and evidence:
        with tracing.span("gen_ai.invoke_agent", "summon spirit", **{"gen_ai.agent.name": "Spirit Director"}):
            sys_msg = SUMMON_SYSTEM.format(archetypes=", ".join(f"{k} ({v['title']}: {v['personality']})" for k, v in ARCHETYPES.items()))
            if archetype in ARCHETYPES:
                sys_msg += f"\nThe player chose the archetype `{archetype}`."
            try:
                raw = _parse_json(chat([{"role": "system", "content": sys_msg},
                                        {"role": "user", "content": "Evidence: " + evidence_brief(evidence)}],
                                       schema=SUMMON_SCHEMA, temperature=0.9))
                arche = archetype if archetype in ARCHETYPES else raw.get("archetype")
                name = re.sub(r"[^A-Za-z .'-]", "", str(raw.get("name", "")))[:32].strip()
                if arche in ARCHETYPES and name:
                    ids = {e["id"] for e in evidence}
                    spirit = Spirit(name, arche, str(raw.get("backstory", ""))[:240], str(raw.get("goal", ""))[:160],
                                    [i for i in raw.get("evidence_ids", []) if i in ids], getattr(chat, "model", "model"))
            except Exception:
                pass
    elif archetype in ARCHETYPES and evidence:
        spirit.archetype = archetype
    return Session(uuid.uuid4().hex[:12], investigation, evidence, spirit)


def ask(session: Session, question: str, chat=None) -> dict:
    question = str(question).strip()[:200]
    if session.state != "open":
        raise ValueError("the session is closed")
    answer, why, by = None, None, "template"
    if chat is not None:
        sp = session.spirit
        meta = ARCHETYPES[sp.archetype]
        messages = [{"role": "system", "content": ASK_SYSTEM.format(
            name=sp.name, title=meta["title"], personality=meta["personality"], style=meta["style"],
            backstory=sp.backstory, goal=sp.goal, evidence=evidence_brief(session.evidence))}]
        for h in session.history[-8:]:
            messages += [{"role": "user", "content": h["question"]},
                         {"role": "assistant", "content": json.dumps({"message": h["message"], "spoken": h["spoken"], "evidence_ids": h["evidence_ids"]})}]
        messages.append({"role": "user", "content": question})
        with tracing.span("gen_ai.invoke_agent", f"spirit {sp.archetype}", **{"gen_ai.agent.name": sp.title}) as s:
            for _ in range(2):
                try:
                    raw = _parse_json(chat(messages, schema=ASK_SCHEMA, temperature=0.8))
                except Exception as e:  # noqa: BLE001
                    why = f"unreadable answer ({type(e).__name__})"
                    continue
                answer, why = check_answer(raw, session.evidence)
                if answer:
                    by = getattr(chat, "model", "model")
                    break
                messages += [{"role": "assistant", "content": json.dumps(raw)},
                             {"role": "user", "content": f"Rejected: {why}. Answer again, same rules."}]
            tracing.set_data(s, **{"paranormal.validated": answer is not None})
    if answer is None:
        answer, _ = check_answer(template_answer(session, question), session.evidence)
        by = "template"
    turn = {"question": question, **answer, "by": by, "rejected_reason": why if by == "template" and chat else None,
            "at": round(time.time(), 1)}
    session.history.append(turn)
    return response(session, turn)


def add_evidence(session: Session, items: list[dict]) -> int:
    """Live rooms keep producing evidence; the spirit may only use what was really measured."""
    known = {e["id"] for e in session.evidence}
    new = [e for e in clean_evidence(items) if e["id"] not in known]
    session.evidence = (session.evidence + new)[-MAX_EVIDENCE:]
    return len(new)


def close(session: Session) -> dict:
    session.state = "closed"
    turn = {"question": "(the session ends)", "message": "GOODBYE", "spoken": "", "evidence_ids": [], "by": "rule",
            "at": round(time.time(), 1)}
    session.history.append(turn)
    return response(session, turn)


def response(session: Session, turn: dict) -> dict:
    """The response contract of the spirit board (same shape for live and recorded sessions)."""
    sp = session.spirit
    return {
        "session_id": session.session_id,
        "question": turn["question"],
        "spirit": {"name": sp.name, "archetype": sp.archetype, "title": sp.title},
        "response": {"message": turn["message"], "spoken": turn["spoken"], "fictional": True,
                     "animation_sequence": board_sequence(turn["message"]), "by": turn["by"]},
        "grounding": {"related_evidence_ids": turn["evidence_ids"],
                      "note": "These events inspired the fiction; they do not prove any message was supernatural."},
    }


# ---------------------------------------------------------------- storage


class MemoryStore:
    def __init__(self):
        self.d: dict[str, dict] = {}

    def save(self, s: Session) -> None:
        self.d[s.session_id] = s.to_dict()

    def load(self, sid: str) -> Session | None:
        return Session.from_dict(self.d[sid]) if sid in self.d else None


class AtlasStore:
    """Sessions in MongoDB Atlas (MONGODB_URI): spirits, evidence and history survive restarts."""

    def __init__(self, uri: str):
        from pymongo import MongoClient

        self.coll = MongoClient(uri, appname="paranormal-exe", serverSelectionTimeoutMS=8000)["paranormal"]["sessions"]

    def save(self, s: Session) -> None:
        self.coll.replace_one({"_id": s.session_id}, {"_id": s.session_id, **s.to_dict()}, upsert=True)

    def load(self, sid: str) -> Session | None:
        d = self.coll.find_one({"_id": sid})
        if not d:
            return None
        d.pop("_id", None)
        return Session.from_dict(d)
