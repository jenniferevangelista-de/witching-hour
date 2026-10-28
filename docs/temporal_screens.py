"""Screenshots of the local Temporal UI (python docs/temporal_screens.py NIGHTS OUT_DIR)."""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

nights = sys.argv[1].split(",")
out = Path(sys.argv[2] if len(sys.argv) > 2 else "out")
base = "http://localhost:8233/namespaces/default/workflows"

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page.goto(base, wait_until="networkidle")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(out / "temporal-workflows.png"))
    for n in nights:
        d = json.loads((out / f"describe-{n}.json").read_text(encoding="utf-8"))
        run_id = d["workflowExecutionInfo"]["execution"]["runId"]
        page.goto(f"{base}/night-watch-{n}/{run_id}/history", wait_until="networkidle")
        page.wait_for_timeout(2500)
        page.screenshot(path=str(out / f"temporal-{n}.png"), full_page=True)
    b.close()
print("ok")
