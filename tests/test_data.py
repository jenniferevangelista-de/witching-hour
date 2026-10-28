from datetime import date

from witching_hour.data import eligible_nights, features, load_home_assistant, load_uci, peer_columns


def test_load_uci_parses_quoted_padded_numbers(tmp_path):
    p = tmp_path / "energydata_complete.csv"
    p.write_text(
        '"date","Appliances","lights","T1","RH_1","rv1","rv2"\n'
        '"2016-01-11 17:00:00","  60","30","19.89","47.59","13.2","13.2"\n'
        '"2016-01-11 17:20:00"," 50","30","19.70","47.10","1","1"\n',
        encoding="utf-8",
    )
    h = load_uci(p)
    assert "rv1" not in h.df.columns
    assert h.df.loc["2016-01-11 17:00", "Appliances"] == 60
    # the missing 17:10 slot is filled by interpolation
    assert abs(h.df.loc["2016-01-11 17:10", "T1"] - 19.795) < 1e-6


def test_eligible_nights_need_memory(house):
    nights = eligible_nights(house, context_days=14)
    assert nights[0] == date(2016, 1, 15)
    assert nights[-1] == date(2016, 1, 20)
    assert len(nights) == 6


def test_peers_leave_out_same_room(house):
    assert peer_columns(house, "T1") == ["T2"]
    assert peer_columns(house, "Appliances") == []


def test_features_have_time_and_context(house):
    X = features(house, house.df.iloc[:10], "RH_2")
    assert {"tod", "tod_sin", "tod_cos", "dow", "weekend", "T_out", "RH_1"} <= set(X.columns)
    assert "RH_2" not in X.columns and "T2" not in X.columns


def test_home_assistant_export(tmp_path):
    p = tmp_path / "history.csv"
    p.write_text(
        "entity_id,state,last_changed\n"
        "sensor.kitchen_temperature,20.0,2016-01-01T00:00:00.000Z\n"
        "sensor.kitchen_temperature,22.0,2016-01-01T00:05:00.000Z\n"
        "sensor.kitchen_temperature,unavailable,2016-01-01T00:07:00.000Z\n"
        "light.hallway,off,2016-01-01T00:00:00.000Z\n"
        "light.hallway,on,2016-01-01T00:10:00.000Z\n"
        "sensor.kitchen_temperature,21.0,2016-01-01T00:20:00.000Z\n",
        encoding="utf-8",
    )
    h = load_home_assistant(p)
    kinds = {s.id: s.kind for s in h.sensors}
    assert kinds == {"sensor.kitchen_temperature": "temperature", "light.hallway": "light"}
    t = h.df["sensor.kitchen_temperature"]
    assert abs(t.loc["2016-01-01 00:00"] - 21.0) < 1e-9  # 5 min at 20, 5 min at 22
    assert h.df.loc["2016-01-01 00:10", "light.hallway"] == 1.0
    assert h.sensor("sensor.kitchen_temperature").room == "kitchen"
