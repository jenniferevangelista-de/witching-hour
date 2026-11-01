"""Witching Hour film in the paper style of the Night Guard film (hand-drawn ink on paper, the crew narrating).

  python video/paper/wh_paper.py voices      -> voices/*.mp3 and timeline.json
  python video/paper/wh_paper.py frames 5 30 -> review/*.jpg
  python video/paper/wh_paper.py render      -> witching_hour_paper_film.mp4
Uses palito.py (the ink primitives of the Night Guard film) and Windows fonts.
"""
import asyncio
import json
import math
import random
import subprocess
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from palito import FPS, H, INK, RED, W, eio, eout, font, jit, paper, poof, seg, text, wcircle, wline, wrect  # noqa: E402

SR = 24000
NIGHT = (38, 50, 108); GOLD = (232, 150, 20); GREEN = (40, 150, 110); SOFT = (120, 112, 125); ROSA = (214, 60, 130)
VIOLET = (120, 80, 200); WHITE = (255, 252, 242)
VOICE = {"luna": "en-US-AvaMultilingualNeural", "bigotes": "en-GB-RyanNeural", "xochi": "en-US-EmmaMultilingualNeural"}
SCENES = [
    ("intro", "luna", "What if someone tried to warn you, and you never heard them? I'm Luna, the medium. Welcome to Witching Hour.", 0.8),
    ("crew", "luna", "This is my crew. Doctor Bigotes, the skeptic. Xochi, the night watch. We read the same evidence, and we never agree on what it means.", 0.8),
    ("house", "bigotes", "Case one. A real house in Belgium, logged every ten minutes for four months. TabPFN learns what each room should read at night. "
                         "At five forty, the appliances used three hundred eighty watt hours. It expected seventy five at most.", 0.8),
    ("cite", "xochi", "Every sentence the crew writes must cite a measured moment, and every number must match. "
                      "Ninety six stories, three hundred sixty two cited sentences. A sentence that cites nothing vanishes.", 0.8),
    ("warning", "luna", "Case two. Kenji, a client in Japan, sent us his hallway camera. His mother almost went out. "
                        "The light flickers. Three knocks. A shadow. And she stays home.", 1.0),
    ("notes", "bigotes", "Hmph. A tired bulb. The pipes knocking. A neighbour. I have a boring explanation for almost everything.", 0.8),
    ("seance", "luna", "For the rest, I open the board. The spirit speaks only through the glass, and every answer must point at a real moment. Will you come back?", 7.5),
    ("room", "xochi", "Now it's your turn. Use your camera, play without one, or bring your own recording.", 0.8),
    ("tested", "bigotes", "Of course I tested it. With planted ghosts, TabPFN caught twenty five percent, and LightGBM under ten. "
                          "Tinker taught a small model the rule: ninety five, then ninety nine percent. Four open models compared through Backboard. Eighty one tests.", 0.8),
    ("tech", "luna", "Open models, all the way down. TabPFN, Gemma four on a laptop, ElevenLabs voices, Backboard, Tinker, Render, "
                     "Temporal, Sentry, Mastra, Browserbase and SerpApi.", 1.0),
    ("end", "xochi", "The evidence is real. The spirits are fiction. And the feeling is yours.", 2.5),
]
GUARDIAN = ROOT / "demo_data" / "media" / "the_warning" / "turn-6.mp3"     # the recorded Guardian: "I will never leave you"
MUSIC = ROOT / "video" / "music" / "Funkorama.mp3"


def decode(p):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def make_voices():
    import edge_tts
    vd = HERE / "voices"; vd.mkdir(exist_ok=True)
    async def go():
        for sid, who, line, _ in SCENES:
            await edge_tts.Communicate(line, VOICE[who], rate="-2%").save(str(vd / f"{sid}.mp3"))
    asyncio.run(go())
    t, out = 0.6, []
    for sid, who, line, extra in SCENES:
        dur = len(decode(vd / f"{sid}.mp3")) / SR
        out.append({"id": sid, "who": who, "line": line, "start": round(t, 2), "voice_dur": round(dur, 2), "end": round(t + dur + extra, 2)})
        t += dur + extra
    (HERE / "timeline.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("timeline", round(t, 1), "s")


@lru_cache(maxsize=1)
def TL():
    return {s["id"]: s for s in json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))}


