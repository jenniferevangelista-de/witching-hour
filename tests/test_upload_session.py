"""Recording/session isolation regressions for a remote CI runner.

Requires pytest, playwright + Chromium, and ffmpeg. These tests create only tiny
synthetic clips and mock every session/model request. They never use a personal
video, a model key, a camera or a microphone. Install this file under tests/;
WH_TEST_ROOT may alternatively point at the checkout when running a staging copy.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlparse

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="Recording isolation tests require Playwright and Chromium")
expect = pw.expect
ROOT = Path(os.environ.get("WH_TEST_ROOT", Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def isolation_server(tmp_path_factory):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update(WH_DATA=str(ROOT / "demo_data"), WH_LIVE="0", WH_LLM="none",
               BACKBOARD_API_KEY="", MONGODB_URI="", AUTH0_DOMAIN="", SENTRY_DSN="")
    base = f"http://127.0.0.1:{port}"
    log_path = tmp_path_factory.mktemp("recording-isolation") / "server.log"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "witching_hour.app:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail(f"Isolated server exited; inspect {log_path}")
                try:
                    with urllib.request.urlopen(base + "/api/health", timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(0.1)
            else:
                pytest.fail(f"Isolated server failed to start; inspect {log_path}")
            yield base
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@pytest.fixture(scope="session")
def isolation_browser():
    with pw.sync_playwright() as runner:
        browser = runner.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def isolation_clip(tmp_path_factory):
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "ffmpeg is required to create this synthetic CI fixture"
    clip = tmp_path_factory.mktemp("recording-isolation-media") / "personal-fixture.webm"
    # The rectangle appears before frame eight, then changes position without
    # changing its area. The clip has no sound and contains no real people.
    filters = (
        "drawbox=x=15:y=20:w=30:h=50:color=white:t=fill:enable='between(t,0.5,0.75)',"
        "drawbox=x=110:y=20:w=30:h=50:color=white:t=fill:enable='gte(t,1)'"
    )
    subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=black:s=160x90:r=4:d=3", "-vf", filters, "-an",
        "-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-threads", "1", str(clip),
    ], check=True, timeout=30)
    return clip


DEMO_EVENT = {"id": "demo-only", "type": "audio", "start": 0.5, "end": 0.75,
              "confidence": 0.9, "description": "DEMO_ONLY_EVENT"}
DEMO_SPIRIT = {"name": "Demo Guardian", "title": "The Guardian", "archetype": "guardian",
               "backstory": "DEMO_ONLY_BACKSTORY", "goal": "DEMO_ONLY_GOAL", "by": "fixture-demo"}
DEMO_TURN = {"question": "DEMO QUESTION", "response": {
    "message": "YES", "spoken": "DEMO_ONLY_ANSWER", "animation_sequence": ["YES"],
    "fictional": True, "by": "fixture-demo"}, "grounding": {"related_evidence_ids": ["demo-only"]}}


class SessionFixture:
    def __init__(self):
        self.created = []
        self.asked = []
        self.sessions = {}
        self.hold_next_ask = False
        self.pending = []
        self.model = "fixture-current"

    def handle(self, route):
        request = route.request
        path = urlparse(request.url).path
        if request.method == "POST" and path == "/api/sessions":
            payload = deepcopy(request.post_data_json)
            self.created.append(payload)
            sid = f"fixture-session-{len(self.created)}"
            response = {"session_id": sid, "model": self.model,
                "spirit": {"name": f"Current Spirit {len(self.created)}", "title": "The Watcher",
                    "archetype": "watcher", "backstory": "CURRENT_ONLY_BACKSTORY",
                    "goal": "respond to this recording", "by": self.model}}
            self.sessions[sid] = {"response": response, "evidence": payload["evidence"]}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(response))
            return
        parts = path.strip("/").split("/")
        if request.method == "POST" and len(parts) == 4 and parts[:2] == ["api", "sessions"]:
            sid, action = parts[2:]
            if action == "close":
                route.fulfill(status=200, content_type="application/json", body=json.dumps(
                    {"response": {"message": "GOODBYE", "fictional": True}}))
                return
            assert action == "ask" and sid in self.sessions, f"Unexpected fixture request: {path}"
            payload = request.post_data_json
            self.asked.append((sid, deepcopy(payload)))
            event_ids = [event["id"] for event in self.sessions[sid]["evidence"]]
            body = {"question": payload["question"], "spirit": self.sessions[sid]["response"]["spirit"],
                "response": {"message": "YES" if event_ids else "NO", "spoken": "CURRENT_ONLY_ANSWER",
                    "animation_sequence": ["YES" if event_ids else "NO"], "fictional": True,
                    "by": "template" if self.model.startswith("template spirits") else self.model}, "grounding": {"related_evidence_ids": event_ids[:1]}}
            if self.hold_next_ask:
                self.hold_next_ask = False
                body["response"]["spoken"] = "STALE_OLD_RESPONSE_MUST_NOT_APPEAR"
                self.pending.append((route, body))
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
            return
        raise AssertionError(f"Unexpected session/model request: {request.method} {path}")

    def release_old_response(self):
        route, body = self.pending.pop(0)
        try:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        except pw.Error:
            # Aborting the stale fetch is also a valid implementation. Do not
            # suppress another interception error when the request did not fail.
            if not route.request.failure:
                raise


@pytest.fixture
def isolation_page(isolation_browser, isolation_server, isolation_clip):
    context = isolation_browser.new_context(viewport={"width": 1200, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    page.set_default_timeout(20000)
    sessions = SessionFixture()
    page.route("https://**/*", lambda route: route.abort())
    page.route("**/api/sessions**", sessions.handle)
    page.route("**/api/seance/voices", lambda route: route.fulfill(
        status=200, content_type="application/json", body="{}"))
    demo = {"id": "the-warning", "video": "/qa/demo.webm", "story": "A staged synthetic demo.",
        "evidence": [DEMO_EVENT], "series": {"t": [i / 4 for i in range(12)],
            "brightness": [0.0] * 12, "motion": [0.0] * 12, "audio_db": []},
        "seance": {"spirit": DEMO_SPIRIT, "model": "fixture-demo", "context": "DEMO_ONLY_MEMORY",
            "turns": [DEMO_TURN], "audio": {}}}
    page.route("**/api/demo/cases", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({"cases": [demo]})))
    page.route("**/qa/demo.webm", lambda route: route.fulfill(
        status=200, content_type="video/webm", path=str(isolation_clip)))
    page.add_init_script("""(() => {
        const read = File.prototype.arrayBuffer;
        window.__qaHoldUpload = false;
        File.prototype.arrayBuffer = function (...args) {
            if (!window.__qaHoldUpload) return read.apply(this, args);
            return new Promise((resolve, reject) => {
                window.__qaReleaseUpload = () => read.apply(this, args).then(resolve, reject);
            });
        };
    })();""")
    page.goto(isolation_server + "/#unheard", wait_until="domcontentloaded")
    page.locator("#uh-seance").wait_for(state="attached")
    yield page, sessions
    context.close()


def open_demo(page):
    page.locator("#uh-demo").click()
    expect(page.locator("#uh-status")).to_have_attribute("data-state", "ready", timeout=30000)
    expect(page.locator("#uh-replay")).not_to_have_attribute("hidden", "")


def finish_demo_replay(page):
    page.locator("#uh-replay").click()
    expect(page.locator("#uh-turns li")).to_have_count(1)
    expect(page.locator("#uh-turns")).to_contain_text("DEMO_ONLY_ANSWER")


def upload_current(page, clip):
    page.locator("#uh-file").set_input_files(str(clip))
    expect(page.locator("#uh-status")).to_have_attribute("data-state", "ready", timeout=30000)
    expect(page.locator("#uh-status")).to_contain_text(clip.name)


def summon_current(page, sessions):
    previous = len(sessions.created)
    page.locator("#summon-panel").click()
    expect(page.locator("#uh-spirit")).to_contain_text(f"Current Spirit {previous + 1}")
    assert len(sessions.created) == previous + 1
    return f"fixture-session-{previous + 1}"


def ask_current(page, text="A fresh question"):
    page.locator("#uh-ask input").fill(text)
    page.locator("#uh-ask button").click()
    expect(page.locator("#uh-turns li")).to_have_count(1)
    expect(page.locator("#uh-turns")).to_contain_text("CURRENT_ONLY_ANSWER")


def test_upload_synchronously_clears_demo_and_blocks_summon_during_measurement(isolation_page, isolation_clip):
    page, sessions = isolation_page
    open_demo(page)
    finish_demo_replay(page)
    with page.expect_download() as exported:
        page.locator("#uh-dossier").click()
    dossier = Path(exported.value.path()).read_text(encoding="utf-8")
    assert "recorded séance from fixture-demo, replayed without a new model call" in dossier
    assert "made up by an open model" not in dossier
    page.locator("#uh-words").fill("DEMO_ONLY_MEMORY")
    page.evaluate("window.__qaHoldUpload = true")
    page.locator("#uh-file").set_input_files(str(isolation_clip))
    expect(page.locator("#uh-status")).to_have_attribute("data-state", "loading")
    expect(page.locator("#uh-words")).to_have_value("")
    expect(page.locator("#uh-turns li")).to_have_count(0)
    expect(page.locator("#uh-spirit")).to_have_text("")
    expect(page.locator("#uh-spelled")).to_have_text("")
    expect(page.locator("#uh-replay")).to_be_hidden()
    expect(page.locator("#uh-seance")).to_be_hidden()
    expect(page.locator("#summon-panel")).to_be_disabled()
    assert not sessions.created
    page.evaluate("window.__qaReleaseUpload()")
    expect(page.locator("#uh-status")).to_have_attribute("data-state", "ready", timeout=30000)
    expect(page.locator("#summon-panel")).to_be_enabled()


@pytest.mark.parametrize("reply_source", ["fixture-current", "template spirits (no model attached)"])
def test_personal_upload_creates_fresh_session_with_only_current_evidence(isolation_page, isolation_clip, reply_source):
    page, sessions = isolation_page
    sessions.model = reply_source
    open_demo(page)
    finish_demo_replay(page)
    upload_current(page, isolation_clip)
    current = page.evaluate("window.WH.evidenceFor('uh')")
    assert current and all(event["id"] != "demo-only" for event in current)
    sid = summon_current(page, sessions)
    sent = sessions.created[-1]
    assert sent["investigation"] == isolation_clip.name
    assert sent["context"] == ""
    assert sent["evidence"] == current
    expect(page.locator("#uh-turns li")).to_have_count(0)
    ask_current(page)
    assert sessions.asked[-1][0] == sid
    citations = page.locator("#uh-turns .cite").evaluate_all("nodes => nodes.map(node => node.dataset.ev)")
    assert set(citations).issubset({event["id"] for event in current})
    expect(page.locator("#uh-seance")).not_to_contain_text("DEMO_ONLY")
    with page.expect_download() as exported:
        page.locator("#uh-dossier").click()
    dossier = Path(exported.value.path()).read_text(encoding="utf-8")
    assert f"This session reports: {reply_source}." in dossier
    assert "Each reply's source is shown beside it." in dossier
    assert "made up by an open model" not in dossier
    assert "recorded séance from" not in dossier
    assert "DEMO_ONLY" not in dossier


def test_late_answer_from_previous_session_cannot_repaint_new_upload(isolation_page, isolation_clip):
    page, sessions = isolation_page
    upload_current(page, isolation_clip)
    old_sid = summon_current(page, sessions)
    sessions.hold_next_ask = True
    page.locator("#uh-ask input").fill("Old session question")
    page.locator("#uh-ask button").click()
    page.wait_for_function("document.querySelector('#uh-ask button').disabled")
    assert sessions.pending and sessions.asked[-1][0] == old_sid
    upload_current(page, isolation_clip)
    fresh_sid = summon_current(page, sessions)
    assert fresh_sid != old_sid
    sessions.release_old_response()
    # An absent stale update must remain absent after the old reduced-motion
    # sequence's maximum 3 x 700 ms reading holds would have completed.
    page.wait_for_timeout(3000)
    expect(page.locator("#uh-turns li")).to_have_count(0)
    expect(page.locator("#uh-seance")).not_to_contain_text("STALE_OLD_RESPONSE")
    expect(page.locator("#uh-spirit")).to_contain_text("Current Spirit 2")
    ask_current(page, "New session question")
    assert sessions.asked[-1][0] == fresh_sid


def test_inflight_recorded_replay_cannot_restore_demo_after_upload(isolation_page, isolation_clip):
    page, sessions = isolation_page
    open_demo(page)
    page.evaluate("""() => {
        const ask = window.WH.stage.ask.bind(window.WH.stage);
        window.WH.stage.ask = (...args) => {
            if (args[0] === 'uh' && args[1] === 'DEMO QUESTION') {
                return new Promise(resolve => {
                    window.__qaReleaseReplay = () => Promise.resolve(ask(...args)).then(resolve);
                });
            }
            return ask(...args);
        };
    }""")
    page.locator("#uh-replay").click()
    page.wait_for_function("typeof window.__qaReleaseReplay === 'function'")
    upload_current(page, isolation_clip)
    current = page.evaluate("window.WH.evidenceFor('uh')")
    summon_current(page, sessions)  # Re-activating the stage must not revive its older revision.
    page.evaluate("window.__qaReleaseReplay()")
    page.wait_for_timeout(3000)
    assert page.evaluate("window.WH.evidenceFor('uh')") == current
    expect(page.locator("#uh-turns li")).to_have_count(0)
    expect(page.locator("#uh-seance")).not_to_contain_text("DEMO_ONLY")
    expect(page.locator("#uh-replay")).to_be_hidden()
    expect(page.locator("#uh-spirit")).to_contain_text("Current Spirit 1")


def test_second_summon_starts_a_new_transcript_and_session(isolation_page, isolation_clip):
    page, sessions = isolation_page
    upload_current(page, isolation_clip)
    first_sid = summon_current(page, sessions)
    ask_current(page, "First session question")
    # The original design hides its Summon proxy during an active session. The
    # real action remains the public UI handler, invoked here without a layout change.
    page.locator("#uh-open").evaluate("button => button.click()")
    expect(page.locator("#uh-spirit")).to_contain_text("Current Spirit 2")
    assert len(sessions.created) == 2
    expect(page.locator("#uh-turns li")).to_have_count(0)
    expect(page.locator("#uh-spelled")).to_have_text("")
    ask_current(page, "Second session question")
    assert sessions.asked[-1][0] != first_sid
    expect(page.locator("#uh-turns")).not_to_contain_text("First session question")
