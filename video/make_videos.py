"""The two Witching Hour videos.

1. The film: the crew introduce themselves and the three cases, over the app's own screenshots.
2. The tour: a real recording of the running app (Playwright + Chrome), narrated by Luna.

python video/make_videos.py BASE_URL OUT_DIR      (the app must be running at BASE_URL)
Needs: ffmpeg, edge-tts, Pillow, numpy, cairosvg, playwright.
"""
from __future__ import annotations

import hashlib
import json
import re
import textwrap
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "video/out")
WORK = OUT / "work"
SHOTS = ROOT / "docs" / "screens"
W, H, FPS, SR = 1920, 1080, 24, 24000
VOICE = {"luna": "en-US-AvaMultilingualNeural", "bigotes": "en-GB-RyanNeural", "xochi": "en-US-EmmaMultilingualNeural"}
NAME = {"luna": ("Luna", "the Medium", (255, 191, 60)), "bigotes": ("Dr. Bigotes", "the Skeptic", (121, 207, 161)),
        "xochi": ("Xochi", "the Night Watch", (240, 98, 146))}


def run(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def pcm(path: Path) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def say(who: str, text: str, name: str) -> Path:
    rate = "-4%"
    fingerprint = hashlib.sha256(
        f"{VOICE[who]}\0{rate}\0{text}".encode("utf-8")
    ).hexdigest()[:12]
    p = WORK / "voice" / f"{name}_{fingerprint}.mp3"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        run(
            "edge-tts", "--voice", VOICE[who], f"--rate={rate}",
            "--text", text, "--write-media", str(p),
        )
    return p


def warning_case() -> dict:
    cases = json.loads(
        (ROOT / "demo_data" / "cases.json").read_text(encoding="utf-8")
    )["cases"]
    return next(case for case in cases if case["id"] == "the-warning")


def recorded_guardian(case: dict, index: int = 0) -> tuple[Path, str]:
    turn = case["seance"]["turns"][index]
    if turn["response"].get("fictional") is not True:
        raise ValueError("The recorded Guardian reply must be labelled fictional.")
    audio = case["seance"]["audio"][index]
    if not audio:
        raise ValueError("The selected Guardian reply has no recorded audio.")
    path = ROOT / "demo_data" / "media" / audio.removeprefix("/media/")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path, turn["response"]["spoken"]


def pad(seconds: float) -> np.ndarray:
    """A soft A-minor drone with a slow shimmer, for under the voices."""
    t = np.arange(int(seconds * SR)) / SR
    x = np.zeros_like(t)
    for f, a in ((110, .5), (130.81, .35), (164.81, .35), (220, .2), (329.63, .08)):
        x += a * np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * .07 * t))
    x *= .55 + .45 * np.sin(2 * np.pi * .05 * t) ** 2
    fade = np.minimum(1, np.minimum(t / 3, (seconds - t) / 3))
    return (x / np.abs(x).max() * .035 * fade).astype(np.float32)


def write_wav(x: np.ndarray, path: Path):
    x = np.clip(x, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype(np.int16).tobytes())


def srt(cues: list[tuple[float, float, str]], path: Path):
    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    path.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)), encoding="utf-8")


SUB_STYLE = "FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00201030,BorderStyle=3,Outline=1,Shadow=0,MarginV=28"


# ------------------------------------------------------------------ drawing helpers


