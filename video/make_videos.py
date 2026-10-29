"""The two Witching Hour videos.

1. The film: the crew introduce themselves and the three cases, over the app's own screenshots.
2. The tour: a real recording of the running app (Playwright + Chrome), narrated by Luna.

python video/make_videos.py BASE_URL OUT_DIR      (the app must be running at BASE_URL)
Needs: ffmpeg, edge-tts, Pillow, numpy, cairosvg, playwright.
"""
from __future__ import annotations

import json
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
    p = WORK / "voice" / f"{name}.mp3"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        run("edge-tts", "--voice", VOICE[who], "--rate", "-4%", "--text", text, "--write-media", str(p))
    return p


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
    ("title", ("What if someone tried to warn you, and you never heard them?", "Halloween · Día de los Muertos · a paranormal activity detector"),
     [("luna", "What if someone tried to warn you, and you never heard them? Welcome to Witching Hour, a paranormal activity detector for Halloween and Día de los Muertos.")]),
    ("character", ("luna", "A tiny sugar-skull ghost with a marigold crown and a crystal ball.", "“Shhh... the house is breathing.”"),
     [("luna", "I'm Luna, the medium. I read the evidence, I tell the ghost stories, and I'm the one who opens the Ouija board.")]),
    ("character", ("bigotes", "A black cat scientist with round glasses, a lab coat and a flashlight.", "“Hmph. Probably the kettle.”"),
     [("bigotes", "I'm Doctor Bigotes, the skeptic. I have never met a ghost that was not a kettle, a draft or a tired bulb. Under every piece of evidence, I write what most likely happened.")]),
    ("character", ("xochi", "A xoloitzcuintli, the dog that guides souls on Día de los Muertos.", "“I kept watch. Here is what I saw.”"),
     [("xochi", "And I'm Xochi, the night watch. On Día de los Muertos, xolos guide the souls. I carry the messages to the living: a calm note at dawn for the family, and the case dossier.")]),
    ("shot", ("doors.png", "luna", "PARANORMAL.exe", None),
     [("luna", "Our terminal, PARANORMAL dot exe, opens three cases. The House. The Unheard. And The Room. One rule holds it all together: the evidence is real, the spirits are fiction.")]),
    ("shot", ("top.png", "bigotes", "Case 1 · The House", None),
     [("bigotes", "Case one is a real house in Belgium, logged every ten minutes for four months. Our spirit meter is TabPFN, an open tabular model. It learns what every room should feel like at every minute of the night, and flags whatever breaks the pattern.")]),
    ("shot", ("night-medium.png", "luna", "A case file", 0.0),
     [("luna", "Every strange night becomes a case file. I tell the story, Doctor Bigotes explains it, and Xochi writes the note. Every sentence must cite its evidence, and every number must match. Otherwise, it vanishes.")]),
    ("shot", ("benchmark.png", "bigotes", "Testing the meter", None),
     [("bigotes", "Of course I tested the meter. We planted fake ghosts in real nights. At five percent false alarms, TabPFN caught twenty five percent of them. LightGBM caught under ten.")]),
    ("shot", ("warning-9_4.png", "xochi", "Case 2 · The Unheard", None),
     [("xochi", "Case two is The Unheard. A staged recording. Twenty one forty three. She has her coat on, her hand almost on the door. The lamp flickers. Something whispers. Three knocks. A tall shadow passes behind her. And she stays home.")]),
    ("shot", ("seance.png", "bigotes", "The evidence locker", 0.35),
     [("bigotes", "Your browser reads the clip frame by frame, and the video never leaves the page. Five moments stand out. A buzz with the flicker: cheap bulbs. A soft sound: I would not call it a voice. The knocks: ghosts are rarely this loud.")]),
    ("shot", ("seance.png", "luna", "The board", 0.0),
     [("luna", "Then I open the board for what he could not explain. The guardian hears what she remembers, and every answer points at a real moment. Will you come back?")],
     "demo_data/media/the_warning/turn-6.mp3"),
    ("shot", ("doors.png", "xochi", "Case 3 · The Room", None),
     [("xochi", "Case three is The Room. Turn on your own camera and ask the board, live. Nothing is uploaded. And if something really moves right after the glass stops... that was not part of the game.")]),
    ("card", ("Open source, all the way down", ["TabPFN · the spirit meter", "Gemma 4 · local, through Ollama", "Temporal · a durable night watch",
                                                "Sentry · agent tracing", "ElevenLabs · our voices", "Tinker · a fine-tuned apprentice",
                                                "Mastra · the hunt as an agent", "Backboard · the model bake-off",
                                                "Browserbase · a real browser", "SerpApi · tonight's weather"], "bigotes"),
     [("bigotes", "Under the hood: Gemma 4 runs locally through Ollama. Temporal keeps the night watch durable, Sentry traces the agent, and ElevenLabs gives us our voices. Tinker trained an apprentice, Mastra runs the hunt, Backboard compared the models, and Render hosts the demo.")]),
    ("title", ("The evidence is real. The spirits are fiction.", "witching-hour.onrender.com · github.com/jenniferevangelista-de/witching-hour"),
     [("luna", "The evidence is real. The spirits are fiction."), ("xochi", "And the feeling is yours.")]),
]


