import json
from datetime import date

import requests

from tests.conftest import GHOST_NIGHT, synthetic_house
from witching_hour.bakeoff import run_bakeoff
from witching_hour.scanner import SeasonalBackend, scan_night
from witching_hour.store import build_index, save_scan


class FakeResponse:
    status_code = 200

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"status": "COMPLETED", "content": self._content}


def test_bakeoff_scores_grounding_per_model(tmp_path, monkeypatch):
    scan = scan_night(synthetic_house(), date.fromisoformat(GHOST_NIGHT), SeasonalBackend(), sensors=["T1", "T2"])
    save_scan(scan, tmp_path)
    build_index(tmp_path)
    e = scan.events[0]
    good = {"title": "Warm", "sentences": [{"text": f"At {e.start} the kitchen warmed to {e.observed:.1f} °C.", "cites": [e.id]}]}
    bad = {"title": "Warm", "sentences": [{"text": "At 01:23 the kitchen hit 99 °C.", "cites": [e.id]}]}
    seen = []

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.append(json["model_name"])
        assert headers["X-API-Key"] == "test-key" and json["memory"] == "off"
        return FakeResponse(_dumps(good if json["model_name"] == "good/model" else bad))

    _dumps = json.dumps
    monkeypatch.setenv("BACKBOARD_API_KEY", "test-key")
    monkeypatch.setattr(requests, "post", fake_post)
    res = run_bakeoff(tmp_path, [GHOST_NIGHT], ["medium"], ["good/model", "bad/model"])
    scores = {r["model"]: r["grounded_share"] for r in res["results"]}
    assert scores == {"good/model": 1.0, "bad/model": 0.0}
    assert seen == ["good/model", "bad/model"]
