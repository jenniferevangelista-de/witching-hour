from witching_hour.checks import cold_checks
from witching_hour.narrator import narrate, night_payload, template_story, validate
from witching_hour.scanner import Event, NightScan


def _series(values):
    t = [f"{h:02d}:{m:02d}" for h in range(6) for m in range(0, 60, 10)][: len(values)]
    return {"t": t, "y": values}


def test_cold_checks_need_an_hour_and_skip_utility_rooms():
    cold = [19.0] * 6 + [17.5, 17.2, 16.9, 17.0, 17.4, 17.8] + [18.5] * 4 + [17.0] * 3
    sensors = {
        "T9": {"kind": "temperature", "room": "parents' room"},
        "T3": {"kind": "temperature", "room": "laundry room"},
        "RH_9": {"kind": "humidity", "room": "parents' room"},
    }
    series = {"T9": _series(cold), "T3": _series([10.0] * 19), "RH_9": _series([10.0] * 19)}
    checks = cold_checks(series, sensors)
    assert len(checks) == 1  # the 30 minute dip at the end is too short, laundry and humidity are ignored
    c = checks[0]
    assert (c.id, c.room, c.start, c.end, c.minutes, c.coldest, c.coldest_time) == (
        "C1", "parents' room", "01:00", "02:00", 60, 16.9, "01:20")


def _scan_with_check():
    e1 = Event("E1", "Appliances", "house", "energy", "Wh", "above", "03:10", "03:40", "03:20",
               420.0, 60.0, 40.0, 110.0, 9.3, 30, [])
    series = {"T9": _series([17.0] * 12 + [19.0] * 24)}
    sensors = {"T9": {"kind": "temperature", "room": "parents' room", "unit": "°C", "label": "parents' room temperature"}}
    scan = NightScan("2016-02-10", "Wednesday", "test", (0, 6), [e1], series, sensors)
    scan.checks = cold_checks(series, sensors)
    return scan


def test_round_trip_recomputes_checks_for_old_files():
    scan = _scan_with_check()
    d = scan.to_dict()
    assert d["checks"][0]["id"] == "C1"
    d.pop("checks")
    assert NightScan.from_dict(d).checks[0].minutes == 120


def test_family_note_can_cite_checks_and_the_who_threshold():
    scan = _scan_with_check()
    raw = {"title": "A cool night", "sentences": [
        {"text": "The parents' room stayed below 18 °C from 00:00 to 02:00, down to 17.0 °C.", "cites": ["C1"]},
        {"text": "The WHO recommends at least 18 °C indoors in cold seasons.", "cites": ["C1"]},
        {"text": "Appliances used 420 Wh at 03:20.", "cites": ["E1"]},
        {"text": "It was 15 °C in the parents' room.", "cites": ["C1"]},
    ]}
    kept, rejected = validate(raw, scan)
    assert len(kept) == 3 and len(rejected) == 1
    st = template_story(scan, "family")
    raw = {"title": st.title, "sentences": [{"text": s.text, "cites": s.cites} for s in st.sentences]}
    assert validate(raw, scan)[1] == []
    assert night_payload(scan, with_checks=True)["checks"][0]["coldest"] == "17.0 °C"
    assert "checks" not in night_payload(scan)


def test_family_mode_runs_on_a_cold_night_without_events():
    scan = _scan_with_check()
    scan.events = []

    class Chat:
        model = "fake"

        def __call__(self, messages, schema=None, temperature=0.5):
            assert "C1" in messages[1]["content"]
            return '{"title": "Cold", "sentences": [{"text": "The parents\' room stayed below 18 °C until 02:00.", "cites": ["C1"]}]}'

    st = narrate(scan, "family", chat=Chat(), retries=0)
    assert st.sentences and st.sentences[0].cites == ["C1"]
