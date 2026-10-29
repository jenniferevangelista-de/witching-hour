"""Browser regressions using only synthetic media/devices on the CI runner."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="Install playwright to run browser regressions")
expect = pw.expect
ROOT = Path(__file__).resolve().parents[1]
QA = Path(os.environ.get("QA_ARTIFACT_DIR", str(ROOT / "artifacts" / "qa")))

@pytest.fixture(scope="session")
def web_server():
    QA.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(WH_DATA=str(ROOT / "demo_data"), WH_LIVE="0", WH_LLM="none",
               MONGODB_URI="", AUTH0_DOMAIN="", SENTRY_DSN="")
    base = f"http://127.0.0.1:{port}"
    with (QA / "server.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "witching_hour.app:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail("The QA server exited; see artifacts/qa/server.log")
                try:
                    with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail("The isolated QA server did not start within 20 seconds")
            yield base
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

@pytest.fixture(scope="session")
def browser():
    with pw.sync_playwright() as runner:
        instance = runner.chromium.launch(headless=True, args=[
            "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
        ])
        yield instance
        instance.close()

@pytest.fixture
def page(browser, web_server, request):
    context = browser.new_context(
        viewport={"width": 1200, "height": 900}, reduced_motion="reduce",
        permissions=["camera", "microphone"], accept_downloads=True,
    )
    page = context.new_page()
    page.set_default_timeout(15000)
    page.goto(web_server, wait_until="domcontentloaded")
    page.locator("#uh-seance").wait_for(state="attached")
    if request.node.name == "test_oversize_file_rejected_before_arraybuffer":
        page.evaluate("() => document.fonts.ready.then(() => null)")
        capture(page, "hero-desktop.png", ".hero")
        page.set_viewport_size({"width": 390, "height": 900})
        capture(page, "hero-mobile.png", ".hero")
        page.set_viewport_size({"width": 1200, "height": 900})
    yield page
    try:
        page.screenshot(path=str(QA / (request.node.name + ".png")), full_page=False)
    finally:
        context.close()

@pytest.fixture(scope="session")
def media(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required for the synthetic browser fixtures"
    out = tmp_path_factory.mktemp("synthetic-media")
    motion = out / "still-then-motion.webm"
    # Black for 3 s; the same rectangle then shifts position at 4 s without
    # changing total brightness. The quiet opening must not stop analysis.
    filters = (
        "drawbox=x=15:y=20:w=30:h=50:color=white:t=fill:enable='between(t,3,3.75)',"
        "drawbox=x=110:y=20:w=30:h=50:color=white:t=fill:enable='gte(t,4)'"
    )
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=black:s=160x90:r=4:d=6", "-vf", filters, "-an",
        "-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-threads", "1", str(motion),
    ], check=True, timeout=30)
    long_clip = out / "too-long.webm"
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=black:s=160x90:r=1:d=91", "-an",
        "-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-threads", "1", str(long_clip),
    ], check=True, timeout=30)
    return {"motion": motion, "long": long_clip}

def upload_and_wait(page, path):
    page.locator("#uh-file").set_input_files(str(path))
    expect(page.locator("#uh-status")).to_contain_text("measured moment", timeout=30000)
    expect(page.locator("#uh-open")).to_be_visible()
    expect(page.locator("#uh-open")).to_be_enabled()

def summon(page):
    with page.expect_response(lambda response:
        response.url.endswith("/api/sessions") and response.request.method == "POST") as created:
        page.locator("#uh-open").click()
    result = created.value.json()
    expect(page.locator("#uh-seance")).to_be_visible()
    expect(page.locator("#uh-ask input")).to_be_enabled()
    return result["session_id"]

def capture(page, name, selector):
    page.locator(selector).evaluate(
        "(element) => element.scrollIntoView({block: 'start', inline: 'nearest', behavior: 'instant'})"
    )
    page.screenshot(path=str(QA / name), full_page=False, animations="disabled")
    if name in {"hero-desktop.png", "hero-mobile.png", "room-desktop.png", "room-mobile.png"}:
        # Only this synthetic localhost app is emitted for remote visual review.
        # Each image is capped at 62.5 kB; four images cannot exceed 250 kB.
        picture = b""
        for quality in (65, 50, 35, 20):
            picture = page.screenshot(type="jpeg", quality=quality, full_page=False, animations="disabled")
            if len(picture) <= 62500:
                break
        if len(picture) > 62500:
            pytest.fail("QA image exceeded the safe log size; see PNG artifact")
        label = name.replace(".png", ".jpg")
        (QA / label).write_bytes(picture)
        encoded = base64.b64encode(picture).decode("ascii")
        print(f"WH_IMAGE_START:{label}", flush=True)
        for offset in range(0, len(encoded), 12000):
            print("WH_IMAGE_DATA:" + encoded[offset:offset + 12000], flush=True)
        print(f"WH_IMAGE_END:{label}", flush=True)

def allocation_probe(page):
    page.evaluate("""() => {
        window.__qaBufferReads = 0; window.__qaCreated = []; window.__qaRevoked = [];
        const read = File.prototype.arrayBuffer;
        File.prototype.arrayBuffer = function (...args) {
            window.__qaBufferReads++; return read.apply(this, args);
        };
        const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
        URL.createObjectURL = (blob) => {
            const url = create(blob); window.__qaCreated.push(url); return url;
        };
        URL.revokeObjectURL = (url) => { window.__qaRevoked.push(url); revoke(url); };
    }""")

def test_oversize_file_rejected_before_arraybuffer(page):
    allocation_probe(page)
    # "Up to 24 MiB" permits the boundary; one byte above must fail.
    page.locator("#uh-file").set_input_files({
        "name": "oversize.webm", "mimeType": "video/webm", "buffer": b"x" * (24 * 1024 * 1024 + 1),
    })
    expect(page.locator("#uh-status")).to_contain_text("up to 24 MiB")
    assert page.evaluate("window.__qaBufferReads") == 0
    assert page.evaluate("window.__qaCreated.length") == 0
    expect(page.locator("#uh-open")).to_be_hidden()
    expect(page.locator("#uh-demo")).to_be_enabled()

def test_duration_rejection_releases_video_and_url_before_decode(page, media):
    allocation_probe(page)
    page.locator("#uh-file").set_input_files(str(media["long"]))
    expect(page.locator("#uh-status")).to_contain_text("no longer than 90 seconds")
    assert page.evaluate("window.__qaBufferReads") == 0
    assert page.evaluate("window.__qaCreated") == page.evaluate("window.__qaRevoked")
    assert page.locator("#uh-video").get_attribute("src") is None
    expect(page.locator("#uh-open")).to_be_hidden()
    expect(page.locator("#uh-demo")).to_be_enabled()

def test_keyboard_selection_and_motion_after_still_opening(page, media):
    page.bring_to_front()
    trigger = page.get_by_role("button", name="Bring your own recording")
    expect(trigger).to_be_visible()
    expect(page.locator("#uh-file")).to_be_enabled()
    trigger.focus()
    expect(trigger).to_be_focused()
    with page.expect_file_chooser() as chosen:
        trigger.press("Enter")
    chosen.value.set_files(str(media["motion"]))
    expect(page.locator("#uh-status")).to_contain_text("measured moment", timeout=30000)
    motion = page.locator("#uh-evidence .event").filter(has=page.locator(".what", has_text="motion"))
    expect(motion).to_have_count(1)
    assert float(motion.locator(".ts").inner_text().rstrip("s")) >= 3.75
    expect(page.locator("#uh-status")).not_to_contain_text("background")
    expect(page.locator("#uh-evidence")).to_contain_text("relative signal intensity")
    capture(page, "unheard-desktop.png", "#uh-evidence")

def test_cancelled_session_cannot_restore_late_answer_after_new_file(page, media, web_server):
    upload_and_wait(page, media["motion"])
    sid = summon(page)
    page.evaluate("""() => {
        const getJSON = window.WH.getJSON;
        window.WH.getJSON = (url, options) => {
            if (url.includes("/api/sessions/") && url.endsWith("/ask")) {
                return new Promise((resolve) => { window.__qaLateReply = resolve; });
            }
            return getJSON(url, options);
        };
    }""")
    page.locator("#uh-ask input").fill("Is someone here?")
    page.locator("#uh-ask button").click()
    page.wait_for_function("typeof window.__qaLateReply === 'function'")
    with page.expect_response(lambda response: response.url.endswith(f"/api/sessions/{sid}/close")) as closed:
        page.locator("#uh-cancel").click()
    assert closed.value.status == 200
    assert page.request.get(f"{web_server}/api/sessions/{sid}").json()["state"] == "closed"
    upload_and_wait(page, media["motion"])
    late = {"question": "old case", "response": {
        "message": "LATE", "spoken": "stale reply", "animation_sequence": ["L", "A", "T", "E"],
        "by": "template", "fictional": True}, "grounding": {"related_evidence_ids": ["ev-001"]}}
    page.evaluate("(reply) => window.__qaLateReply(reply)", late)
    # Flush the reduced-motion zero-delay spell timers before checking absence.
    page.wait_for_timeout(150)
    expect(page.locator("#uh-seance")).to_be_hidden()
    expect(page.locator("#uh-turns li")).to_have_count(0)
    expect(page.locator("#uh-status")).not_to_contain_text("stale reply")

def test_replay_closes_live_session_and_preserves_actual_sources(page, media):
    measured = {"id": "ev-recorded", "type": "motion", "start": 4.0, "end": 4.25,
                "confidence": 0.8, "description": "a synthetic rectangle moved"}
    series = {"t": [i / 4 for i in range(24)], "brightness": [0.0] * 24,
              "motion": [0.0] * 24, "audio_db": []}
    turn = {"question": "Who is there?", "response": {
        "message": "YES", "spoken": "A fictional replay.", "animation_sequence": ["YES"],
        "fictional": True, "by": "fixture-response-model"}, "grounding": {"related_evidence_ids": ["ev-recorded"]}}
    demo = {"id": "the-warning", "video": "/qa/synthetic.webm", "story": "A staged synthetic QA case.",
        "evidence": [measured], "series": series, "seance": {
        "spirit": {"name": "Fixture Guardian", "title": "The Guardian", "archetype": "guardian",
                   "backstory": "An invented test character.", "goal": "to be noticed", "by": "fixture-identity-model"},
        "turns": [turn], "audio": {}}}
    page.route("**/api/demo/cases", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"cases": [demo]})))
    page.route("**/qa/synthetic.webm", lambda route: route.fulfill(
        status=200, content_type="video/webm", path=str(media["motion"])))
    page.locator("#uh-demo").click()
    expect(page.locator("#uh-replay")).to_be_visible(timeout=30000)
    expect(page.locator("#uh-open")).to_be_enabled()
    sid = summon(page)
    with page.expect_response(lambda response: response.url.endswith(f"/api/sessions/{sid}/close")) as closed:
        page.locator("#uh-replay").click()
    assert closed.value.status == 200
    expect(page.locator("#uh-status")).to_contain_text("Recorded séance complete", timeout=15000)
    expect(page.locator("#uh-ask")).to_be_hidden()
    expect(page.locator("#uh-turns li")).to_have_count(1)
    expect(page.locator("#uh-turns")).to_contain_text("fixture-response-model")
    expect(page.locator("#uh-seance .by")).to_have_text("fixture-identity-model")
    expect(page.locator("#uh-evidence [data-ev='ev-recorded']")).to_have_count(1)
    with page.expect_download() as downloaded:
        page.locator("#uh-dossier").click()
    dossier = Path(downloaded.value.path()).read_text(encoding="utf-8")
    assert "Fixture Guardian" in dossier and "fixture-identity-model" in dossier
    assert "fixture-response-model" in dossier
    capture(page, "session-recorded.png", "#uh-turns")

def test_camera_startup_failure_stops_acquired_tracks(page):
    page.evaluate("""() => {
        const getMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
        navigator.mediaDevices.getUserMedia = async (options) => {
            const stream = await getMedia(options); window.__qaTracks = stream.getTracks(); return stream;
        };
        const play = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function (...args) {
            return this.id === "rm-video" ? Promise.reject(new Error("Synthetic startup failure")) : play.apply(this, args);
        };
    }""")
    page.locator("#rm-start").click()
    expect(page.locator("#rm-status")).to_contain_text("Synthetic startup failure")
    assert page.evaluate("window.__qaTracks.length > 0 && window.__qaTracks.every(t => t.readyState === 'ended')")
    assert page.locator("#rm-video").evaluate("(video) => video.srcObject === null")
    expect(page.locator("#rm-seance-open")).to_be_hidden()
    expect(page.locator("#rm-start")).to_have_text("Turn on camera and microphone")

def test_camera_flash_is_not_motion_and_stop_releases_devices(page):
    page.evaluate("""() => {
        window.__qaFrame = 0;
        const pixels = CanvasRenderingContext2D.prototype.getImageData;
        CanvasRenderingContext2D.prototype.getImageData = function (...args) {
            if (args[2] === 160 && args[3] === 90) {
                const data = new Uint8ClampedArray(160 * 90 * 4);
                const value = ++window.__qaFrame > 20 ? 255 : 0;
                for (let i = 0; i < data.length; i += 4) {
                    data[i] = data[i + 1] = data[i + 2] = value; data[i + 3] = 255;
                }
                return new ImageData(data, 160, 90);
            }
            return pixels.apply(this, args);
        };
        AnalyserNode.prototype.getFloatTimeDomainData = function (buffer) { buffer.fill(0); };
    }""")
    page.locator("#rm-start").click()
    expect(page.locator("#rm-status")).to_contain_text("Listening locally")
    page.evaluate("window.__qaTracks = document.querySelector('#rm-video').srcObject.getTracks()")
    expect(page.locator("#rm-log")).to_contain_text("the light changed suddenly", timeout=10000)
    expect(page.locator("#rm-log li")).to_have_count(1)
    expect(page.locator("#rm-log")).not_to_contain_text("movement")
    assert page.locator("#rm-haunt").is_hidden()
    capture(page, "room-desktop.png", "#room + section")
    page.set_viewport_size({"width": 390, "height": 900})
    capture(page, "room-mobile.png", "#room + section")
    page.locator("#rm-start").click()
    expect(page.locator("#rm-status")).to_contain_text("Camera and microphone stopped")
    assert page.evaluate("window.__qaTracks.every(t => t.readyState === 'ended')")
    assert page.locator("#rm-video").evaluate("(video) => video.srcObject === null")
    expect(page.locator("#rm-seance-open")).to_be_hidden()
