"""The investigator: a small tool-calling agent around the TabPFN scans.

The model (Gemma through Ollama by default) never sees raw sensor data. It can
only call four tools. Two of them are TabPFN-backed: the night scans and the
`expected_reading` lookup that returns TabPFN's predicted range for a moment.
The protocol is plain JSON, so any local model that follows instructions works.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import tracing
from .narrator import Story, check_card, event_card, fmt, narrate, normalize_saved_story, template_story
from .scanner import NightScan

SYSTEM = """You are Witching Hour, an investigator for one house's night-time sensor logs (midnight to 6 AM).
A model called TabPFN learned from the previous two weeks of the house what each sensor should read at each
moment. Readings far outside that expected range are "events".

You can call these tools:
- haunted_nights(month: "YYYY-MM" or null, top_k: int) -> nights ranked by their strongest event
- scan_night(date: "YYYY-MM-DD") -> the events of one night
- expected_reading(date: "YYYY-MM-DD", time: "HH:MM", sensor: str) -> what TabPFN expected vs what was observed
- tonight() -> live weather for the house's town (Google via SerpApi) and TabPFN's forecast for each room tonight
- official_warnings() -> what Dr. Bigotes read on the official weather warnings page, in a real browser
- tell_story(date: "YYYY-MM-DD", mode: "medium", "skeptic" or "family") -> a story and its source about the night
  A story with model="template" is a scripted summary, not generated model output.
  ("family" is a calm morning note for the family of someone who lives alone, with cold-room checks)

