"""Record what each night's spirit board means, read by Luna with ElevenLabs.

  python demo/make_board_voices.py      # needs ELEVENLABS_API_KEY in .env

For every night with a board message (demo_data/ouija/<night>.json) it writes demo_data/audio/<night>.board.mp3:
the board's shorthand and its plain meaning, the same words the page shows under the board.
Only these fixed texts are ever sent to ElevenLabs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from witching_hour import voice  # noqa: E402

D = ROOT / "demo_data"


def board_text(o: dict) -> str:
    return f"The spirit spelled: {o['message'].title()}. In plain words: {o['why'].strip()}"


def main() -> None:
    voice.load_env(ROOT / ".env")
    manifest_path = D / "audio" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    chars = 0
    for p in sorted((D / "ouija").glob("*.json")):
        o = json.loads(p.read_text(encoding="utf-8"))
        if not o.get("message") or not o.get("why"):
            continue
        key, text = f"{p.stem}.board", board_text(o)
        out = D / "audio" / f"{key}.mp3"
        if manifest.get(key, {}).get("text") == text and out.exists():
            continue
        chars += voice.speak(text, "medium", out)
        manifest[key] = {"text": text, "voice": voice.VOICES["medium"][1], "model": voice.MODEL, "file": out.name}
        print(f"{key}: {len(text)} chars", flush=True)
    manifest_path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"done, {chars} characters sent")


if __name__ == "__main__":
    main()
