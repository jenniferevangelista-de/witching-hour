"""Web app. Locally it can ask your Ollama model live. On the public demo it only
replays scans and stories that the same pipeline computed ahead of time."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import time
from collections import defaultdict, deque

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth
from .agent import Haunting, investigate
from .narrator import DEFAULT_MODEL, OllamaChat

STATIC = Path(__file__).parent / "static"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def data_dir() -> Path:
    return Path(os.environ.get("WH_DATA", "demo_data"))


def live_enabled() -> bool:
    return os.environ.get("WH_LIVE", "1") == "1"


app = FastAPI(title="Witching Hour", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
auth.install(app)  # Auth0 login for the family room, home install only
_haunting: dict[str, Haunting] = {}


def haunting() -> Haunting:
    key = str(data_dir())
    if key not in _haunting:
        _haunting[key] = Haunting(key)
    return _haunting[key]


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    h = haunting()
    return {
        "ok": True,
        "nights": len(h.nights),
        "live": live_enabled(),
        "commit": os.environ.get("RENDER_GIT_COMMIT", "")[:7],
    }


@app.get("/api/nights")
def nights():
    return haunting().index


@app.get("/api/nights/{night}")
def night(night: str):
    if not DATE.match(night):
        raise HTTPException(400, "date must be YYYY-MM-DD")
    h = haunting()
    scan = h.night(night)
    if scan is None:
        raise HTTPException(404, "no scan for that night")
    out = scan.to_dict()
    out["stories"] = {m: h.story(night, m) for m in ("medium", "skeptic", "family") if h.story(night, m)}
    for m, st in out["stories"].items():
        if (data_dir() / "audio" / f"{night}.{m}.mp3").exists():
            st["audio"] = f"/audio/{night}.{m}.mp3"
    from .ouija import template_message

    op = data_dir() / "ouija" / f"{night}.json"
    out["ouija"] = json.loads(op.read_text(encoding="utf-8")) if op.exists() else template_message(scan)
    return out


AUDIO = re.compile(r"^(\d{4}-\d{2}-\d{2}\.(medium|skeptic|family)|seance-[0-9a-f]{10})\.mp3$")


@app.get("/api/seance/voices")
def seance_voices():
    """The séance's fixed lines that were voiced ahead of time: {normalised text: {file, who, voice, text}}."""
    p = data_dir() / "audio" / "seance_manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


@app.get("/audio/{name}", include_in_schema=False)
def audio(name: str):
    p = data_dir() / "audio" / name
    if not AUDIO.match(name) or not p.exists():
        raise HTTPException(404, "no audio")
    return FileResponse(p, media_type="audio/mpeg")


def _read_json(name: str, default):
    p = data_dir() / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


@app.get("/api/agent-runs")
def agent_runs():
    return _read_json("agent_runs.json", [])


@app.get("/api/tonight")
def tonight():
    return _read_json("tonight.json", {})


@app.get("/api/bakeoff")
def bakeoff():
    return _read_json("bakeoff.json", {})


@app.get("/api/fieldwork")
def fieldwork():
    return _read_json("fieldwork.json", {})


EXTRAS = {"season_report", "atlas_memory", "tiger_store", "mastra_runs", "tinker"}


@app.get("/api/extra/{name}")
def extra(name: str):
    if name not in EXTRAS:
        raise HTTPException(404, "unknown")
    return _read_json(f"{name}.json", {})


@app.get("/api/eval")
def eval_results():
    return _read_json("eval.json", {})


# ---------------------------------------------------------------- PARANORMAL.exe spirit sessions

from . import spirits  # noqa: E402
from .providers import describe, make_chat  # noqa: E402

_store = None
_hits: dict[str, deque] = defaultdict(deque)
_day: deque = deque()
PER_IP_HOUR = int(os.environ.get("WH_SPIRIT_PER_IP_HOUR", "40"))
PER_DAY = int(os.environ.get("WH_SPIRIT_PER_DAY", "600"))


def store():
    global _store
    if _store is None:
        uri = os.environ.get("MONGODB_URI")
        try:
            _store = spirits.AtlasStore(uri) if uri else spirits.MemoryStore()
        except Exception:
            _store = spirits.MemoryStore()
    return _store