def S(sid): return TL()[sid]


@lru_cache(maxsize=16)
def env(sid):
    a = decode(HERE / "voices" / f"{sid}.mp3"); hop = SR // 12
    r = np.array([np.sqrt(np.mean(a[j:j + hop] ** 2)) for j in range(0, len(a), hop)])
    return (r / (r.max() or 1)).tolist()


def talking(t):
    for s in TL().values():
        if s["start"] <= t < s["start"] + s["voice_dur"]:
            e = env(s["id"]); k = int((t - s["start"]) * 12)
            return s["who"], (e[k] if 0 <= k < len(e) else 0.0)
    return None, 0.0


@lru_cache(maxsize=32)
def char(who, size):
    im = Image.open(HERE / f"{who}.png").convert("RGBA")
    return im.resize((size, int(size * im.height / im.width)), Image.LANCZOS)


def put(img, who, cx, base, size, t, lvl=0.0, k=1.0):
    if k <= 0: return
    s = max(8, int(size * eout(k) * (1.3 if who == "luna" else 1.0)))   # her drawing sits smaller in its frame
    im = char(who, s); bob = math.sin(t * 3 + hash(who) % 7) * 6 + (lvl * 14 if lvl > 0.12 else 0)
    img.alpha_composite(im, (int(cx - im.width / 2), int(base - im.height - bob)))


@lru_cache(maxsize=1)
def subs():
    out = []
    for s in TL().values():
        parts, cur = [], ""
        for w in s["line"].split():
            if len(cur) + len(w) > 62 and cur: parts.append(cur); cur = w
            else: cur = (cur + " " + w).strip()
        parts.append(cur)
        total = sum(len(p) for p in parts); t = s["start"]
        for p in parts:
            d = s["voice_dur"] * len(p) / total; out.append((t, t + d + 0.15, p)); t += d
    return out


def subtitle(d, t):
    for a, b, s in subs():
        if a <= t < b:
            f = font("segoeprb.ttf", 40); w = d.textlength(s, font=f)
            d.rounded_rectangle((W / 2 - w / 2 - 24, 1002, W / 2 + w / 2 + 24, 1062), 18, fill=(255, 251, 240))
            text(d, s, W / 2, 1031, 40, INK); return


def stamp(img, s, cx, cy, ang, col=RED, size=80):
    f = font("impact.ttf", size); d0 = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w = int(d0.textlength(s, font=f)) + 60; h = size + 50
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0)); dd = ImageDraw.Draw(lay)
    dd.rectangle((6, 6, w - 6, h - 6), outline=col + (255,), width=8); dd.text((w / 2, h / 2), s, font=f, fill=col + (255,), anchor="mm")
    lay = lay.rotate(ang, expand=True, resample=Image.BICUBIC); img.alpha_composite(lay, (int(cx - lay.width / 2), int(cy - lay.height / 2)))


# ------------------------------------------------------------------ scenes
def sc_intro(img, d, t):
    a = S("intro")["start"]; who, lvl = talking(t)
    put(img, "luna", 560, 960, 560, t, lvl if who == "luna" else 0, seg(t, 0.2, 0.9))
    z = eout(seg(t, a + 0.2, a + 0.9))
    text(d, "WITCHING HOUR", 1270, 300, int(40 + 90 * z), NIGHT, "mm", "impact.ttf")
    if t > a + 1.2: text(d, "Halloween · Día de los Muertos", 1270, 410, 46, INK)
    if t > a + 2.4: text(d, "a ghost hunt built on open models", 1270, 480, 40, SOFT)
    if t > a + 4.5: stamp(img, "CITE OR VANISH", 1270, 640, -5, RED, 70)


def sc_crew(img, d, t):
    a = S("crew")["start"]; who, lvl = talking(t)
    for i, (k, name, role, col, t0) in enumerate([("luna", "Luna", "the medium", GOLD, 0.2), ("bigotes", "Dr. Bigotes", "the skeptic", GREEN, 2.0),
                                                   ("xochi", "Xochi", "the night watch", ROSA, 4.0)]):
        cx = 380 + i * 580
        put(img, k, cx, 720, 380, t, 0, seg(t, a + t0, a + t0 + 0.5))
        if t > a + t0 + 0.4:
            text(d, name, cx, 790, 60, col, "mm", "impact.ttf"); text(d, role, cx, 860, 40, INK)
    if t > a + 7.0: text(d, "same evidence · three readings", W / 2, 150, 50, NIGHT)


