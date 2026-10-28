import numpy as np

from witching_hour.footage import detect, robust_z, where


def rows(n=80, flicker_at=None, motion_at=None, motion_cx=0.8):
    out = []
    for i in range(n):
        t = i * 0.25
        b = 0.30 + 0.002 * np.sin(i)
        if flicker_at is not None and flicker_at <= i < flicker_at + 2:
            b = 0.12
        m = 0.002 + 0.0005 * np.cos(i)
        cx = None
        if motion_at is not None and motion_at <= i < motion_at + 4:
            m, cx = 0.05, motion_cx
        out.append({"t": t, "brightness": b, "motion": m, "area": 0.08 if cx else 0.0, "cx": cx})
    return out


def test_robust_z_ignores_the_spike_it_measures():
    z = robust_z(np.array([1.0] * 20 + [1.1] * 20 + [9.0]))
    assert z[-1] > 50


def test_detect_finds_light_motion_and_sound_with_where_and_ids():
    levels = [-50.0 + 0.3 * np.sin(i) for i in range(80)]
    levels[36] = levels[37] = -22.0
    ev = detect(rows(flicker_at=28, motion_at=44), levels)
    kinds = [e["type"] for e in ev]
    assert "light_change" in kinds and "motion" in kinds and "audio" in kinds
    m = next(e for e in ev if e["type"] == "motion")
    assert m["where"] == "right" and m["start"] == 11.0 and 0 < m["confidence"] <= 1
    assert [e["id"] for e in ev] == [f"ev-{i:03d}" for i in range(1, len(ev) + 1)]
    a = next(e for e in ev if e["type"] == "audio")
    assert a["start"] == 9.0 and "dB above the room" in a["description"]


def test_a_quiet_clip_has_no_evidence():
    assert detect(rows(), [-50.0 + 0.2 * np.sin(i) for i in range(80)]) == []
    assert where(0.1) == "left" and where(0.5) == "center" and where(None) is None


def test_a_light_flicker_is_not_counted_as_movement():
    r = rows(flicker_at=28)
    for i in (28, 29, 30):  # the whole frame changes when the light does
        r[i]["motion"], r[i]["area"], r[i]["cx"] = 0.09, 0.6, 0.5
    kinds = {e["type"] for e in detect(r, [])}
    assert kinds == {"light_change"}


def test_a_whisper_then_knocks_are_two_sounds():
    levels = [-60.0 + 0.3 * np.sin(i) for i in range(80)]
    levels[33], levels[34] = -52.0, -45.0  # a whisper rising
    levels[36] = levels[37] = levels[38] = -22.0  # knocks, a sudden jump
    levels[35] = -50.0
    sounds = [e for e in detect(rows(), levels) if e["type"] == "audio"]
    assert [s["start"] for s in sounds] == [8.25, 9.0]


def test_soft_footsteps_are_not_evidence():
    levels = [-60.0] * 80
    for i in (4, 12, 20, 28):  # footsteps, 2 dB above a very steady room
        levels[i] = -58.0
    levels[50] = -30.0
    sounds = [e for e in detect(rows(), levels) if e["type"] == "audio"]
    assert [s["start"] for s in sounds] == [12.5]