Reply with exactly one JSON object and nothing else.
To call a tool: {"tool": "scan_night", "args": {"date": "2016-03-04"}}
To finish: {"answer": "your answer in 2 to 5 sentences"}
Base every claim on tool results. Copy dates, times and values exactly as the tools return them.
Never invent events. If the tools show nothing unusual, say so."""

AGENT_SCHEMA = {
    "type": "object",
    "properties": {"tool": {"type": "string"}, "args": {"type": "object"}, "answer": {"type": "string"}},
}


class Haunting:
    """Read access to scans and stories on disk (the demo data folder)."""

    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        idx = self.dir / "index.json"
        self.index = json.loads(idx.read_text(encoding="utf-8")) if idx.exists() else {"nights": []}
        self._cache: dict[str, NightScan] = {}

    @property
    def nights(self) -> list[dict]:
        return self.index.get("nights", [])

    def night(self, date: str) -> NightScan | None:
        if date not in self._cache:
            p = self.dir / "nights" / f"{date}.json"
            if not p.exists():
                return None
            self._cache[date] = NightScan.from_dict(json.loads(p.read_text(encoding="utf-8")))
        return self._cache[date]

    def story(self, date: str, mode: str) -> dict | None:
        p = self.dir / "stories" / f"{date}.{mode}.json"
        if not p.exists():
            return None
        saved = json.loads(p.read_text(encoding="utf-8"))
        scan = self.night(date)
        return normalize_saved_story(scan, mode, saved) if scan is not None else saved

    def audio(self, date: str, mode: str) -> Path | None:
        """Only expose recordings whose manifest matches the presented story."""
        path = self.dir / "audio" / f"{date}.{mode}.mp3"
        manifest_path = self.dir / "audio" / "manifest.json"
        if not path.is_file() or not manifest_path.is_file():
            return None
        story = self.story(date, mode)
        if story is None:
            return None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(manifest, dict):
            return None
        entry = manifest.get(f"{date}.{mode}")
        if not isinstance(entry, dict):
            return None
        from .voice import script
        return path if entry.get("text") == script(story) else None


def _resolve_sensor(scan: NightScan, name: str) -> str | None:
    if name in scan.series:
        return name
    want = set(re.findall(r"[a-z]+", name.lower()))
    best, best_score = None, 0
    for sid, meta in scan.sensors.items():
        have = set(re.findall(r"[a-z]+", f"{sid} {meta.get('label', '')}".lower()))
        score = len(want & have)
        if score > best_score:
            best, best_score = sid, score
    return best


class Tools:
    def __init__(self, haunting: Haunting, chat=None):
        self.h = haunting
        self.chat = chat

    def haunted_nights(self, month: str | None = None, top_k: int = 5) -> dict:
        rows = [n for n in self.h.nights if not month or n["night"].startswith(month)]
        rows = sorted(rows, key=lambda n: -n["score"])[: max(1, min(int(top_k or 5), 10))]
        return {"nights": [{k: n[k] for k in ("night", "weekday", "score", "n_events", "headline") if k in n} for n in rows]}

    def scan_night(self, date: str) -> dict:
        scan = self.h.night(date)
        if scan is None:
            return {"error": f"no scan for {date}"}
        top = sorted(scan.events, key=lambda e: -e.sigma)[:8]
        return {"night": scan.night, "weekday": scan.weekday,
                "events": [event_card(e) for e in sorted(top, key=lambda e: e.start)],
                "cold_room_checks": [check_card(c) for c in scan.checks[:6]]}

    def expected_reading(self, date: str, time: str, sensor: str) -> dict:
        scan = self.h.night(date)
        if scan is None:
            return {"error": f"no scan for {date}"}
        sid = _resolve_sensor(scan, sensor)
        if sid is None:
            return {"error": f"unknown sensor {sensor!r}", "sensors": [m["label"] for m in scan.sensors.values()]}
        s = scan.series[sid]
        t = time[:5].rjust(5, "0")
        if t not in s["t"]:
            return {"error": f"time {time} is not a 10 minute slot between {s['t'][0]} and {s['t'][-1]}"}
        i = s["t"].index(t)
        unit = scan.sensors[sid]["unit"]
        return {
            "sensor": scan.sensors[sid]["label"], "time": t,
            "observed": fmt(s["y"][i], unit), "expected": fmt(s["q50"][i], unit),
            "expected_range_90": f"{fmt(s['q05'][i], unit)} to {fmt(s['q95'][i], unit)}",
            "sigma": abs(s["z"][i]),
        }

    def tonight(self) -> dict:
        p = self.h.dir / "tonight.json"
        if not p.exists():
            return {"error": "no forecast yet; run: witching-hour tonight"}
        d = json.loads(p.read_text(encoding="utf-8"))
        return {k: d[k] for k in ("place", "fetched_at", "source")} | {
            "outside": [{"time": h["time"], "temp_c": h["temp_c"], "weather": h["weather"]} for h in d["hours"]],
            "rooms": [{k: r[k] for k in ("room", "coldest_time", "expected", "low", "high", "p_below_18")} for r in d["rooms"]],
        }

    def official_warnings(self) -> dict:
        p = self.h.dir / "fieldwork.json"
        if not p.exists():
            return {"error": "no field trip yet; run: witching-hour fieldwork"}
        d = json.loads(p.read_text(encoding="utf-8"))
        return {k: d.get(k) for k in ("url", "fetched_at", "via", "cold_warning", "cold_lines", "excerpt")}

    def tell_story(self, date: str, mode: str = "medium") -> dict:
        mode = mode if mode in ("medium", "skeptic", "family") else "medium"
        saved = self.h.story(date, mode)
        if saved is None:
            scan = self.h.night(date)
            if scan is None:
                return {"error": f"no scan for {date}"}
            story: Story = narrate(scan, mode, chat=self.chat) if self.chat else template_story(scan, mode)
            saved = story.to_dict()
        return {"title": saved["title"], "sentences": [s["text"] for s in saved["sentences"]],
                "model": saved.get("model", "unknown"), "attempts": saved.get("attempts", 0),
                "verified": saved.get("verified", 0)}

    def call(self, name: str, args: dict) -> dict:
        fn = {"haunted_nights": self.haunted_nights, "scan_night": self.scan_night,
              "expected_reading": self.expected_reading, "tell_story": self.tell_story,
              "tonight": self.tonight, "official_warnings": self.official_warnings}.get(name)
        if fn is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return fn(**(args or {}))
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}


@dataclass
class AgentRun:
    question: str
    answer: str
    steps: list[dict] = field(default_factory=list)
    model: str = ""

    def to_dict(self) -> dict:
        return {"question": self.question, "answer": self.answer, "steps": self.steps, "model": self.model}


def _parse(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {"answer": text}


def investigate(question: str, haunting: Haunting, chat, max_steps: int = 6) -> AgentRun:
    with tracing.agent_transaction("invoke_agent Witching Hour", **{
            "gen_ai.request.model": getattr(chat, "model", "")}) as t:
        run = _investigate(question, haunting, chat, max_steps)
        tracing.set_data(t, **{"witching_hour.steps": len(run.steps),
                               "witching_hour.tools": ",".join(s["tool"] for s in run.steps)})
        return run


def _investigate(question: str, haunting: Haunting, chat, max_steps: int) -> AgentRun:
    tools = Tools(haunting, chat)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    run = AgentRun(question, "", model=getattr(chat, "model", ""))
    for _ in range(max_steps):
        out = _parse(chat(messages, schema=AGENT_SCHEMA, temperature=0.2))
        tool = out.get("tool")
        if tool:
            args = out.get("args") or {}
            with tracing.span("gen_ai.execute_tool", f"execute_tool {tool}", **{
                    "gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": tool,
                    "gen_ai.tool.type": "function"}) as s:
                result = tools.call(tool, args)
                tracing.set_data(s, **{"witching_hour.tool_error": "error" in result})
            run.steps.append({"tool": tool, "args": args, "result": result})
            messages += [
                {"role": "assistant", "content": json.dumps({"tool": tool, "args": args})},
                {"role": "user", "content": f"Result of {tool}:\n{json.dumps(result, ensure_ascii=False)}\n"
                 "Call another tool or finish with {\"answer\": ...}."},
            ]
            continue
        if out.get("answer"):
            run.answer = str(out["answer"]).strip()
            return run
        messages.append({"role": "user", "content": "Reply with one JSON object: a tool call or an answer."})
    run.answer = "I ran out of steps before I could finish the investigation."
    return run
