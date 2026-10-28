from witching_hour.atlas_memory import case_text
from witching_hour.season import cost, keep_grounded
from witching_hour.tiger_store import rrf


def test_ultramarine_cost_uses_published_prices():
    usage = {"prompt_tokens": 20000, "completion_tokens": 1500, "prompt_tokens_details": {"cached_tokens": 4000}}
    # 16k fresh * 0.15 + 4k cached * 0.03 + 1.5k out * 0.50, per million
    assert cost(usage) == round((16000 * 0.15 + 4000 * 0.03 + 1500 * 0.50) / 1e6, 6)
    assert cost({}) == 0.0


def test_season_findings_must_cite_known_nights():
    report = {"findings": [
        {"text": "The machines wake at 05:40 on weekdays.", "nights": ["2016-04-19", "2016-04-28"]},
        {"text": "A ghost every full moon.", "nights": ["2016-13-01"]},
        {"text": "No nights cited.", "nights": []},
    ]}
    kept, dropped = keep_grounded(report, {"2016-04-19", "2016-04-28"})
    assert [k["text"] for k in kept] == ["The machines wake at 05:40 on weekdays."] and len(dropped) == 2


def test_rrf_rewards_items_found_by_both_searches():
    fused = rrf([["a", "b", "c"], ["c", "a", "d"]])
    assert fused[0][0] == "a" and {x for x, _ in fused} == {"a", "b", "c", "d"}


def test_case_text_joins_what_matters():
    doc = {"night": "2016-03-09", "weekday": "Wednesday", "apparitions": ["living room cold"], "cold_rooms": [],
           "medium": "A cold spot arrived.", "family": "Check the heating."}
    t = case_text(doc)
    assert t.startswith("Wednesday 2016-03-09") and "A cold spot arrived." in t and "Check the heating." in t
