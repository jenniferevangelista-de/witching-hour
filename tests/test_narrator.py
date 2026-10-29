import json

import pytest

from witching_hour.narrator import check_sentence, clean_text, narrate, night_payload, template_story, validate
from witching_hour.scanner import Event, NightScan


def make_scan():
    e1 = Event("E1", "RH_5", "bathroom", "humidity", "%", "above", "03:10", "03:50", "03:20",
               78.4, 61.2, 58.0, 64.5, 7.1, 40, ["E2"])
    e2 = Event("E2", "T5", "bathroom", "temperature", "°C", "above", "03:10", "03:40", "03:30",
               22.6, 20.1, 19.8, 20.5, 5.2, 30, ["E1"])
    return NightScan("2016-03-04", "Friday", "test", (0, 6), [e1, e2], {}, {})


def test_check_sentence_rules():
    by_id = {e.id: e for e in make_scan().events}
    assert check_sentence("At 03:20 the bathroom air hit 78.4 %.", ["E1"], by_id) is None
    assert check_sentence("At 3:20 AM the mirror fogged.", ["E1"], by_id) is None
    assert "not in the cited" in check_sentence("At 03:20 it hit 81 %.", ["E1"], by_id)
    assert "not in the cited" in check_sentence("It was 22.6 °C.", ["E1"], by_id)  # right number, wrong citation
    assert check_sentence("It was 22.6 °C.", ["E2"], by_id) is None
    assert check_sentence("Something moved.", ["E9"], by_id) == "cites no known event or check"
    assert check_sentence("Between midnight and 6 AM the house slept.", ["E1"], by_id) is None


def test_validate_keeps_only_grounded_sentences():
    raw = {"title": "Fog", "sentences": [
        {"text": "At 03:10 the bathroom began to breathe.", "cites": ["E1"]},
        {"text": "A woman in white appeared at 02:00.", "cites": ["E1"]},
        {"text": "No proof here.", "cites": []},
    ]}
    kept, rejected = validate(raw, make_scan())
    assert [s.text for s in kept] == ["At 03:10 the bathroom began to breathe."]
    assert len(rejected) == 2


class ScriptedChat:
    model = "fake-gemma"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages, schema=None, temperature=0.5):
        self.calls.append(list(messages))
        return self.replies.pop(0)


def test_narrate_retries_with_feedback_then_keeps_best():
    bad = {"title": "Boo", "sentences": [{"text": "It reached 99 %.", "cites": ["E1"]}]}
    good = {"title": "Boo", "sentences": [
        {"text": "At 03:10 the bathroom fogged.", "cites": ["E1"]},
        {"text": "It reached 78.4 %.", "cites": ["E1"]},
        {"text": "The air warmed to 22.6 °C.", "cites": ["E2"]},
    ]}
    chat = ScriptedChat([json.dumps(bad), "```json\n" + json.dumps(good) + "\n```"])
    story = narrate(make_scan(), "medium", chat=chat)
    assert story.attempts == 2 and len(story.sentences) == 3 and story.rejected == []
    assert "99 %" in chat.calls[1][-1]["content"]


def test_template_story_passes_its_own_validator():
    scan = make_scan()
    for mode in ("medium", "skeptic"):
        st = template_story(scan, mode)
        raw = {"title": st.title, "sentences": [{"text": s.text, "cites": s.cites} for s in st.sentences]}
        kept, rejected = validate(raw, scan)
        assert rejected == [] and len(kept) == 2


def test_payload_is_compact_and_formatted():
    p = night_payload(make_scan())
    assert p["night"].startswith("Friday 2016-03-04")
    assert p["events"][0]["observed"] == "78.4 %"
    assert p["events"][1]["expected_range"] == "19.8 °C to 20.5 °C"


def test_clean_text_removes_inline_citations_only():
    assert clean_text('At 05:30 the machines woke up [E1]') == "At 05:30 the machines woke up."
    assert clean_text('It hit "17.8 °C" at "05:40" (C1, C2).') == "It hit 17.8 °C at 05:40."
    assert clean_text("The WHO recommends 18 °C (C1). Check the heating (C1).") == "The WHO recommends 18 °C. Check the heating."


@pytest.mark.parametrize("mode", ["medium", "skeptic", "family"])
def test_quiet_night_is_a_scripted_threshold_summary_without_a_model_call(mode):
    scan = make_scan()
    scan.events = []
    # This reading is outside the 90% band, but no event crossed the scanner's
    # more conservative alert threshold. The summary must not call it in-band.
    scan.series = {"T5": {"t": ["03:10"], "y": [21.0], "q05": [19.8], "q95": [20.5]}}
    chat = ScriptedChat([])  # any accidental model call would exhaust replies

    story = narrate(scan, mode, chat=chat, model="must-not-be-attributed")

    assert chat.calls == []
    assert story.model == "template" and story.attempts == 0
    assert story.sentences[0].cites == []
    assert story.to_dict()["verified"] == 0 and story.to_dict()["dropped"] == 0
    assert "every reading stayed inside" not in story.sentences[0].text.lower()
    assert "alert" in story.sentences[0].text


def test_quiet_template_has_the_same_provenance_as_the_narration_shortcut():
    scan = make_scan()
    scan.events = []
    for mode in ("medium", "skeptic", "family"):
        assert template_story(scan, mode).to_dict() == narrate(scan, mode, chat=ScriptedChat([])).to_dict()