def make_film():
    get_fonts()
    clips, cues, voice_track, t = [], [], [], 0.0
    for i, scene in enumerate(FILM):
        kind, args, lines = scene[0], scene[1], scene[2]
        extra = ROOT / scene[3] if len(scene) > 3 else None
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
        if extra and extra.exists():
            clip = pcm(extra)
            cues.append((start, start + len(clip) / SR, "“I will never leave you. Please just stay safe inside the walls, my dear.”"))
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
    """Subtitles of at most ~70 characters, timed by their share of the line."""
    parts, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > 70 and cur:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    parts.append(cur)
    total = sum(len(p) for p in parts)
    out, a = [], 0.0
    for p in parts:
        b = a + seconds * len(p) / total
        out.append((a, b, p))
        a = b
    return out


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
    ("open", "This is the live demo of Witching Hour. I'm Luna, and I'll show you around."),
    ("doors", "Meet the crew, and the three doors of PARANORMAL dot exe."),
    ("map", "Case one, The House. The haunting map: every square is a night of a real house. The brighter it glows, the stronger the apparition. A blue dot means a room fell under eighteen degrees."),
    ("night", "I'll open April nineteenth. At five forty the spirit meter jumps: the machines are waking up. Here is my story of that night."),
    ("skeptic", "Doctor Bigotes explains it. Hover a citation, and the evidence it points to lights up on the chart."),
    ("family", "And Xochi writes the morning note for the family. Even the house gets a message on the board, checked against the night's own events."),
    ("tonight", "Tonight's forecast mixes live weather with TabPFN, and Doctor Bigotes checks the official warnings in a real browser."),
    ("unheard", "Now, The Unheard. I open The Warning, and the browser reads the clip frame by frame. The video never leaves this page."),
    ("evidence", "Five moments stand out from the rest of the recording, and Doctor Bigotes has a note for each one. The flicker, the buzz, a soft sound, the knocks, and the shadow."),
    ("replay", "She told me what she remembers. Here is the recorded séance with the guardian. Listen."),
    ("room", "And The Room. It uses your own camera and microphone, live. In this recording, the camera is Chrome's test pattern, so the board sees motion everywhere."),
    ("summon", "I summon the spirit of the room and ask it something."),
    ("archive", "Down in the archive: the planted ghosts benchmark, the model bake-off, and the apprentice we fine-tuned with Tinker."),
    ("end", "The evidence is real. The spirits are fiction. Happy Halloween, and feliz Día de los Muertos."),
]