def throttle(request: Request) -> None:
    """The public demo spends a small provider credit: keep it for real visitors."""
    now = time.time()
    # the proxy appends the address it saw, so the last entry is the one a visitor cannot forge
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[-1].strip()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    while _day and now - _day[0] > 86400:
        _day.popleft()
    if len(q) >= PER_IP_HOUR or len(_day) >= PER_DAY:
        raise HTTPException(429, "The spirits are tired. Try again later.")
    q.append(now)
    _day.append(now)


class NewSession(BaseModel):
    investigation: str = Field(default="recording", max_length=80)
    evidence: list[dict] = Field(default_factory=list, max_length=spirits.MAX_EVIDENCE)
    archetype: str | None = None
    context: str = Field(default="", max_length=200)


class SpiritQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=200)


@app.get("/api/spirits")
def spirit_info():
    return {"archetypes": {k: {x: v[x] for x in ("title", "personality", "style")} for k, v in spirits.ARCHETYPES.items()},
            "model": describe(make_chat())}


@app.post("/api/sessions", dependencies=[Depends(throttle)])
def new_session(body: NewSession):
    chat = make_chat()
    s = spirits.summon(body.investigation, body.evidence, chat=chat, archetype=body.archetype, context=body.context)
    store().save(s)
    return {"session_id": s.session_id, "spirit": {**spirits.asdict(s.spirit), "title": s.spirit.title},
            "evidence": s.evidence, "model": describe(chat)}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    s = store().load(sid)
    if s is None:
        raise HTTPException(404, "no such session")
    return s.to_dict()


@app.post("/api/sessions/{sid}/ask", dependencies=[Depends(throttle)])
def ask_spirit(sid: str, q: SpiritQuestion):
    s = store().load(sid)
    if s is None:
        raise HTTPException(404, "no such session")
    if s.state != "open":
        raise HTTPException(409, "the session is closed")
    out = spirits.ask(s, q.question, chat=make_chat())
    store().save(s)
    return out


class MoreEvidence(BaseModel):
    evidence: list[dict] = Field(max_length=10)


@app.post("/api/sessions/{sid}/evidence")
def more_evidence(sid: str, body: MoreEvidence):
    s = store().load(sid)
    if s is None:
        raise HTTPException(404, "no such session")
    added = spirits.add_evidence(s, body.evidence)
    store().save(s)
    return {"added": added, "evidence": len(s.evidence)}


MEDIA = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)?\.(mp4|mp3|png|jpg)$")


@app.get("/media/{name:path}", include_in_schema=False)
def media(name: str):
    p = data_dir() / "media" / name
    if not MEDIA.match(name) or not p.exists():
        raise HTTPException(404, "no media")
    kind = {"mp4": "video/mp4", "mp3": "audio/mpeg", "png": "image/png", "jpg": "image/jpeg"}[name.rsplit(".", 1)[1]]
    return FileResponse(p, media_type=kind)


@app.post("/api/sessions/{sid}/close")
def close_session(sid: str):
    s = store().load(sid)
    if s is None:
        raise HTTPException(404, "no such session")
    out = spirits.close(s)
    store().save(s)
    return out


@app.get("/api/demo/cases")
def demo_cases():
    return _read_json("cases.json", {"cases": []})


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=300)


@app.post("/api/ask", dependencies=[Depends(auth.require_family)])
def ask(q: Question):
    if not live_enabled():
        return JSONResponse(status_code=503, content={
            "detail": "This public demo has no model attached, on purpose: a house's night logs are private. "
                      "Run Witching Hour on your own machine to ask live questions. The recorded investigations "
                      "below were made by the same agent with Gemma running locally."})
    chat = OllamaChat(os.environ.get("WH_MODEL", DEFAULT_MODEL))
    if not chat.available():
        return JSONResponse(status_code=503, content={
            "detail": f"Ollama model {chat.model} is not running. Start it with: ollama pull {chat.model}"})
    return investigate(q.question, haunting(), chat).to_dict()
