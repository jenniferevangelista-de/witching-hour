"""Read the stories out loud with ElevenLabs.

Only the verified sentences are spoken, so the audio never says anything the
validator dropped. A family member can listen to the morning note on the way to
work; the Medium gets a storyteller voice for Halloween.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# One voice per character of the crew.
VOICES = {
    "medium": ("cgSgspJ2msm6clMCkdW9", "Jessica"),  # Luna: playful, a little breathless
    "skeptic": ("JBFqnCBsd6RMkjVDRZzb", "George"),  # Dr. Bigotes: dry British professor
    "family": ("XrExE9yKIg1WjnnlVkGX", "Matilda"),  # Xochi: warm and calm
}
SETTINGS = {
    "medium": {"stability": 0.3, "similarity_boost": 0.8, "style": 0.6},
    "skeptic": {"stability": 0.55, "similarity_boost": 0.8, "style": 0.3},
    "family": {"stability": 0.6, "similarity_boost": 0.8, "style": 0.15},
}
MODEL = "eleven_multilingual_v2"
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64"


def load_env(path: str | Path = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def script(story: dict) -> str:
    """What gets read: the title, then the verified sentences, in order."""
    lines = [story.get("title", "").strip().rstrip(".") + "."] + [s["text"].strip() for s in story.get("sentences", [])]
    return " ".join(x for x in lines if x and x != ".")


def speak(text: str, mode: str, out: Path, api_key: str | None = None, timeout: int = 120) -> int:
    import requests

    key = api_key or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY is not set")
    voice, _ = VOICES[mode]
    settings = SETTINGS[mode]
    r = requests.post(API.format(voice=voice), headers={"xi-api-key": key, "Content-Type": "application/json"},
                      json={"text": text, "model_id": MODEL, "voice_settings": settings}, timeout=timeout)
    r.raise_for_status()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return len(text)


def voice_stories(data_dir: str | Path, dates: list[str], modes: list[str]) -> dict:
    """Write demo_data/audio/<night>.<mode>.mp3 and a manifest with the exact text and voice."""
    data_dir = Path(data_dir)
    manifest_path = data_dir / "audio" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    chars = 0
    for d in dates:
        for mode in modes:
            p = data_dir / "stories" / f"{d}.{mode}.json"
            if not p.exists():
                continue
            story = json.loads(p.read_text(encoding="utf-8"))
            text = script(story)
            key = f"{d}.{mode}"
            out = data_dir / "audio" / f"{key}.mp3"
            if manifest.get(key, {}).get("text") == text and out.exists():
                continue
            chars += speak(text, mode, out)
            manifest[key] = {"text": text, "voice": VOICES[mode][1], "model": MODEL, "file": out.name}
            print(f"{key}: {len(text)} chars, voice {VOICES[mode][1]}", flush=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"characters": chars, "files": len(manifest)}
