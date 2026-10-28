"""Screenshots of the running app for the README (python docs/screens.py BASE_URL OUT_DIR)."""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
out = Path(sys.argv[2] if len(sys.argv) > 2 else "docs/screens")
night = sys.argv[3] if len(sys.argv) > 3 else ""
out.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
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

    cover = browser.new_page(viewport={"width": 1000, "height": 420}, device_scale_factor=2, color_scheme="dark")
    cover.goto(f"{base}/#{night}" if night else base, wait_until="networkidle")
    cover.wait_for_timeout(800)
    cover.evaluate("document.querySelector('header.hero p:last-of-type').style.display='none'")
    cover.screenshot(path=str(out / "cover.png"))

    phone = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=3, color_scheme="dark")
    phone.goto(f"{base}/#{night}" if night else base, wait_until="networkidle")
    phone.wait_for_selector(".story, .notice", timeout=20000)
    phone.wait_for_timeout(800)
    phone.screenshot(path=str(out / "phone.png"), full_page=False)
    browser.close()
print("saved to", out)
