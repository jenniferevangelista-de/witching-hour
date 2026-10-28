"""Web app. Locally it can ask your Ollama model live. On the public demo it only
replays scans and stories that the same pipeline computed ahead of time."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

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
    return out


AUDIO = re.compile(r"^\d{4}-\d{2}-\d{2}\.(medium|skeptic|family)\.mp3$")


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


@app.get("/api/eval")
def eval_results():
    return _read_json("eval.json", {})


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=300)


@app.post("/api/ask")
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