def make_tour():
    from playwright.sync_api import sync_playwright

    lines = {k: (pcm(say("luna", text, f"tour_{k}")), text) for k, text in TOUR}
    case = json.loads((ROOT / "demo_data" / "cases.json").read_text(encoding="utf-8"))["cases"][0]
    guardian = [ROOT / a.lstrip("/").replace("media/", "demo_data/media/", 1) if a else None for a in case["seance"]["audio"]]
    marks, turns = [], []
    rec = WORK / "rec"
    with sync_playwright() as p:
        args = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", "--autoplay-policy=no-user-gesture-required"]
        try:
            browser = p.chromium.launch(channel="chrome", args=args)
        except Exception:  # noqa: BLE001
            browser = p.chromium.launch(args=args)
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(rec),
                                  record_video_size={"width": W, "height": H}, color_scheme="dark")
        ctx.grant_permissions(["camera", "microphone"], origin=BASE)
        ctx.add_init_script(CURSOR_JS)
        page = ctx.new_page()
        t0 = time.monotonic()
        now = lambda: time.monotonic() - t0  # noqa: E731

        def glide(sel, click=False):
            loc = page.locator(sel).first
            loc.scroll_into_view_if_needed()
            box = loc.bounding_box()
            if box:
                page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
                if click:
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)

        def scroll_to(sel, offset=90):
            page.evaluate(f"(() => {{ const e = document.querySelector('{sel}'); if (e) window.scrollTo({{top: e.getBoundingClientRect().top + scrollY - {offset}, behavior: 'smooth'}}); }})()")

        def step(key, action, min_wait=0.0):
            start = now()
            try:
                action()
            except Exception as e:  # noqa: BLE001
                print("step", key, "failed:", e, flush=True)
            clip, text = lines[key]
            marks.append((start + .3, key))
            rest = max(len(clip) / SR + .7, min_wait) - (now() - start)
            if rest > 0:
                page.wait_for_timeout(int(rest * 1000))

        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(1500)
        step("open", lambda: page.mouse.move(W / 2, 400, steps=10))
        step("doors", lambda: (scroll_to("#crew", 120), page.wait_for_timeout(900), glide("nav.doors .door")))
        step("map", lambda: (glide("a.door[href='#case-house']", True), page.wait_for_timeout(900), scroll_to("#map-title", 60)))
        step("night", lambda: (glide(".cell[data-night='2016-04-19']", True), page.wait_for_timeout(1500), scroll_to("#night", 40)))
        step("skeptic", lambda: (glide("button.tab.skeptic", True), page.wait_for_timeout(1200), glide("#night .cite")))
        step("family", lambda: (glide("button.tab.family", True), page.wait_for_timeout(2500), scroll_to("#night .ouija", 120)))
        step("tonight", lambda: scroll_to("#tonight", 40))
        step("unheard", lambda: (scroll_to("#unheard", 20), page.wait_for_timeout(1200), glide("#uh-demo", True)))
        page.wait_for_function("document.querySelectorAll('#uh-evidence .event').length > 0", timeout=120000)
        step("evidence", lambda: (scroll_to("#uh-timeline", 140), page.wait_for_timeout(1500), glide("#uh-evidence .event .ts")))

        def replay():
            scroll_to("#uh-open", 380)
            page.wait_for_timeout(800)
            glide("#uh-replay", True)
        step("replay", replay)
        n = len(case["seance"]["turns"])
        seen, deadline = 0, now() + 200
        while seen < n and now() < deadline:
            c = page.evaluate("document.querySelectorAll('#uh-turns li').length")
            if c > seen:
                for k in range(seen, c):
                    turns.append((now(), k))
                seen = c
                page.evaluate("(() => { const l = document.querySelector('#uh-turns li:last-child'); if (l) l.scrollIntoView({block: 'center', behavior: 'smooth'}); })()")
            page.wait_for_timeout(200)
        page.wait_for_timeout(2500)
        step("room", lambda: (scroll_to("#room", 20), page.wait_for_timeout(1200), glide("#rm-start", True)), min_wait=9)
        step("summon", lambda: (glide("#rm-seance-open", True), page.wait_for_timeout(2500), glide("#rm-suggest button", True)), min_wait=12)
        step("archive", lambda: scroll_to("#eval-title", 40), min_wait=8)
        step("end", lambda: page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})"), min_wait=6)
        page.wait_for_timeout(1500)
        video = Path(page.video.path())
        ctx.close()
        browser.close()

    total = duration(video) if video.exists() else now()
    voice = np.zeros(int((total + 2) * SR), np.float32)
    cues = []

    def place(clip, at):
        i = int(at * SR)
        seg = clip[: max(0, len(voice) - i)]
        voice[i:i + len(seg)] += seg

    for at, key in marks:
        clip, text = lines[key]
        place(clip, at)
        cues += [(at + a, at + b, s) for a, b, s in split_cue(text, len(clip) / SR)]
    for at, k in turns:  # the guardian speaks when each answer lands on the list
        if k < len(guardian) and guardian[k] and guardian[k].exists():
            clip = pcm(guardian[k])
            place(clip, at)
            cues += [(at, at + len(clip) / SR, "“" + case["seance"]["turns"][k]["response"]["spoken"] + "”")]
    mix_and_mux("witching_hour_tour", video, voice, sorted(cues))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    which = sys.argv[3] if len(sys.argv) > 3 else "both"
    if which in ("film", "both"):
        make_film()
    if which in ("tour", "both"):
        make_tour()
