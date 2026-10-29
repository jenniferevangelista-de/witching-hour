import json

import pytest
from fastapi.testclient import TestClient

from witching_hour import app as app_module, voice
from witching_hour.agent import Haunting, Tools
from witching_hour.checks import cold_checks
from witching_hour.narrator import quiet_night
from witching_hour.scanner import NightScan
from witching_hour.store import save_scan

NIGHT = "2016-01-16"
LEGACY_TEXT = "Every reading stayed inside its expected range."


def write_legacy_case(data_dir, mode, cold=False):
    times = [f"00:{minute:02d}" for minute in range(0, 60, 10)]
    series = {
        "T9": {
            "t": times,
            "y": [17.0 if cold else 21.0] * 6,
            "q05": [19.5] * 6,
            "q50": [20.0] * 6,
            "q95": [20.5] * 6,
            "z": [2.0] * 6,
        }
    }
    sensors = {
        "T9": {
            "kind": "temperature",
            "room": "bedroom",
            "unit": "°C",
            "label": "bedroom temperature",
        }
    }
    scan = NightScan(NIGHT, "Saturday", "test", (0, 6), [], series, sensors)
    scan.checks = cold_checks(series, sensors)
    save_scan(scan, data_dir)
    sentences = [{"text": LEGACY_TEXT, "cites": []}]
    if cold and mode == "family":
        sentences = [{
            "text": "The bedroom stayed below 18 °C, down to 17.0 °C.",
            "cites": ["C1"],
        }]
    saved = {
        "night": NIGHT,
        "mode": mode,
        "model": "historically-selected-gemma",
        "title": "Historical title",
        "sentences": sentences,
        "attempts": 1,
        "verified": 1,
        "dropped": 0,
        "rejected": [],
    }
    path = data_dir / "stories" / f"{NIGHT}.{mode}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(saved), encoding="utf-8")
    return scan, path, saved


def client_for(data_dir, monkeypatch):
    monkeypatch.setenv("WH_DATA", str(data_dir))
    monkeypatch.setenv("WH_LIVE", "0")
    app_module._haunting.clear()
    return TestClient(app_module.app)


@pytest.mark.parametrize("mode", ["medium", "skeptic", "family"])
def test_legacy_quiet_story_is_identical_for_api_and_agent_without_rewriting(
    tmp_path, monkeypatch, mode
):
    scan, path, _ = write_legacy_case(tmp_path, mode)
    original = path.read_bytes()
    expected = quiet_night(scan, mode).to_dict()
    haunting = Haunting(tmp_path)

    saved = haunting.story(NIGHT, mode)
    tool = Tools(haunting).tell_story(NIGHT, mode)
    client = client_for(tmp_path, monkeypatch)
    presented = client.get(f"/api/nights/{NIGHT}").json()["stories"][mode]

    assert saved == expected
    assert presented == expected
    assert tool["sentences"] == [s["text"] for s in expected["sentences"]]
    assert tool["model"] == "template"
    assert tool["attempts"] == 0 and tool["verified"] == 0
    assert LEGACY_TEXT not in " ".join(tool["sentences"])
    assert path.read_bytes() == original


def test_family_note_with_cold_checks_keeps_its_recorded_model_and_citations(
    tmp_path, monkeypatch
):
    scan, path, saved = write_legacy_case(tmp_path, "family", cold=True)
    original = path.read_bytes()
    assert not scan.events and scan.checks

    haunting = Haunting(tmp_path)
    presented = client_for(tmp_path, monkeypatch).get(
        f"/api/nights/{NIGHT}"
    ).json()["stories"]["family"]

    assert haunting.story(NIGHT, "family") == saved
    assert presented == saved
    assert Tools(haunting).tell_story(NIGHT, "family")["model"] == saved["model"]
    assert presented["sentences"][0]["cites"] == ["C1"]
    assert path.read_bytes() == original


def test_stale_audio_is_hidden_and_cannot_be_requested_directly(
    tmp_path, monkeypatch
):
    _, story_path, legacy = write_legacy_case(tmp_path, "medium")
    original_story = story_path.read_bytes()
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    audio_path = audio_dir / f"{NIGHT}.medium.mp3"
    audio_path.write_bytes(b"ID3historical-audio")
    manifest_path = audio_dir / "manifest.json"
    manifest_path.write_text(json.dumps({
        f"{NIGHT}.medium": {"text": voice.script(legacy)}
    }), encoding="utf-8")
    original_audio = audio_path.read_bytes()
    original_manifest = manifest_path.read_bytes()
    client = client_for(tmp_path, monkeypatch)

    story = client.get(f"/api/nights/{NIGHT}").json()["stories"]["medium"]
    assert "audio" not in story
    assert client.get(f"/audio/{NIGHT}.medium.mp3").status_code == 404
    assert story_path.read_bytes() == original_story
    assert audio_path.read_bytes() == original_audio
    assert manifest_path.read_bytes() == original_manifest

    # Matching is based on the declared transcript, not speech recognition.
    manifest_path.write_text(json.dumps({
        f"{NIGHT}.medium": {"text": voice.script(story)}
    }), encoding="utf-8")
    story = client.get(f"/api/nights/{NIGHT}").json()["stories"]["medium"]
    assert story["audio"] == f"/audio/{NIGHT}.medium.mp3"
    assert client.get(story["audio"]).status_code == 200


def test_voice_generation_uses_the_shared_presented_story(
    tmp_path, monkeypatch
):
    scan, path, _ = write_legacy_case(tmp_path, "medium")
    original = path.read_bytes()
    spoken = []

    def fake_speak(text, mode, out, api_key=None, timeout=120):
        spoken.append((text, mode))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"ID3")
        return len(text)

    monkeypatch.setattr(voice, "speak", fake_speak)
    voice.voice_stories(tmp_path, [NIGHT], ["medium"])

    expected = voice.script(quiet_night(scan, "medium").to_dict())
    assert spoken == [(expected, "medium")]
    assert LEGACY_TEXT not in spoken[0][0]
    assert Haunting(tmp_path).audio(NIGHT, "medium") is not None
    assert path.read_bytes() == original