def font(name: str, size: int):
    for p in (WORK / name, Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")):
        try:
            return ImageFont.truetype(str(p), size)
        except OSError:
            continue
    return ImageFont.load_default()


def get_fonts():
    for fname, url in (("Creepster.ttf", "https://github.com/google/fonts/raw/main/ofl/creepster/Creepster-Regular.ttf"),):
        p = WORK / fname
        if not p.exists():
            try:
                urllib.request.urlretrieve(url, p)
            except Exception:  # noqa: BLE001
                pass


def avatar(who: str, size: int) -> Image.Image:
    import cairosvg

    p = WORK / f"{who}_{size}.png"
    if not p.exists():
        cairosvg.svg2png(url=str(ROOT / "witching_hour" / "static" / "characters" / f"{who}.svg"),
                         write_to=str(p), output_width=size)
    return Image.open(p).convert("RGBA")


def backdrop() -> Image.Image:
    y = np.linspace(0, 1, H)[:, None, None]
    a = np.array([27, 16, 56]) * (1 - y) + np.array([10, 7, 26]) * y
    img = Image.fromarray(np.broadcast_to(a, (H, W, 3)).astype(np.uint8))
    d = ImageDraw.Draw(img)
    colors = [(255, 191, 60), (240, 98, 146), (121, 207, 161), (167, 123, 255), (217, 72, 91), (99, 179, 237)]
    for i in range(24):  # papel picado
        x0 = i * 80
        d.polygon([(x0 + 4, 0), (x0 + 76, 0), (x0 + 76, 46), (x0 + 40, 62), (x0 + 4, 46)], fill=colors[i % 6])
        for k in range(3):
            d.ellipse([x0 + 16 + k * 18, 18, x0 + 26 + k * 18, 28], fill=(27, 16, 56))
    rng = np.random.default_rng(7)
    for _ in range(90):  # stars
        x, yy = int(rng.integers(0, W)), int(rng.integers(80, H))
        d.point((x, yy), fill=(220, 210, 255))
    return img


def fit(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    img = img.copy()
    img.thumbnail(box, Image.LANCZOS)
    return img


def rounded(img: Image.Image, r: int = 22) -> Image.Image:
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.size[0] - 1, img.size[1] - 1], r, fill=255)
    out = img.convert("RGBA")
    out.putalpha(m)
    return out


def frame_shot(shot: str, who: str, title: str, crop_top: float | None = None) -> Image.Image:
    img = backdrop().convert("RGBA")
    d = ImageDraw.Draw(img)
    d.text((W // 2, 104), title, font=font("Creepster.ttf", 64), fill=(141, 255, 207), anchor="mm")
    s = Image.open(SHOTS / shot).convert("RGB")
    if crop_top is not None:  # tall captures: keep a 16:10 window starting at this fraction
        h = int(s.width * 0.62)
        y0 = int((s.height - h) * crop_top)
        s = s.crop((0, y0, s.width, y0 + h))
    s = rounded(fit(s, (1420, 800)))
    x, y = 420 + (1420 - s.width) // 2, 150 + (800 - s.height) // 2
    shadow = Image.new("RGBA", (s.width + 40, s.height + 40), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([20, 20, s.width + 20, s.height + 20], 22, fill=(0, 0, 0, 150))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)), (x - 20, y - 6))
    img.alpha_composite(s, (x, y))
    speaker(img, who)
    return img.convert("RGB")


