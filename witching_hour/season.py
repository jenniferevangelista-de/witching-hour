"""The season report: Ultramarine reads every case file and looks for patterns.

A pile of documents (one per haunted or cold night: apparitions, cold rooms and
what the crew wrote) goes to Ultramarine 1 Flash from Paper Instruments, called
with the plain OpenAI-style chat completions API. It must answer in JSON and cite
the nights each finding comes from; findings that cite a night that does not
exist are dropped. The run's real cost is computed from the token counts.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .agent import Haunting

API = "https://api.paperinstruments.com/v1/chat/completions"
MODEL = "ultramarine-1-flash"
PRICE_PER_M = {"input": 0.15, "cached_input": 0.03, "output": 0.50}  # USD, paperinstruments.com/ultramarine

SYSTEM = (
    "You are the archivist of the Witching Hour ghost-hunting crew. You read the case files of one real house "
    "(sensor logs between midnight and 6 AM, January to May 2016) and write the season report: 4 to 6 findings "
    "about patterns across nights (what keeps coming back, at what time, in which room, and the most likely ordinary "
    "cause). Use only the case files. Every finding must list the nights (YYYY-MM-DD) it is based on. Copy numbers "
    "exactly. Answer only with JSON: {\"title\": str, \"findings\": [{\"text\": str, \"nights\": [str]}]}."
)


def case_files(data_dir: str | Path) -> list[dict]:
    h = Haunting(data_dir)
    docs = []
    for n in h.nights:
        if not n["n_events"] and not n.get("n_cold"):
            continue
        scan = h.night(n["night"])
        doc = {
            "night": scan.night, "weekday": scan.weekday,
            "apparitions": [f"{e.room} {e.kind} {e.direction} {e.start}-{e.end}, observed {e.observed} {e.unit}, "
                            f"expected {e.expected} {e.unit}" for e in scan.events],
            "cold_rooms": [f"{c.room} below 18 °C {c.start}-{c.end}, coldest {c.coldest} °C" for c in scan.checks],
        }
        for mode in ("medium", "skeptic", "family"):
            st = h.story(scan.night, mode)
            if st:
                doc[mode] = " ".join(s["text"] for s in st["sentences"])
        docs.append(doc)
    return docs


def cost(usage: dict) -> float:
    cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
    fresh = (usage.get("prompt_tokens") or 0) - cached
    return round((fresh * PRICE_PER_M["input"] + cached * PRICE_PER_M["cached_input"]
                  + (usage.get("completion_tokens") or 0) * PRICE_PER_M["output"]) / 1e6, 6)


def keep_grounded(report: dict, known_nights: set[str]) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for f in report.get("findings", []):
        nights = [d for d in f.get("nights", []) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d))]
        if nights and all(d in known_nights for d in nights):
            kept.append({"text": str(f.get("text", "")).strip(), "nights": nights})
        else:
            dropped.append(f)
    return kept, dropped


def season_report(data_dir: str | Path, api_key: str | None = None) -> dict:
    import requests

    key = api_key or os.environ.get("PAPERINSTRUMENTS_API_KEY")
    if not key:
        raise RuntimeError("PAPERINSTRUMENTS_API_KEY is not set")
    docs = case_files(data_dir)
    body = {"model": MODEL, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Case files, one JSON object per night:\n" + "\n".join(json.dumps(d, ensure_ascii=False) for d in docs)},
    ], "max_completion_tokens": 4000}
    r = requests.post(API, headers={"Authorization": f"Bearer {key}"}, json=body, timeout=300)
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    report = json.loads(m.group(0) if m else text)
    kept, dropped = keep_grounded(report, {d["night"] for d in docs})
    usage = data.get("usage") or {}
    return {
        "title": report.get("title", "The season report"), "findings": kept, "dropped": len(dropped),
        "model": f"{MODEL} (Paper Instruments)", "case_files": len(docs), "usage": usage, "cost_usd": cost(usage),
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
