from witching_hour.fieldwork import summarize


def test_summarize_keeps_warning_lines_and_spots_cold():
    text = "Meteoalarm\nBelgium\nYellow warning: low temperature in Hainaut\nGreen: no particular awareness required\nCookies"
    s = summarize(text)
    assert s["cold_warning"] is True
    assert "low temperature" in s["cold_lines"][0]
    assert "Cookies" not in s["excerpt"]


def test_summarize_without_warnings():
    s = summarize("Belgium\nNo warnings in force\nAbout us")
    assert s["cold_warning"] is False and "No warnings" in s["excerpt"]