def speaker(img: Image.Image, who: str):
    a = avatar(who, 300)
    img.alpha_composite(a, (60, 560 - a.height // 2))
    name, role, color = NAME[who]
    d = ImageDraw.Draw(img)
    d.text((210, 780), name, font=font("x", 40), fill=color, anchor="mm")
    d.text((210, 826), role, font=font("x", 26), fill=(205, 196, 230), anchor="mm")


def frame_character(who: str, line1: str, quote: str) -> Image.Image:
    img = backdrop().convert("RGBA")
    a = avatar(who, 560)
    img.alpha_composite(a, (170, 560 - a.height // 2))
    name, role, color = NAME[who]
    d = ImageDraw.Draw(img)
    d.text((860, 330), name, font=font("Creepster.ttf", 120), fill=color, anchor="lm")
    d.text((866, 440), role.upper(), font=font("x", 40), fill=(205, 196, 230), anchor="lm")
    y = 520
    for chunk in wrap(line1, 46):
        d.text((866, y), chunk, font=font("x", 36), fill=(240, 234, 255), anchor="lm")
        y += 52
    d.text((866, y + 30), quote, font=font("x", 36), fill=color, anchor="lm")
    return img.convert("RGB")


def frame_card(title: str, rows: list[str], who: str) -> Image.Image:
    img = backdrop().convert("RGBA")
    d = ImageDraw.Draw(img)
    d.text((W // 2 + 180, 170), title, font=font("Creepster.ttf", 80), fill=(141, 255, 207), anchor="mm")
    cols = 2
    for i, r in enumerate(rows):
        cx, cy = 560 + (i % cols) * 680, 290 + (i // cols) * 98
        d.rounded_rectangle([cx, cy, cx + 640, cy + 80], 18, fill=(42, 29, 85), outline=(90, 70, 150), width=3)
        d.text((cx + 26, cy + 40), r, font=font("x", 32), fill=(240, 234, 255), anchor="lm")
    speaker(img, who)
    return img.convert("RGB")


def frame_title(line: str, sub: str) -> Image.Image:
    img = backdrop().convert("RGBA")
    d = ImageDraw.Draw(img)
    d.text((W // 2, 300), "WITCHING HOUR", font=font("Creepster.ttf", 170), fill=(141, 255, 207), anchor="mm")
    d.text((W // 2, 450), line, font=font("Creepster.ttf", 58), fill=(255, 191, 60), anchor="mm")
    for i, who in enumerate(("luna", "bigotes", "xochi")):
        a = avatar(who, 300)
        img.alpha_composite(a, (W // 2 - 520 + i * 380, 560))
    d.text((W // 2, 1000), sub, font=font("x", 30), fill=(205, 196, 230), anchor="mm")
    return img.convert("RGB")


def wrap(text: str, n: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > n:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return out + ([cur] if cur else [])


# ------------------------------------------------------------------ 1. the film

FILM = [
    ("title",
     ("What if a ghost story cited its sources?",
      "Halloween · Día de los Muertos · real measurements, fictional spirits"),
     [("luna", "I'm Luna. What if a ghost story had to cite its sources? "
               "The measurements are real. The spirits are fiction.")]),

    ("shot", ("warning-9_4.png", "xochi", "The Unheard · a staged case", None),
     [("xochi", "I'm Xochi, the night watch. In this staged clip, a flicker, "
                "a sound and a shadow interrupt a journey to the door.")]),

    ("shot", ("seance.png", "bigotes", "Five measured moments", 0.35),
     [("bigotes", "I'm Doctor Bigotes. Five measured moments, with ordinary "
                  "explanations. A buzz beside the flicker? I'd check the bulb.")]),

    ("shot", ("seance.png", "luna", "One recorded, fictional reply", 0.0),
     [("luna", "I turn those events into fiction. Here is one recorded Guardian "
               "reply, inspired by the evidence. Is someone here?")],
     0),

    ("shot", ("top.png", "bigotes", "The House · learning its own pattern", None),
     [("bigotes", "The House uses real Belgian sensor logs. TabPFN learns from "
                  "the previous fortnight and predicts a range for each "
                  "ten-minute slot.")]),

    ("shot", ("night-medium.png", "luna", "One event, three readings", 0.0),
     [("luna", "Appliance energy: three hundred and eighty watt-hours at five "
               "forty, against an expected fifty two. Same event, three voices: "
               "story, explanation and morning note.")]),

    ("shot", ("night-skeptic.png", "bigotes", "Checks have limits", 0.0),
     [("bigotes", "Generated narrations face citation and numeric checks. "
                  "That does not verify every explanation. Quiet-night "
                  "summaries are scripted.")]),

    ("shot", ("benchmark.png", "bigotes", "An exploratory benchmark", None),
     [("bigotes", "In an exploratory planted-anomaly benchmark, TabPFN caught "
                  "twenty five percent at a five-percent false-alarm threshold. "
                  "LightGBM caught about ten.")]),

    ("shot", ("doors.png", "xochi", "The Room · footage stays in the browser", None),
     [("xochi", "The Room measures camera and microphone locally. Footage stays "
                "in your browser. Measured events and your questions go to "
                "the board's server.")]),

    ("card",
     ("Open models, optional services",
      ["TabPFN · quantile forecasts", "Gemma · local narration",
       "Optional cloud integrations", "Video narration · Edge TTS",
       "Guardian · ElevenLabs", "Public demo · Render"],
      "bigotes"),
     [("bigotes", "Open models can run at home. Cloud integrations are optional. "
                  "This video's narration uses Microsoft Edge TTS. "
                  "The recorded Guardian uses ElevenLabs.")]),

    ("title",
     ("Measure first. Mark the fiction.",
      "witching-hour.onrender.com · github.com/jenniferevangelista-de/witching-hour"),
     [("luna", "Three cases. Measurements first, fiction clearly marked."),
      ("xochi", "And the feeling is yours.")]),
]


def make_film():
    get_fonts()
    case = warning_case()
    clips, cues, voice_track, t = [], [], [], 0.0
    for i, scene in enumerate(FILM):
        kind, args, lines = scene[0], scene[1], scene[2]
        extra_index = scene[3] if len(scene) > 3 else None
        frame = {"title": frame_title, "character": frame_character, "card": frame_card,
                 "shot": frame_shot}[kind](*args)
        png = WORK / f"film_{i:02d}.png"
        frame.save(png)
        audio = [np.zeros(int(.5 * SR), np.float32)]
        start = t + .5
        for j, (who, text) in enumerate(lines):
            clip = pcm(say(who, text, f"film_{i:02d}_{j}"))
            cues += [(start + a, start + b, txt) for a, b, txt in split_cue(text, len(clip) / SR)]
            audio += [clip, np.zeros(int(.35 * SR), np.float32)]
            start += len(clip) / SR + .35
        if extra_index is not None:
            extra, spoken = recorded_guardian(case, extra_index)
            clip = pcm(extra)
            cues += [
                (start + a, start + b, text)
                for a, b, text in split_cue(f"“{spoken}”", len(clip) / SR)
            ]
            audio += [clip, np.zeros(int(.4 * SR), np.float32)]
        audio.append(np.zeros(int(.6 * SR), np.float32))
        seg = np.concatenate(audio)
        n = int(np.ceil(len(seg) / SR * FPS))
        seg = np.pad(seg, (0, n * SR // FPS - len(seg)))  # audio exactly as long as the clip
        voice_track.append(seg)
        dur = n / FPS
        mp4 = WORK / f"film_{i:02d}.mp4"
        run("ffmpeg", "-y", "-loop", "1", "-i", str(png), "-vf",
            f"scale=2880:-2,zoompan=z='min(zoom+0.00035,1.05)':d={n}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={FPS},"
            f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(dur - .4, 0):.2f}:d=0.4",
            "-frames:v", str(n), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "veryfast", str(mp4))
        clips.append(mp4)
        t += n / FPS
        print(f"film scene {i}: {dur:.1f}s", flush=True)
    finish("witching_hour_film", clips, np.concatenate(voice_track), cues)


def split_cue(text: str, seconds: float) -> list[tuple[float, float, str]]:
    """Phrase-oriented subtitles with estimated, not word-aligned, timing."""
    text = " ".join(text.split())
    if not text or seconds <= 0:
        return []

    clauses = re.split(r"(?<=[.!?;:,])\s+", text)
    units = [
        piece
        for clause in clauses
        for piece in textwrap.wrap(
            clause, width=70,
            break_long_words=False, break_on_hyphens=False,
        )
    ]

    parts = []
    for unit in units:
        if parts and len(parts[-1]) + 1 + len(unit) <= 70:
            parts[-1] += " " + unit
        else:
            parts.append(unit)

    while len(parts) > 1:
        total = sum(len(part) for part in parts)
        short = next(
            (
                i for i, part in enumerate(parts)
                if seconds * len(part) / total < 1.0
                or (i == len(parts) - 1 and len(part.split()) == 1)
            ),
            None,
        )
        if short is None:
            break
        if short == 0:
            join = 0
        elif short == len(parts) - 1:
            join = short - 1
        else:
            join = (
                short - 1
                if len(parts[short - 1]) <= len(parts[short + 1])
                else short
            )
        parts[join:join + 2] = [" ".join(parts[join:join + 2])]

    total = sum(len(part) for part in parts)
    cues, start = [], 0.0
    for i, part in enumerate(parts):
        end = (
            seconds if i == len(parts) - 1
            else start + seconds * len(part) / total
        )
        cues.append((start, end, part))
        start = end
    return cues


def finish(name: str, clips: list[Path], voice: np.ndarray, cues):
    lst = WORK / f"{name}.txt"
    lst.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    silent = WORK / f"{name}_silent.mp4"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(silent))
    mix_and_mux(name, silent, voice, cues)


def mix_and_mux(name: str, video: Path, voice: np.ndarray, cues):
    vdur = duration(video)
    n = int(vdur * SR)
    voice = np.pad(voice, (0, max(0, n - len(voice))))[:n]
    wav = WORK / f"{name}.wav"
    write_wav(voice * .9 + pad(vdur), wav)
    sub = OUT / f"{name}.srt"
    srt(cues, sub)
    out = OUT / f"{name}.mp4"
    subpath = sub.resolve().as_posix().replace(":", r"\:")
    run("ffmpeg", "-y", "-i", str(video), "-i", str(wav), "-vf", f"subtitles='{subpath}':force_style='{SUB_STYLE}'",
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", str(out))
    print(f"{out}: {duration(out):.1f}s", flush=True)


# ------------------------------------------------------------------ 2. the tour

CURSOR_JS = """
(() => {
  const c = document.createElement('div');
  c.style.cssText = 'position:fixed;z-index:99999;width:22px;height:22px;border-radius:50%;pointer-events:none;' +
    'background:rgba(255,191,60,.9);box-shadow:0 0 0 4px rgba(255,191,60,.35);left:-50px;top:-50px;transition:transform .1s';
  const add = () => document.body && !c.isConnected && document.body.appendChild(c);
  document.addEventListener('mousemove', (e) => { add(); c.style.left = (e.clientX - 11) + 'px'; c.style.top = (e.clientY - 11) + 'px'; }, true);
  document.addEventListener('mousedown', () => { c.style.transform = 'scale(.7)'; }, true);
  document.addEventListener('mouseup', () => { c.style.transform = ''; }, true);
})();
"""

TOUR = [
    ("open", "I'm Luna. Welcome to a recorded tour of Witching Hour. "
             "The measurements are real; the spirits are fictional."),
    ("map", "The House: real sensor logs, one square per night. "
            "TabPFN flags unusual readings in ten-minute slots."),
    ("night", "April nineteenth: at five forty, appliance energy reached "
              "three hundred and eighty watt-hours. Expected: about fifty two."),
    ("skeptic", "Bigotes offers an ordinary explanation. This citation "
                "highlights the event he is using. Citation and numeric "
                "checks do not verify every explanation."),
    ("family", "Xochi turns that same event into a morning note for the family."),
    ("tonight", "This saved forecast combines fetched weather with historical "
                "house data. It is not a current reading from a lived-in home."),
    ("unheard", "The Warning is staged. We analyze its footage in the browser, "
                "then keep the measured moments as evidence."),
    ("evidence", "The flicker, a buzz, a soft sound, knocks and motion. "
                 "Bigotes offers ordinary possibilities."),
    ("replay", "Here is one reply from the recorded Guardian session. "
               "The voice is ElevenLabs; the character and message are fiction."),
    ("room", "The Room measures a camera and microphone. This demonstration "
             "uses Chrome's test pattern, not anyone's private room. "
             "Footage stays in the browser; measured events go to the server."),
    ("summon", "I asked, Is someone here? This answer is fiction. "
               "The provider label names the model or template that answered."),
    ("benchmark", "The planted-anomaly benchmark compares TabPFN with two "
                  "baselines. These exploratory results do not guarantee "
                  "performance in another home."),
    ("bakeoff", "The model comparison also records invalid JSON. The local "
                "Gemma reference allowed a retry; the remote runs did not."),
    ("apprentice", "Tinker fine-tuning improved this validator score on later "
                   "nights. It did not make responses faster."),
    ("credits", "Tour narration uses Microsoft Edge TTS. The recorded Guardian "
                "uses ElevenLabs. Open models can run at home; "
                "cloud integrations are optional."),
    ("end", "Measure first. Mark the fiction. Explore Witching Hour."),
]


def make_tour():
    from playwright.sync_api import sync_playwright

    lines = {
        key: (pcm(say("luna", text, f"tour_{key}")), text)
        for key, text in TOUR
    }
    case = warning_case()
    guardian_path, guardian_text = recorded_guardian(case, 0)
    guardian_audio = pcm(guardian_path)
    marks, turns = [], []
    rec = WORK / "rec"

    with sync_playwright() as p:
        args = [
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--autoplay-policy=no-user-gesture-required",
        ]
        try:
            browser = p.chromium.launch(channel="chrome", args=args)
        except Exception:
            browser = p.chromium.launch(args=args)

        ctx = browser.new_context(
            viewport={"width": W, "height": H},
            record_video_dir=str(rec),
            record_video_size={"width": W, "height": H},
            color_scheme="dark",
        )
        ctx.grant_permissions(["camera", "microphone"], origin=BASE)
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        t0 = time.monotonic()
        now = lambda: time.monotonic() - t0

        def glide(sel, click=False):
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=15000)
            loc.scroll_into_view_if_needed()
            box = loc.bounding_box()
            if box is None:
                raise RuntimeError(f"Capture target has no visible box: {sel}")
            page.mouse.move(
                box["x"] + box["width"] / 2,
                box["y"] + box["height"] / 2,
                steps=18,
            )
            if click:
                page.mouse.click(
                    box["x"] + box["width"] / 2,
                    box["y"] + box["height"] / 2,
                )

        def scroll_to(sel, offset=90):
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=15000)
            loc.evaluate(
                """(e, offset) => window.scrollTo({
                    top: e.getBoundingClientRect().top + scrollY - offset,
                    behavior: 'instant'
                })""",
                offset,
            )
            page.wait_for_timeout(200)

        def step(key, action, ready=None, min_wait=0.0):
            # Required actions must succeed before narrating their result.
            action()
            if ready is not None:
                ready()
            page.wait_for_timeout(150)
            at = now() + .15
            marks.append((at, key))
            print(f"tour step {key}: ready at {at:.3f}s", flush=True)
            clip, _ = lines[key]
            page.wait_for_timeout(
                int(max(len(clip) / SR + .7, min_wait) * 1000)
            )

        def open_night():
            glide(".cell[data-night='2016-04-19']", True)
            page.wait_for_function(
                """document.querySelector('#night h2')
                   ?.textContent.includes('19 April 2016')""",
                timeout=15000,
            )
            scroll_to("#night", 40)

        def skeptic():
            glide("button.tab.skeptic", True)
            page.locator("#night .cite").first.wait_for(state="visible")
            glide("#night .cite")

        def family():
            glide("button.tab.family", True)
            page.locator("#night .bubble").wait_for(state="visible")
            scroll_to("#night", 40)

        def open_warning():
            scroll_to("#unheard", 20)
            glide("#uh-demo", True)
            page.wait_for_function(
                "document.querySelectorAll('#uh-evidence .event').length > 0",
                timeout=120000,
            )
            scroll_to("#uh-video", 20)

        def replay():
            glide("#uh-replay", True)
            page.locator("#uh-seance").wait_for(state="visible")

        def open_room():
            scroll_to("#room", 20)
            glide("#rm-start", True)
            page.wait_for_function(
                """(() => {
                    const v = document.querySelector('#rm-video');
                    return v && v.srcObject && v.readyState >= 2;
                })()""",
                timeout=15000,
            )
            page.locator("#rm-seance-open").wait_for(
                state="visible", timeout=15000,
            )

        def ask_room():
            glide("#rm-seance-open", True)
            page.locator("#rm-seance").wait_for(
                state="visible", timeout=30000,
            )
            question = page.locator("#rm-suggest button").first
            question.wait_for(state="visible")
            if question.inner_text().strip() != "Is someone here?":
                raise RuntimeError("The recorded question changed.")
            glide("#rm-suggest button", True)
            page.locator("#rm-turns li").first.wait_for(
                state="visible", timeout=45000,
            )
            scroll_to("#rm-seance", 20)

        def apprentice():
            heading = page.get_by_role(
                "heading", name="Training an apprentice", exact=True,
            )
            heading.wait_for(state="visible")
            heading.scroll_into_view_if_needed()

        try:
            page.goto(BASE, wait_until="networkidle")
            page.locator(
                ".cell[data-night='2016-04-19']"
            ).wait_for(state="visible", timeout=15000)

            step("open", lambda: scroll_to("header.hero", 0))
            step("map", lambda: scroll_to("#map-title", 40))
            step("night", open_night)
            step("skeptic", skeptic)
            step("family", family)
            step("tonight", lambda: scroll_to("#tonight", 40))
            step("unheard", open_warning)
            step(
                "evidence",
                lambda: (
                    scroll_to("#uh-timeline", 100),
                    glide("#uh-evidence .event .ts"),
                ),
            )
            step("replay", replay)

            first = page.locator("#uh-turns li").first
            first.wait_for(state="visible", timeout=45000)
            if case["seance"]["turns"][0]["question"] not in first.inner_text():
                raise RuntimeError("Recorded Guardian turn does not match audio.")
            first.scroll_into_view_if_needed()
            at = now() + .15
            turns.append((at, 0))
            # Preserve this reply in full before moving to the next case.
            page.wait_for_timeout(int((len(guardian_audio) / SR + .6) * 1000))

            step("room", open_room)
            step("summon", ask_room)
            step(
                "benchmark",
                lambda: scroll_to("#eval-title", 40),
                ready=lambda: page.locator("#eval table").wait_for(
                    state="visible",
                ),
            )
            step("bakeoff", lambda: scroll_to("#bakeoff-sec", 40))
            step("apprentice", apprentice)
            step("credits", lambda: scroll_to("footer.ofrenda", 40))
            step("end", lambda: scroll_to("header.hero", 0))
            page.wait_for_timeout(1000)
            video = Path(page.video.path())
        finally:
            ctx.close()
            browser.close()

    total = duration(video)
    voice = np.zeros(int((total + 2) * SR), np.float32)
    cues = []

    def place(clip, at):
        i = int(at * SR)
        seg = clip[:max(0, len(voice) - i)]
        voice[i:i + len(seg)] += seg

    for at, key in marks:
        clip, text = lines[key]
        place(clip, at)
        cues += [
            (at + a, at + b, text)
            for a, b, text in split_cue(text, len(clip) / SR)
        ]

    for at, _ in turns:
        place(guardian_audio, at)
        cues += [
            (at + a, at + b, text)
            for a, b, text in split_cue(
                f"“{guardian_text}”", len(guardian_audio) / SR,
            )
        ]

    mix_and_mux("witching_hour_tour", video, voice, sorted(cues))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    which = sys.argv[3] if len(sys.argv) > 3 else "both"
    if which in ("film", "both"):
        make_film()
    if which in ("tour", "both"):
        make_tour()
