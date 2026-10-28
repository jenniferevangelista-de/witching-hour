"""Dr. Bigotes's field trip: check the official warnings in a real browser.

Before blaming a ghost for a cold night, the Skeptic looks at the official
weather warnings for the house's country. The warnings page is a JavaScript app,
so it needs a real browser: a Browserbase cloud browser, driven with Playwright.
The page text goes to the agent as a tool result; a screenshot goes to the demo.
"""
from __future__ import annotations

import base64
import os
import re
from datetime import datetime, timezone

WARNINGS_URL = "https://meteoalarm.org/en/live/region/BE"
COLD = re.compile(r"low[- ]temperature|extreme(ly)? low|cold|frost|snow|ice|icy", re.I)


NONE = re.compile(r"no results for this filter|no (active )?warnings|no particular awareness", re.I)


def summarize(text: str, limit: int = 700) -> dict:
    """Keep the lines that mention warnings and say whether any is about cold."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    keep = [ln for ln in lines if re.search(r"warning|alert|no results|no particular", ln, re.I)]
    cold = [ln for ln in keep if COLD.search(ln)]
    none = any(NONE.search(ln) for ln in lines) and not cold
    if none:
        excerpt = "No active warnings listed (the page said: " + next(ln for ln in lines if NONE.search(ln)) + ")"
    else:
        excerpt = " · ".join(keep)[:limit] or " ".join(lines)[:limit]
    return {"excerpt": excerpt[:limit], "cold_warning": bool(cold), "no_warnings": none, "cold_lines": cold[:5]}


def field_trip(url: str = WARNINGS_URL, screenshot_path: str | None = None) -> dict:
    import requests
    from playwright.sync_api import sync_playwright

    key, project = os.environ["BROWSERBASE_API_KEY"], os.environ["BROWSERBASE_PROJECT_ID"]
    headers = {"X-BB-API-Key": key, "Content-Type": "application/json"}
    r = requests.post("https://api.browserbase.com/v1/sessions", headers=headers, timeout=30, json={
        "projectId": project, "timeout": 120, "keepAlive": False,
        "browserSettings": {"viewport": {"width": 1280, "height": 900}}})
    r.raise_for_status()
    sess = r.json()
    out = {"url": url, "via": "Browserbase cloud browser + Playwright", "session": sess.get("id"),
           "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(sess["connectUrl"], timeout=30000)
            try:
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.set_viewport_size({"width": 1280, "height": 900})
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(6000)  # the map and the list are rendered by JavaScript
                out["status"] = resp.status if resp else None
                out["title"] = (page.title() or "")[:120]
                text = page.inner_text("body", timeout=15000)
                out.update(summarize(text))
                shot = page.screenshot(type="png")
                if screenshot_path:
                    with open(screenshot_path, "wb") as f:
                        f.write(shot)
                    out["screenshot"] = os.path.basename(screenshot_path)
                else:
                    out["screenshot_b64"] = base64.b64encode(shot).decode()[:200]
            finally:
                browser.close()
    finally:
        if sess.get("id"):
            try:
                requests.post(f"https://api.browserbase.com/v1/sessions/{sess['id']}", headers=headers,
                              json={"projectId": project, "status": "REQUEST_RELEASE"}, timeout=10)
            except requests.RequestException:
                pass
    return out
