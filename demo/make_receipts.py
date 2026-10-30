"""Count the proof that sits in this repository, so the page can show real numbers instead of claims.

  python demo/make_receipts.py     # writes demo_data/receipts.json

Everything here is counted from files: tests, workflows, recorded voices, nights, the planted-ghost benchmark, the
model bake-off, and whether every moment the recorded séance cites really exists in The Warning's evidence.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "demo_data"


def main() -> None:
    tests = sum(len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), re.M)) for f in (ROOT / "tests").glob("*.py"))
    warning = json.loads((D / "cases.json").read_text(encoding="utf-8"))["cases"][0]
    ids = {e["id"] for e in warning["evidence"]}
    cited = set()
    for t in warning["seance"]["turns"]:
        cited |= set(t["grounding"]["related_evidence_ids"])
    ev = json.loads((D / "eval.json").read_text(encoding="utf-8"))["results"]
    bk = json.loads((D / "bakeoff.json").read_text(encoding="utf-8"))
    out = {
        "counted_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tests": tests,
        "workflows": len(list((ROOT / ".github" / "workflows").glob("*.yml"))),
        "voice_lines": len(json.loads((D / "audio" / "seance_manifest.json").read_text(encoding="utf-8"))),
        "audio_files": len(list((D / "audio").glob("*.mp3"))),
        "nights": len(list((D / "nights").glob("*"))),
        "stories": len(list((D / "stories").glob("*"))),
        "warning": {"moments": len(ids), "cited": sorted(cited), "all_cited_exist": cited <= ids, "turns": len(warning["seance"]["turns"])},
        "planted": [{"backend": r["backend"], "recall_fpr5": r["recall_fpr5"], "auc": r["auc"], "cases": r["n_cases"]} for r in ev],
        "bakeoff": [{"model": r["model"], "grounded": r["grounded_share"], "verified": r["verified"], "sentences": r["sentences"]} for r in bk["results"]]
        + ([{"model": bk["local"]["model"], "grounded": bk["local"]["grounded_share"], "verified": bk["local"]["verified"], "sentences": bk["local"]["sentences"]}] if bk.get("local") else []),
    }
    (D / "receipts.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("planted", "bakeoff")}))


if __name__ == "__main__":
    main()
