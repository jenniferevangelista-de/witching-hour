"""Screenshots of the running app for the README (python docs/screens.py BASE_URL OUT_DIR)."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screens")
night = sys.argv[3] if len(sys.argv) > 3 else ""
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    try:  # Google Chrome plays the H.264 demo clip; the bundled Chromium cannot
        browser = p.chromium.launch(channel="chrome")
    except Exception:  # noqa: BLE001
        browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2, color_scheme="dark")
    page.goto(f"{base}/#{night}" if night else base, wait_until="networkidle")
    page.wait_for_selector(".story, .notice", timeout=20000)
    page.wait_for_timeout(800)
    page.screenshot(path=str(out / "full.png"), full_page=True)
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=str(out / "top.png"))
    page.locator("#night").screenshot(path=str(out / "night-medium.png"))
    page.click("button[data-mode=skeptic]")
    page.wait_for_timeout(400)
    page.locator("#night").screenshot(path=str(out / "night-skeptic.png"))
    first_cite = page.locator(".cite").first
    if first_cite.count():
        first_cite.hover()
        page.wait_for_timeout(300)
        page.locator("#night").screenshot(path=str(out / "night-cite-hover.png"))
    page.locator("#eval").screenshot(path=str(out / "benchmark.png"))
    page.locator(".ask .panel").screenshot(path=str(out / "agent.png"))

    page.goto(base, wait_until="networkidle")
    page.wait_for_timeout(1200)
    page.locator("#crew").screenshot(path=str(out / "crew.png"))
    page.locator("header.hero").screenshot(path=str(out / "hero.png"))
    for mode in ("skeptic", "family"):
        page.goto(f"{base}/#{night}" if night else base, wait_until="networkidle")
        page.wait_for_selector(".bubble", timeout=20000)
        page.click(f"button.tab.{mode}")
        page.wait_for_timeout(500)
        page.locator("#night").screenshot(path=str(out / f"night-{mode}.png"))
    for sel, name in (("#tonight", "tonight.png"), ("#bakeoff-sec", "bakeoff.png"), ("footer.ofrenda", "ofrenda.png")):
        if page.locator(sel).count() and page.locator(sel).is_visible():
            page.locator(sel).screenshot(path=str(out / name))

    cover = browser.new_page(viewport={"width": 1000, "height": 420}, device_scale_factor=2, color_scheme="dark")
    cover.goto(base, wait_until="networkidle")
    cover.wait_for_timeout(1200)
    cover.evaluate("""() => {
      document.querySelector('.tagline').style.display = 'none';
      document.querySelector('.doors').style.display = 'none';
      document.querySelectorAll('.card p, .card q').forEach(e => e.style.display = 'none');
      document.querySelector('header.hero').scrollIntoView();
    }""")
    cover.screenshot(path=str(out / "cover.png"))

    # The Unheard: open the demo case, let the browser find the evidence, replay the recorded seance
    uh = browser.new_page(viewport={"width": 1280, "height": 900}, device_scale_factor=2, color_scheme="dark")
    uh.goto(base, wait_until="networkidle")
    uh.locator("nav.doors").screenshot(path=str(out / "doors.png"))
    uh.click("#uh-demo")
    try:
        uh.wait_for_function("document.querySelectorAll('#uh-evidence .event').length > 0", timeout=120000)
        uh.wait_for_timeout(600)
        uh.locator("section.terminal").first.screenshot(path=str(out / "unheard.png"))
        if uh.locator("#uh-replay").is_visible():
            uh.click("#uh-replay")
            n = uh.evaluate("fetch('/api/demo/cases').then(r => r.json()).then(c => c.cases[0].seance.turns.length)")
            uh.wait_for_function(f"document.querySelectorAll('#uh-turns li').length >= {n}", timeout=240000)
            uh.wait_for_timeout(1500)
            uh.locator("section.terminal").first.screenshot(path=str(out / "seance.png"))
    except Exception as e:  # noqa: BLE001
        print("the unheard capture failed:", e)

    phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3, color_scheme="dark")
    phone.goto(f"{base}/#{night}" if night else base, wait_until="networkidle")
    phone.wait_for_selector(".story, .notice", timeout=20000)
    phone.wait_for_timeout(800)
    phone.screenshot(path=str(out / "phone.png"), full_page=False)
    browser.close()
print("saved to", out)
