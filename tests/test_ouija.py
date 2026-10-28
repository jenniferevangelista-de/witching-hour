import json

from witching_hour.ouija import check_message, spirit_message, template_message
from witching_hour.scanner import Event, NightScan


def scan(events=True):
    e1 = Event("E1", "T2", "living room", "temperature", "°C", "below", "04:20", "06:00", "05:00",
               16.6, 18.0, 17.7, 18.6, 5.8, 100, [])
    return NightScan("2016-03-09", "Wednesday", "test", (0, 6), [e1] if events else [], {}, {})


def test_board_messages_must_be_short_cited_and_grounded():
    s = scan()
    assert check_message({"archetype": "guardian", "message": "COLD 0420", "cites": ["E1"]}, s) is None
    assert check_message({"archetype": "watcher", "message": "STAY WARM", "cites": ["E1"]}, s) is None
    assert "number 0300" in check_message({"archetype": "guardian", "message": "COLD 0300", "cites": ["E1"]}, s)
    assert "not a board" in check_message({"archetype": "guardian", "message": "don't go!", "cites": ["E1"]}, s)
    assert "not a board" in check_message({"archetype": "guardian", "message": "ONE TWO THREE FOUR", "cites": ["E1"]}, s)
    assert check_message({"archetype": "guardian", "message": "COLD", "cites": []}, s) == "cites no apparition"
    assert check_message({"archetype": "ghoul", "message": "COLD", "cites": ["E1"]}, s) == "unknown archetype"


def test_quiet_night_never_invents_a_spirit():
    m = spirit_message(scan(events=False), chat=lambda *a, **k: "{}")
    assert m["message"] == "NO" and m["archetype"] is None and m["fiction"] is True


def test_model_message_is_validated_and_falls_back_to_template():
    bad = json.dumps({"archetype": "guardian", "message": "RUN 1234", "cites": ["E1"], "why": "x"})
    good = json.dumps({"archetype": "watcher", "message": "cold 0500", "cites": ["E1"], "why": "The cold spot peaked at 05:00."})

    class Chat:
        model = "fake"

        def __init__(self, replies):
            self.replies = list(replies)

        def __call__(self, messages, schema=None, temperature=0.5):
            return self.replies.pop(0)

    m = spirit_message(scan(), chat=Chat([bad, good]))
    assert m["message"] == "COLD 0500" and m["by"] == "fake"
    m2 = spirit_message(scan(), chat=Chat([bad, bad]))
    assert m2 == template_message(scan()) and m2["message"] == "COLD 0500"
