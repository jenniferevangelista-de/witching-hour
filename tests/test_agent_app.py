import json
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tests.conftest import GHOST_NIGHT, synthetic_house
from witching_hour import app as app_module
from witching_hour.agent import Haunting, Tools, investigate
from witching_hour.narrator import template_story
from witching_hour.scanner import SeasonalBackend, scan_night
from witching_hour.store import build_index, save_scan, save_story


@pytest.fixture(scope="module")
def demo_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    house = synthetic_house()
    for d in ("2016-01-16", GHOST_NIGHT):
        scan = scan_night(house, date.fromisoformat(d), SeasonalBackend(), sensors=["T1", "T2", "RH_1"])
        save_scan(scan, out)
        for mode in ("medium", "skeptic"):
            save_story(template_story(scan, mode), out)
    build_index(out, {"house": "synthetic house", "attribution": "synthetic"})
    (out / "agent_runs.json").write_text(json.dumps([{"question": "q", "answer": "a", "steps": [], "model": "m"}]))
    return out


def test_index_ranks_the_ghost_night(demo_dir):
    h = Haunting(demo_dir)
    top = Tools(h).haunted_nights(top_k=1)["nights"][0]
    assert top["night"] == GHOST_NIGHT and top["n_events"] >= 1
    assert "kitchen" in top["headline"]


def test_tools(demo_dir):
    t = Tools(Haunting(demo_dir))
    ev = t.scan_night(GHOST_NIGHT)["events"]
    assert ev[0]["room"] == "kitchen"
    r = t.expected_reading(GHOST_NIGHT, "03:10", "kitchen temperature")
    assert r["sensor"] == "kitchen temperature" and r["sigma"] > 4
    assert "error" in t.expected_reading(GHOST_NIGHT, "03:15", "T1")
    assert "error" in t.scan_night("1999-01-01")
    assert t.tell_story(GHOST_NIGHT, "skeptic")["sentences"]
    assert "error" in t.call("delete_house", {})


class ScriptedChat:
    model = "fake-gemma"

    def __init__(self, replies):
        self.replies = list(replies)

    def __call__(self, messages, schema=None, temperature=0.5):
        return json.dumps(self.replies.pop(0))


def test_investigate_calls_tools_then_answers(demo_dir):
    chat = ScriptedChat([
        {"tool": "haunted_nights", "args": {"top_k": 3}},
        {"tool": "expected_reading", "args": {"date": GHOST_NIGHT, "time": "03:10", "sensor": "T1"}},
        {"answer": "The kitchen ran hot at 03:10."},
    ])
    run = investigate("Which night was haunted?", Haunting(demo_dir), chat)
    assert [s["tool"] for s in run.steps] == ["haunted_nights", "expected_reading"]
    assert run.answer == "The kitchen ran hot at 03:10."
    assert run.model == "fake-gemma"


def test_investigate_stops_after_max_steps(demo_dir):
    chat = ScriptedChat([{"tool": "haunted_nights", "args": {}}] * 3)
    run = investigate("loop forever", Haunting(demo_dir), chat, max_steps=3)
    assert "ran out of steps" in run.answer and len(run.steps) == 3


@pytest.fixture
def client(demo_dir, monkeypatch):
    monkeypatch.setenv("WH_DATA", str(demo_dir))
    monkeypatch.setenv("WH_LIVE", "0")
    app_module._haunting.clear()
    return TestClient(app_module.app)


def test_app_routes(client):
    assert client.get("/").status_code == 200
    h = client.get("/api/health").json()
    assert h["ok"] and h["nights"] == 2 and h["live"] is False
    idx = client.get("/api/nights").json()
    assert idx["meta"]["house"] == "synthetic house"
    n = client.get(f"/api/nights/{GHOST_NIGHT}").json()
    assert set(n["stories"]) == {"medium", "skeptic"} and n["events"]
    assert client.get("/api/nights/2016-13-99").status_code == 404
    assert client.get("/api/nights/..%2Fsecret").status_code in (400, 404)
    assert client.get("/api/agent-runs").json()[0]["answer"] == "a"
    assert client.get("/static/app.js").status_code == 200


def test_ask_is_off_on_the_public_demo(client):
    r = client.post("/api/ask", json={"question": "Was it a ghost?"})
    assert r.status_code == 503 and "private" in r.json()["detail"]
    assert client.post("/api/ask", json={"question": ""}).status_code == 422


def test_historical_quiet_story_is_presented_as_scripted(client, demo_dir):
    path = demo_dir / "stories" / "2016-01-16.medium.json"
    original = path.read_bytes()
    response = client.get("/api/nights/2016-01-16")
    assert response.status_code == 200
    story = response.json()["stories"]["medium"]
    assert story["model"] == "template" and story["attempts"] == 0
    assert story["verified"] == 0
    assert "range" not in story["sentences"][0]["text"]
    assert path.read_bytes() == original
