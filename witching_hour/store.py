"""Where scans and stories live on disk: one JSON per night, plus an index."""
from __future__ import annotations

import json
from pathlib import Path

from .narrator import PHENOMENA, Story
from .scanner import NightScan


def headline(scan: NightScan) -> str:
    if not scan.events:
        return "a quiet night"
    e = max(scan.events, key=lambda e: e.sigma)
    return f"{PHENOMENA.get((e.kind, e.direction), 'a strange reading')} in the {e.room} at {e.peak_time}"


def save_scan(scan: NightScan, out_dir: str | Path) -> Path:
    p = Path(out_dir) / "nights" / f"{scan.night}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(scan.to_dict(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return p


def save_story(story: Story, out_dir: str | Path) -> Path:
    p = Path(out_dir) / "stories" / f"{story.night}.{story.mode}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(story.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def build_index(out_dir: str | Path, meta: dict | None = None) -> dict:
    out_dir = Path(out_dir)
    nights = []
    for p in sorted((out_dir / "nights").glob("*.json")):
        scan = NightScan.from_dict(json.loads(p.read_text(encoding="utf-8")))
        modes = [m for m in ("medium", "skeptic", "family") if (out_dir / "stories" / f"{scan.night}.{m}.json").exists()]
        nights.append({
            "night": scan.night, "weekday": scan.weekday, "score": round(scan.score, 1),
            "n_events": len(scan.events), "n_cold": len(scan.checks), "headline": headline(scan), "stories": modes,
        })
    index = {"meta": meta or {}, "nights": nights}
    old = out_dir / "index.json"
    if old.exists() and not meta:
        index["meta"] = json.loads(old.read_text(encoding="utf-8")).get("meta", {})
    old.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return index
