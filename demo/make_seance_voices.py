"""Record the séance's fixed lines once with ElevenLabs.

The crew (Luna, Dr. Bigotes, Xochi) and the template Guardian say the same short lines every time, so they are
voiced ahead of time and shipped as audio files. The page looks a line up by its text and plays it.

  python demo/make_seance_voices.py --dry     # list the lines and the number of characters
  python demo/make_seance_voices.py           # needs ELEVENLABS_API_KEY in .env

Writes demo_data/audio/seance-<hash>.mp3 and demo_data/audio/seance_manifest.json.
Only these fixed lines are ever sent to ElevenLabs.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from witching_hour import spirits  # noqa: E402
from witching_hour.voice import MODEL, SETTINGS, VOICES, load_env  # noqa: E402

OUT = ROOT / "demo_data" / "audio"
MANIFEST = OUT / "seance_manifest.json"
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_64"
SPIRIT_SETTINGS = {"stability": 0.35, "similarity_boost": 0.8, "style": 0.45}   # same as the recorded Warning séance


def norm(text: str) -> str:
    """The key the page uses to look a line up (it does the same to the text it is about to say)."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


LUNA = [
    "Shhh... the house is breathing. I am Luna, the medium. I feel every presence in my crystal ball.",
    "Is someone here?", "Who are you?", "What were you trying to tell me that night?", "Why did you knock?",
    "What would have happened if I had gone out?", "Will you come back?", "What were you trying to say?",
    "Where?", "Why?", "Goodbye", "Out! Everybody out!",
    "The room is yours now. Ask the board, and watch the glass.", "That was not me!",
    "I summon the spirit the evidence suggests: a Guardian, a Lost One, a Trickster, a Watcher, a Hostile Presence or a Silent One. Its answers are fiction, and each one must point at a real moment of the recording.",
]
BIGOTES = [
    "Hmph. I am Doctor Bigotes. I have never met a ghost that was not a kettle, a draft or a thermostat.",
    # his note under each piece of evidence of The Warning (the same text the page shows)
    "Hmph. A light that dips and comes back in under a second: a tired bulb, a dimmer, a car's headlights, or the camera's own auto-exposure.",
    "It came with the flicker. A failing bulb buzzes when it struggles. Cheap bulbs, not spirits.",
    "Soft, and not for long: the fridge, the heating ticking, a phone buzzing in a pocket. I would not call it a voice.",
    "Loud and sharp: a door down the hall, the pipes knocking, a neighbour. Ghosts are rarely this loud.",
    "Movement on the right: a person, a pet, a coat in a draft, or the camera adjusting. I would check who was home.",
    "It is only a draft. Probably.",
    "Two real sounds, both cited. And I have no kettle for this.",
    "Fine! I have nothing left to say! Run, run, RUUUUN!", "Probably the kettle. Probably.",
]
XOCHI = [
    "I am Xochi. I keep watch all night, and at dawn I bring the family a note about what I saw.",
    "I kept watch. The glass moved by itself.",
    "Her words are gentle. Her warning is not.",
    "I will write it down: every answer cites a real moment.",
    "Wait. The air just changed.",
    "Stay close to me!", "It moved when the glass stopped. I will write it down.",
    "The case is closed. Thank you for staying until the end.",
]
SPIRIT = sorted({spirits.GUARDIAN_YES, "Still here. I never left.", spirits.GUARDIAN_WHO, spirits.GUARDIAN_WHERE,
                 *[row[2] for row in spirits.GUARDIAN_ROWS], *[d[1] for d in spirits.GUARDIAN_DEFAULTS]})


def catalogue() -> list[tuple[str, str, str]]:
    """(who, text, voice id) for every line."""
    out = []
    for who, mode, lines in (("luna", "medium", LUNA), ("bigotes", "skeptic", BIGOTES), ("xochi", "family", XOCHI)):
        out += [(who, t, mode) for t in lines]
    out += [("spirit", t, "spirit") for t in SPIRIT]
    return out


def voice_of(mode: str):
    if mode == "spirit":
        return spirits.ARCHETYPES["guardian"]["voice"], SPIRIT_SETTINGS, "Guardian"
    return VOICES[mode][0], SETTINGS[mode], VOICES[mode][1]


def main() -> None:
    lines = catalogue()
    chars = sum(len(t) for _, t, _ in lines)
    if "--dry" in sys.argv:
        for who, t, _ in lines:
            print(f"{who:8} {t}")
        print(f"\n{len(lines)} lines, {chars} characters")
        return
    import os

    import requests

    load_env(ROOT / ".env")
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    sent = 0
    for who, text, mode in lines:
        k = norm(text)
        f = f"seance-{hashlib.sha1(k.encode()).hexdigest()[:10]}.mp3"
        if manifest.get(k, {}).get("file") == f and (OUT / f).exists():
            continue
        voice, settings, name = voice_of(mode)
        r = requests.post(API.format(voice=voice), headers={"xi-api-key": key, "Content-Type": "application/json"},
                          json={"text": text, "model_id": MODEL, "voice_settings": settings}, timeout=120)
        r.raise_for_status()
        (OUT / f).write_bytes(r.content)
        manifest[k] = {"file": f, "who": who, "voice": name, "text": text}
        sent += len(text)
        print(f"{who:8} {len(text):3} chars  {text[:60]}", flush=True)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"done: {sent} characters sent, {len(manifest)} lines in the manifest")


if __name__ == "__main__":
    main()
