import json

from witching_hour import voice


def test_script_reads_title_then_verified_sentences_only():
    story = {"title": "A cold night", "sentences": [{"text": "The bedroom stayed below 18 °C."}],
             "rejected": [{"text": "A ghost opened the door."}]}
    assert voice.script(story) == "A cold night. The bedroom stayed below 18 °C."


def test_voice_stories_writes_files_and_skips_unchanged(tmp_path, monkeypatch):
    (tmp_path / "stories").mkdir()
    story = {"title": "Morning", "sentences": [{"text": "The night looked calm."}]}
    (tmp_path / "stories" / "2016-02-10.family.json").write_text(json.dumps(story), encoding="utf-8")
    calls = []

    def fake_speak(text, mode, out, api_key=None, timeout=120):
        calls.append((text, mode))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"ID3")
        return len(text)

    monkeypatch.setattr(voice, "speak", fake_speak)
    r = voice.voice_stories(tmp_path, ["2016-02-10", "2016-02-11"], ["family", "medium"])
    assert calls == [("Morning. The night looked calm.", "family")] and r["files"] == 1
    manifest = json.loads((tmp_path / "audio" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["2016-02-10.family"]["voice"] == "Matilda"
    voice.voice_stories(tmp_path, ["2016-02-10"], ["family"])
    assert len(calls) == 1  # same text, file exists: no second request


def test_seance_lines_are_voiced_and_served():
    import json
    from pathlib import Path

    from fastapi.testclient import TestClient

    from witching_hour import app as app_module, spirits

    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "demo_data" / "audio" / "seance_manifest.json").read_text(encoding="utf-8"))
    for _, _, spoken, _ in spirits.GUARDIAN_ROWS:
        entry = manifest[" ".join(__import__("re").sub(r"[^a-z0-9]+", " ", spoken.lower()).split())]
        assert (root / "demo_data" / "audio" / entry["file"]).exists()
    c = TestClient(app_module.app)
    assert c.get("/api/seance/voices").json() == manifest
    first = next(iter(manifest.values()))["file"]
    assert c.get(f"/audio/{first}").status_code == 200
