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

from .narrator import Story, event_card, fmt, narrate, template_story
from .scanner import NightScan

SYSTEM = """You are Witching Hour, an investigator for one house's night-time sensor logs (midnight to 6 AM).
A model called TabPFN learned from the previous two weeks of the house what each sensor should read at each
moment. Readings far outside that expected range are "events".

You can call these tools:
- haunted_nights(month: "YYYY-MM" or null, top_k: int) -> nights ranked by their strongest event
- scan_night(date: "YYYY-MM-DD") -> the events of one night
- expected_reading(date: "YYYY-MM-DD", time: "HH:MM", sensor: str) -> what TabPFN expected vs what was observed
- tell_story(date: "YYYY-MM-DD", mode: "medium" or "skeptic") -> a verified story about the night

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
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


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
        return {"night": scan.night, "weekday": scan.weekday, "events": [event_card(e) for e in sorted(top, key=lambda e: e.start)]}

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

    def tell_story(self, date: str, mode: str = "medium") -> dict:
        mode = mode if mode in ("medium", "skeptic") else "medium"
        saved = self.h.story(date, mode)
        if saved:
            return {"title": saved["title"], "sentences": [s["text"] for s in saved["sentences"]]}
        scan = self.h.night(date)
        if scan is None:
            return {"error": f"no scan for {date}"}
        story: Story = narrate(scan, mode, chat=self.chat) if self.chat else template_story(scan, mode)
        return {"title": story.title, "sentences": [s.text for s in story.sentences]}

    def call(self, name: str, args: dict) -> dict:
        fn = {"haunted_nights": self.haunted_nights, "scan_night": self.scan_night,
              "expected_reading": self.expected_reading, "tell_story": self.tell_story}.get(name)
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
    tools = Tools(haunting, chat)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    run = AgentRun(question, "", model=getattr(chat, "model", ""))
    for _ in range(max_steps):
        out = _parse(chat(messages, schema=AGENT_SCHEMA, temperature=0.2))
        tool = out.get("tool")
        if tool:
            args = out.get("args") or {}
            result = tools.call(tool, args)
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
