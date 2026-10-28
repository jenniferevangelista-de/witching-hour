import json

import pytest
from fastapi.testclient import TestClient

from witching_hour import spirits

EVIDENCE = [
    {"id": "ev-001", "type": "light_change", "start": 7.0, "end": 7.8, "description": "the hallway light dipped", "confidence": 0.9},
    {"id": "ev-002", "type": "audio", "start": 9.1, "end": 9.6, "description": "a short knock", "confidence": 0.7},
    {"id": "ev-003", "type": "motion", "start": 11.0, "end": 12.5, "description": "movement near the door", "confidence": 0.8, "where": "door"},
]


class Scripted:
    model = "fake-gemma"

    def __init__(self, replies):
        self.replies = list(replies)

    def __call__(self, messages, schema=None, temperature=0.5):
        return json.dumps(self.replies.pop(0))


def test_board_answers_are_validated():
    ok, why = spirits.check_answer({"message": "don't go", "spoken": "Not tonight.", "evidence_ids": ["ev-003"]}, EVIDENCE)
    assert ok["message"] == "DONT GO" and why is None
    assert spirits.check_answer({"message": "STAY HOME NOW PLEASE", "spoken": "", "evidence_ids": ["ev-001"]}, EVIDENCE)[1]
    assert "real evidence" in spirits.check_answer({"message": "BEHIND YOU", "spoken": "", "evidence_ids": ["ev-999"]}, EVIDENCE)[1]
    assert "harm" in spirits.check_answer({"message": "YOU WILL DIE", "spoken": "", "evidence_ids": ["ev-001"]}, EVIDENCE)[1]
    assert spirits.check_answer({"message": "NO", "spoken": "", "evidence_ids": []}, EVIDENCE)[1] is None
    assert spirits.board_sequence("STAY HOME") == ["S", "T", "A", "Y", "SPACE", "H", "O", "M", "E"]
    assert spirits.board_sequence("GOODBYE") == ["GOODBYE"]


def test_summon_and_ask_with_a_model_keeps_memory_and_contract():
    chat = Scripted([
        {"archetype": "guardian", "name": "Agnes", "backstory": "She lived here once.", "goal": "to warn the woman", "evidence_ids": ["ev-003"]},
        {"message": "YES", "spoken": "I was by the door.", "evidence_ids": ["ev-003"]},
        {"message": "DONT GO", "spoken": "Not tonight.", "evidence_ids": ["ev-001", "ev-003"]},
    ])
    s = spirits.summon("the-warning", EVIDENCE, chat=chat)
    assert s.spirit.archetype == "guardian" and s.spirit.name == "Agnes"
    r1 = spirits.ask(s, "Is someone here?", chat=chat)
    r2 = spirits.ask(s, "What were you trying to say?", chat=chat)
    assert r1["response"]["message"] == "YES" and r2["response"]["message"] == "DONT GO"
    assert r2["response"]["fictional"] is True and r2["grounding"]["related_evidence_ids"] == ["ev-001", "ev-003"]
    assert r2["response"]["animation_sequence"][:4] == ["D", "O", "N", "T"]
    assert len(s.history) == 2


def test_bad_model_answers_fall_back_to_template_never_to_threats():
    chat = Scripted([{"message": "YOU WILL DIE", "spoken": "", "evidence_ids": ["ev-001"]},
                     {"message": "CRASH TONIGHT", "spoken": "", "evidence_ids": ["ev-001"]}])
    s = spirits.summon("x", EVIDENCE)  # template spirit
    r = spirits.ask(s, "What happens if I go?", chat=chat)
    assert r["response"]["by"] == "template" and "DIE" not in r["response"]["message"]


def test_no_evidence_means_no_invented_spirit():
    s = spirits.summon("quiet", [])
    assert s.spirit.archetype == "silent"
    r = spirits.ask(s, "Is someone here?")
    assert r["response"]["message"] == "NO" and r["grounding"]["related_evidence_ids"] == []


def test_session_api(monkeypatch):
    monkeypatch.setenv("WH_LLM", "none")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    from witching_hour import app as app_module

    app_module._store = None
    c = TestClient(app_module.app)
    s = c.post("/api/sessions", json={"investigation": "the-warning", "evidence": EVIDENCE}).json()
    assert s["spirit"]["archetype"] == "guardian" and s["model"].startswith("template")
    r = c.post(f"/api/sessions/{s['session_id']}/ask", json={"question": "What were you trying to say?"}).json()
    assert r["response"]["message"] == "STAY HOME" and r["response"]["fictional"] is True
    assert c.post(f"/api/sessions/{s['session_id']}/close").json()["response"]["message"] == "GOODBYE"
    assert c.post(f"/api/sessions/{s['session_id']}/ask", json={"question": "hello?"}).status_code == 409
    assert c.get("/api/sessions/nope").status_code == 404
    assert "guardian" in c.get("/api/spirits").json()["archetypes"]


def test_memory_store_forgets_the_oldest_sessions():
    store = spirits.MemoryStore()
    store.MAX = 3
    ids = []
    for _ in range(5):
        s = spirits.summon("x", EVIDENCE)
        store.save(s)
        ids.append(s.session_id)
    assert store.load(ids[0]) is None and store.load(ids[1]) is None
    assert store.load(ids[4]).session_id == ids[4]