def sc_house(img, d, t):
    a = S("house")["start"]
    wrect(d, 120, 120, 900, 560, t, 300, 7, fill=WHITE)
    text(d, "123 nights · midnight to 6 AM", 510, 165, 36, INK)
    r = random.Random(4); k = seg(t, a + 0.4, a + 4.0)
    for i in range(123):
        if i / 123 > k: break
        x, y = 160 + (i % 18) * 40, 210 + (i // 18) * 46
        v = r.random(); col = (255, 120, 60) if v > 0.93 else (250, 200, 90) if v > 0.8 else (200, 190, 225) if v > 0.4 else (225, 220, 235)
        d.rounded_rectangle((x, y, x + 32, y + 36), 6, fill=col)
    text(d, "bright = strayed from what TabPFN expected", 510, 590, 32, SOFT)
    if t > a + 5.5:                                          # the band and the spike at 05:40
        x0, x1, yb = 1000, 1780, 520
        wrect(d, x0, 140, x1, 560, t, 320, 7, fill=WHITE)
        k2 = seg(t, a + 5.5, a + 9.0)
        pts = [(x0 + 20 + j * 19, yb - 40 - 18 * math.sin(j / 5)) for j in range(40)]
        d.polygon([(x, y - 45) for x, y in pts] + [(x, y + 15) for x, y in reversed(pts)], fill=(220, 230, 250))
        n = max(2, int(40 * k2)); line = [(x, y - 15 + (-300 if 30 <= j <= 32 else 0)) for j, (x, y) in enumerate(pts[:n])]
        wline(d, line, t, 330, 6, RED)
        if k2 > 0.8:
            text(d, "05:40  380 Wh", 1590, 190, 44, RED, "mm", "impact.ttf"); text(d, "expected 36 to 75", 1590, 245, 34, INK)
    if t > a + 10.0: stamp(img, "E1", 1390, 780, 4, RED, 90)


def sc_cite(img, d, t):
    a = S("cite")["start"]
    lines = [("At 05:40 the machines woke up.", "E1", True), ("The air dried out by 05:00.", "E2", True),
             ("A ghost slammed the door.", "", False)]
    for i, (s, ev, ok) in enumerate(lines):
        t0 = a + 0.4 + i * 1.6
        if t < t0: continue
        y = 220 + i * 190; gone = (not ok) and t > a + 9.0
        if gone:
            poof(d, t, 700, y + 40, seg(t, a + 9.0, a + 9.8)); continue
        wrect(d, 160, y, 1240, y + 110, t, 400 + i, 6, fill=WHITE)
        text(d, s, 200, y + 55, 42, INK, "lm")
        if ok:
            wline(d, [(1240, y + 55), (1420, y + 55)], t, 410 + i, 5, GREEN)
            wrect(d, 1420, y + 15, 1560, y + 95, t, 420 + i, 6, fill=(220, 245, 230)); text(d, ev, 1490, y + 55, 46, GREEN, "mm", "impact.ttf")
        elif t > a + 7.0:
            text(d, "cites nothing", 1430, y + 55, 40, RED, "lm")
    if t > a + 5.0:
        text(d, "96 stories · 362 cited sentences · all passed", W / 2, 860, 46, NIGHT)


def hallway(d, t, flick):
    wrect(d, 180, 140, 1100, 840, t, 500, 8, fill=(90, 92, 110) if flick else (60, 62, 80))
    wrect(d, 860, 300, 1040, 840, t, 501, 7, fill=(120, 80, 50)); wcircle(d, 890, 580, 12, t, 502, 4, fill=GOLD)
    wline(d, [(330, 840), (330, 520)], t, 503, 6); d.polygon([(280, 520), (380, 520), (360, 440), (300, 440)], fill=(230, 60, 60) if flick else (150, 40, 40))
    text(d, "● REC  HALLWAY CAM 02  21:43", 200, 175, 30, WHITE, "lm")


def sc_warning(img, d, t):
    a = S("warning")["start"]; v = S("warning")["voice_dur"]; line = S("warning")["line"]
    at = lambda kw: a + v * line.find(kw) / len(line)  # noqa: E731
    flick = at("The light") < t < at("The light") + 1.2 and int(t * 10) % 2 == 0
    hallway(d, t, flick)
    from palito import stick
    stay = t > at("And she stays")
    stick(d, t, (760 if not stay else 560, 760), 1.0, armR=(-30 if not stay else 120, 40), mood="normal", look=0.6, seed=7)
    if t > at("A shadow"): d.ellipse((420, 330, 520, 760), fill=(30, 30, 45))
    for i in range(3):
        k0 = at("Three knocks") + i * 0.45
        if t > k0: text(d, "KNOCK", 1250 + i * 40, 300 + i * 120, 60, RED, "mm", "impact.ttf")
    evs = [("ev-001", "light"), ("ev-002", "sound"), ("ev-003", "sound"), ("ev-004", "knocks"), ("ev-005", "motion")]
    for i, (e, k) in enumerate(evs):
        if t > a + 2 + i * 1.3:
            wrect(d, 1250, 560 + i * 80, 1760, 620 + i * 80, t, 520 + i, 5, fill=WHITE)
            text(d, f"{e}  {k}", 1280, 590 + i * 80, 34, INK, "lm")


def sc_notes(img, d, t):
    a = S("notes")["start"]; who, lvl = talking(t)
    put(img, "bigotes", 420, 900, 520, t, lvl, 1.0)
    notes = [(0.8, "light dips? a tired bulb"), (2.4, "knocks? the pipes"), (3.8, "a shadow? a neighbour, a coat"), (5.5, "almost everything: boring")]
    for i, (t0, s) in enumerate(notes):
        if t > a + t0:
            y = 200 + i * 170; wrect(d, 860, y, 1760, y + 120, t, 600 + i, 6, fill=WHITE)
            d.line((900, y + 60, 930, y + 90, 980, y + 30), fill=GREEN, width=9); text(d, s, 1010, y + 60, 42, INK, "lm")


BOARD = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def letter_pos(ch):
    if ch in BOARD[:13]:
        i = BOARD.index(ch); ang = math.pi * (1.05 - i / 12 * 1.1); return 960 + 520 * math.cos(ang), 600 - 260 * math.sin(ang)
    i = BOARD.index(ch) - 13; ang = math.pi * (1.05 - i / 12 * 1.1); return 960 + 400 * math.cos(ang), 640 - 190 * math.sin(ang)


def sc_seance(img, d, t):
    a = S("seance")["start"]; v = S("seance")["voice_dur"]
    wrect(d, 320, 200, 1600, 920, t, 700, 9, fill=(236, 205, 150))
    for ch in BOARD:
        x, y = letter_pos(ch); text(d, ch, x, y, 52, INK, "mm", "georgiab.ttf")
    text(d, "YES", 450, 260, 54, INK, "mm", "georgiab.ttf"); text(d, "NO", 1470, 260, 54, INK, "mm", "georgiab.ttf")
    text(d, "GOODBYE", 960, 860, 56, INK, "mm", "georgiab.ttf")
    msg = "IAMHERE"; s0 = a + v + 0.2
    k = (t - s0) / 0.75
    if t < s0: gx, gy = 960, 720
    else:
        i = min(int(k), len(msg) - 1); gx, gy = letter_pos(msg[i])
    spelled = "" if t < s0 else "I AM HERE"[: [1, 3, 4, 6, 7, 8, 9][min(int(k), 6)]]
    broken = t > s0 + 0.75 * 7 + 2.2
    if not broken:
        wcircle(d, gx, gy + 20, 60, t, 710, 7, fill=(250, 248, 240)); wcircle(d, gx, gy + 10, 22, t, 711, 5, fill=(200, 240, 225))
    else:
        poof(d, t, gx, gy, seg(t, s0 + 0.75 * 7 + 2.2, s0 + 0.75 * 7 + 3.2))
        for j in range(10):
            ang = j * 0.63; r = 80 + 200 * seg(t, s0 + 7.45, s0 + 8.4)
            d.polygon([(gx + r * math.cos(ang), gy + r * math.sin(ang)), (gx + (r + 26) * math.cos(ang + .1), gy + (r + 26) * math.sin(ang + .1)),
                       (gx + (r + 10) * math.cos(ang - .2), gy + (r + 10) * math.sin(ang - .2))], fill=(180, 210, 230))
    if spelled: text(d, spelled, 960, 990 - 40, 70, GREEN, "mm", "impact.ttf")
    if t > s0 + 6.0: text(d, '"I will never leave you."', 960, 140, 50, VIOLET)


def sc_room(img, d, t):
    a = S("room")["start"]
    wrect(d, 260, 180, 1100, 700, t, 800, 8, fill=(30, 26, 50)); wcircle(d, 680, 440, 80, t, 801, 6, col=(141, 255, 207))
    text(d, "your camera", 680, 600, 40, (220, 220, 240))
    for i, (s, col) in enumerate([("camera + mic", VIOLET), ("play without a camera", GOLD), ("bring your own recording", ROSA)]):
        if t > a + 1.0 + i * 1.2:
            y = 230 + i * 160; wrect(d, 1180, y, 1760, y + 110, t, 810 + i, 6, fill=WHITE)
            d.rectangle((1188, y + 8, 1206, y + 102), fill=col); text(d, s, 1480, y + 55, 40, INK)
    if t > a + 4.5: stamp(img, "YOUR TURN", 960, 850, -4, RED, 76)


def bar(d, t, x, y, w, k, col, label, val, seed):
    wrect(d, x, y, x + w, y + 60, t, seed, 5, fill=WHITE); d.rectangle((x + 6, y + 6, x + 6 + (w - 12) * k, y + 54), fill=col)
    text(d, label, x - 20, y + 30, 38, INK, "rm"); text(d, val, x + w + 20, y + 30, 44, col, "lm", "impact.ttf")


def sc_tested(img, d, t):
    a = S("tested")["start"]; v = S("tested")["voice_dur"]; line = S("tested")["line"]
    at = lambda kw: a + v * line.find(kw) / len(line)  # noqa: E731
    text(d, "planted ghosts caught (5% false alarms)", 960, 120, 44, NIGHT)
    bar(d, t, 600, 180, 800, 0.25 * eio(seg(t, a + 1, a + 3)) / 0.3, RED, "TabPFN", "25%", 900)
    bar(d, t, 600, 270, 800, 0.096 * eio(seg(t, a + 1.5, a + 3.5)) / 0.3, SOFT, "LightGBM", "9.6%", 901)
    if t > at("Tinker"):
        text(d, "Tinker LoRA, Qwen3-8B", 960, 430, 44, NIGHT); k = eio(seg(t, at("Tinker"), at("Tinker") + 2))
        text(d, f"{95.5 + 3.7 * k:.1f}%", 960, 520, 90, GREEN, "mm", "impact.ttf"); text(d, "sentences passing the check", 960, 600, 36, INK)
    if t > at("Four open"):
        for i, m in enumerate(["Gemma 3 27B", "Llama 3.3 70B", "Qwen 2.5 72B", "Mistral Small"]):
            wrect(d, 200 + i * 400, 690, 560 + i * 400, 770, t, 920 + i, 5, fill=WHITE); text(d, m, 380 + i * 400, 730, 34, INK)
        text(d, "one Backboard key", 960, 810, 36, SOFT)
    if t > at("Eighty"): stamp(img, "81 TESTS", 1600, 520, 6, GREEN, 70)


def sc_tech(img, d, t):
    a = S("tech")["start"]; v = S("tech")["voice_dur"]; line = S("tech")["line"]
    cards = [("TabPFN", "spirit meter", RED), ("Gemma", "local storyteller", NIGHT), ("ElevenLabs", "114 voice files", GOLD),
             ("Backboard", "4 models, 1 key", VIOLET), ("Tinker", "LoRA apprentice", ROSA), ("Render", "the live demo", (40, 110, 160)),
             ("Temporal", "survives crashes", GREEN), ("Sentry", "agent traces", (120, 70, 160)), ("Mastra", "agent + memory", (60, 60, 60)),
             ("Browserbase", "a real browser", (30, 30, 30)), ("SerpApi", "live weather", (30, 130, 120)), ("Actions", "runs it all", INK)]
    for i, (kw, sub, col) in enumerate(cards):
        t0 = a + v * max(0, line.find(kw if kw != "Actions" else "SerpApi")) / len(line) + (0.6 if kw == "Actions" else 0)
        k = seg(t, t0, t0 + 0.35)
        if k <= 0: continue
        x = 70 + (i % 4) * 455; y = 120 + (i // 4) * 280; s = eout(k)
        cx, cy = x + 210, y + 120; w, h = 420 * s, 240 * s
        wrect(d, cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, t, 950 + i, 6, fill=WHITE)
        if k > 0.7:
            d.rectangle((cx - w / 2 + 8, cy - h / 2 + 8, cx + w / 2 - 8, cy - h / 2 + 22), fill=col)
            text(d, kw, cx, cy - 20, 54, col, "mm", "impact.ttf"); text(d, sub, cx, cy + 60, 32, INK)
    if t > a + v: stamp(img, "OPEN MODELS", W / 2, 960, -3, RED, 60)


def sc_end(img, d, t):
    a = S("end")["start"]; who, lvl = talking(t)
    for i, k in enumerate(["luna", "bigotes", "xochi"]):
        put(img, k, 560 + i * 400, 560, 320, t, lvl if who == k else 0, seg(t, a + i * 0.3, a + i * 0.3 + 0.5))
    if t > a + 1.0: text(d, "The evidence is real. The spirits are fiction.", W / 2, 650, 60, NIGHT, "mm", "impact.ttf")
    if t > a + 2.5: text(d, "witching-hour.onrender.com", W / 2, 760, 52, RED)
    if t > a + 3.0: text(d, "github.com/jenniferevangelista-de/witching-hour", W / 2, 840, 36, SOFT)
    text(d, 'Music: "Funkorama" Kevin MacLeod (incompetech.com), CC BY 4.0 · opening score: original', W / 2, 1050, 22, SOFT)


ORDER = [("intro", sc_intro), ("crew", sc_crew), ("house", sc_house), ("cite", sc_cite), ("warning", sc_warning), ("notes", sc_notes),
         ("seance", sc_seance), ("room", sc_room), ("tested", sc_tested), ("tech", sc_tech), ("end", sc_end)]
CORNER = {"house": "bigotes", "cite": "xochi", "warning": "luna", "seance": "luna", "room": "xochi", "tested": "bigotes", "tech": "luna"}


def DUR(): return list(TL().values())[-1]["end"] + 0.6


def render(t):
    img = paper().copy().convert("RGBA"); d = ImageDraw.Draw(img)
    sid, fn = ORDER[0]
    for s, f in ORDER:
        if t >= (S(s)["start"] - 0.3 if s != "intro" else 0): sid, fn = s, f
    fn(img, d, t)
    d = ImageDraw.Draw(img)
    if sid in CORNER:                                        # the narrator talks from the corner
        who, lvl = talking(t)
        put(img, who or CORNER[sid], 1800, 1000, 190, t, lvl, 1.0)
    if sid != "end": subtitle(d, t)
    out = img.convert("RGB")
    if t < 1.0: out = Image.blend(Image.new("RGB", out.size, (0, 0, 0)), out, t)
    return out


# ------------------------------------------------------------------ sound
def tt(dur): return np.arange(int(dur * SR)) / SR
def lpf(x, k): return np.convolve(x, np.ones(k) / k, mode="same")


RNG = np.random.default_rng(7)
def pop(): t = tt(0.18); return np.sin(2 * np.pi * (700 + 900 * t) * t) * np.exp(-t * 28) * 0.5
def thud(): t = tt(0.35); return np.sin(2 * np.pi * (90 + 120 * np.exp(-t * 25)) * t) * np.exp(-t * 12) + lpf(RNG.normal(0, 1, len(t)), 3) * np.exp(-t * 40) * 0.5
def chime(f0=1320): t = tt(0.6); return sum(np.sin(2 * np.pi * f0 * m * t) / m for m in (1, 2, 3)) * np.exp(-t * 5) * 0.25
def swish(): t = tt(0.3); return lpf(RNG.normal(0, 1, len(t)), 2) * np.sin(np.pi * t / 0.3) ** 2 * 0.35
def shatter():
    t = tt(0.9); n = RNG.normal(0, 1, len(t)) * (1 - t / 0.9) ** 4
    return np.diff(np.concatenate([[0], n])) * 0.8 + sum(np.sin(2 * np.pi * f * t) * np.exp(-t * 9) * 0.08 for f in (2900, 3700, 4600, 5300))


def drama(dur):
    t = tt(dur); x = np.zeros_like(t)
    for f, a in ((110, .5), (130.81, .35), (164.81, .3), (220, .2)):
        x += a * np.sin(2 * np.pi * f * t + np.sin(2 * np.pi * .07 * t))
    x *= .55 + .45 * np.sin(2 * np.pi * .05 * t) ** 2
    return x / np.abs(x).max()


def make_audio():
    n = int(DUR() * SR); voice = np.zeros(n); fx = np.zeros(n)
    def add(buf, at, clip, g=1.0):
        i = int(at * SR); seg_ = clip[: max(0, n - i)] * g; buf[i:i + len(seg_)] += seg_
    for s in TL().values():
        add(voice, s["start"], decode(HERE / "voices" / f"{s['id']}.mp3"))
    add(fx, S("intro")["start"] + 0.3, chime(1320), .8); add(fx, S("intro")["start"] + 0.45, chime(1760), .8)
    c = S("crew")["start"]
    for t0 in (0.2, 2.0, 4.0): add(fx, c + t0, pop())
    w = S("warning"); line = w["line"]; kt = w["start"] + w["voice_dur"] * line.find("Three knocks") / len(line)
    for i in range(3): add(fx, kt + i * 0.45, thud(), 0.9)
    se = S("seance"); s0 = se["start"] + se["voice_dur"] + 0.2
    for i in range(7): add(fx, s0 + i * 0.75, pop(), 0.5)
    if GUARDIAN.exists(): add(voice, s0 + 6.0, decode(GUARDIAN), 0.9)
    add(fx, s0 + 0.75 * 7 + 2.2, shatter(), 1.0)
    for i in range(12): add(fx, S("tech")["start"] + 0.5 + i * 0.6, chime(880 + 60 * (i % 7)), 0.35)
    add(fx, S("end")["start"], chime(880), 1.0); add(fx, S("end")["start"] + 0.15, chime(1320), 1.0)
    switch = S("room")["start"]
    t = np.arange(n) / SR
    dr = np.zeros(n); dd = drama(switch + 3)[:n]; dr[: len(dd)] = dd
    fk = decode(MUSIC); fk = np.tile(fk, n // len(fk) + 1)[:n]
    x = np.clip((t - switch) / 2.0, 0, 1)
    music = dr * (1 - x) * 0.30 + fk * x * 0.28
    a_ = np.abs(voice); k = int(SR * .25); cs = np.concatenate([[0.0], np.cumsum(a_)])
    envv = (cs[np.minimum(np.arange(n) + k, n)] - cs[np.maximum(np.arange(n) - k, 0)]) / (2 * k) * 6
    mix = voice * 0.95 + fx * 0.8 + music * (1 - 0.5 * np.clip(envv, 0, 1))
    mix = np.clip(mix / max(1.0, np.abs(mix).max()), -1, 1)
    import wave
    with wave.open(str(HERE / "mix.wav"), "wb") as wv:
        wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(SR); wv.writeframes((mix * 32767).astype(np.int16).tobytes())


def job(i): return render(i / FPS).tobytes()


def make_film():
    make_audio()
    n = int(DUR() * FPS)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-i", str(HERE / "mix.wav"), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                           "-pix_fmt", "yuv420p", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k", "-shortest",
                           str(HERE / "witching_hour_paper_film.mp4")], stdin=subprocess.PIPE)
    with Pool(2) as p:
        for b in p.imap(job, range(n), chunksize=8): ff.stdin.write(b)
    ff.stdin.close(); ff.wait()
    print("done", round(DUR(), 1), "s")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "frames"
    if cmd == "voices": make_voices()
    elif cmd == "render": make_film()
    else:
        rv = HERE / "review"; rv.mkdir(exist_ok=True)
        for x in [float(v) for v in sys.argv[2:]] or [3.0]:
            render(x).save(rv / f"f_{x:05.1f}.jpg", quality=80)
        print("ok", round(DUR(), 1))
