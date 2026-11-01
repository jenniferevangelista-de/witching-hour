"""Stick-figure story: 'The Expired Code' — hand-drawn boil on paper (on twos), stickman rig, Gemmy (gemmy_host),
pink-haired host on TV (SadTalker clip). 1920x1080, 24 fps, drawings on twos."""
import math, random, sys, json, glob
from pathlib import Path
from functools import lru_cache
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "like_roblox"))
try:
    from gemmy_host import gemmy_frame  # only the CodeGames shorts need it
except ImportError:
    gemmy_frame = None

HERE = Path(__file__).parent
W, H, FPS = 1920, 1080, 24
INK = (34, 30, 38); RED = (214, 52, 52); CYAN = (60, 200, 235); PAPER = (247, 242, 230)
F = "C:/Windows/Fonts/"


@lru_cache(maxsize=16)
def font(name, size): return ImageFont.truetype(F + name, size)
def clamp(v, a=0.0, b=1.0): return max(a, min(b, v))
def seg(t, a, b): return clamp((t - a) / (b - a))
def eout(k): k = clamp(k); return 1 - (1 - k) ** 3
def eio(k): k = clamp(k); return k * k * (3 - 2 * k)
def dr(t): return int(t * 12)  # drawing index (on twos)


# ------------------------------------------------------------------ voices / mouth envelopes
LINES = {1: 0.5, 2: 7.2, 3: 12.0, 4: 17.6, 5: 21.8}   # start time of each line


@lru_cache(maxsize=8)
def env(i):
    import soundfile as sf
    a, sr = sf.read(HERE / "voz" / f"l{i}.mp3", dtype="float32"); a = a.mean(1) if a.ndim > 1 else a; hop = sr // 12
    r = np.array([np.sqrt(np.mean(a[j:j + hop] ** 2)) for j in range(0, len(a), hop)])
    return (r / (r.max() or 1)).tolist()


def mouth(i, t):
    e = env(i); k = int((t - LINES[i]) * 12)
    if k < 0 or k >= len(e): return 0.0
    m = e[k]; return 0.0 if m < 0.12 else min(1.0, m * 1.25)


# ------------------------------------------------------------------ hand-drawn primitives
def jit(p, t, seed, a=1.6):
    r = random.Random(hash((dr(t), seed, round(p[0]), round(p[1]))) & 0xFFFFFFFF)
    return (p[0] + r.uniform(-a, a), p[1] + r.uniform(-a, a))


def wline(d, pts, t, seed=0, w=7, col=INK, a=1.6):
    """Wobbly ink line through pts, re-jittered every drawing."""
    out = []
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]; n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 28))
        for j in range(n):
            k = j / n; out.append(jit((x0 + (x1 - x0) * k, y0 + (y1 - y0) * k), t, seed + i * 31 + j, a))
    out.append(jit(pts[-1], t, seed + 999, a))
    d.line(out, fill=col, width=w, joint="curve")
    for p in (out[0], out[-1]): d.ellipse((p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2), fill=col)


def wrect(d, x0, y0, x1, y1, t, seed, w=6, col=INK, fill=None):
    if fill: d.rectangle((x0, y0, x1, y1), fill=fill)
    wline(d, [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)], t, seed, w, col)


def wcircle(d, cx, cy, r, t, seed, w=7, col=INK, fill=None):
    pts = [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 26)]
    pts = [jit(p, t, seed + i, 1.4) for i, p in enumerate(pts)]
    if fill: d.polygon(pts, fill=fill)
    d.line(pts + [pts[0]], fill=col, width=w, joint="curve")


@lru_cache(maxsize=1)
def paper():
    rng = np.random.default_rng(3)
    a = np.ones((H, W, 3), np.float32) * np.array(PAPER, np.float32)
    lo = rng.normal(0, 1, (H // 40, W // 40)).astype(np.float32)
    lo = np.array(Image.fromarray(((lo + 3) * 40).clip(0, 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), np.float32) / 40 - 3
    a += (lo * 3 + rng.normal(0, 1, (H, W)) * 2.5)[..., None]
    y, x = np.ogrid[:H, :W]; v = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2)
    a *= (1 - 0.18 * np.clip(v - 0.6, 0, 1))[..., None]
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))


def text(d, s, x, y, size, col=INK, anchor="mm", fn="segoeprb.ttf"):
    d.text((x, y), s, font=font(fn, size), fill=col, anchor=anchor)


# ------------------------------------------------------------------ stickman rig
def stick(d, t, hip, s=1.0, lean=0.0, armL=(200, 250), armR=(-20, 70), legL=(100, 90), legR=(80, 90),
          m=0.0, mood="normal", look=0.0, seed=1):
    """Angles in degrees (0 = right, 90 = down). arm=(upper, fore), leg=(thigh, shin)."""
    hx, hy = hip; L = 95 * s
    def p(o, ang, ln): a = math.radians(ang); return (o[0] + ln * math.cos(a), o[1] + ln * math.sin(a))
    neck = p((hx, hy), -90 + lean, 1.25 * L)
    head = p(neck, -90 + lean, 0.55 * L); hr = 0.5 * L
    wline(d, [(hx, hy), neck], t, seed, 8)
    for i, (a1, a2) in enumerate((armL, armR)):
        e = p(neck, a1, 0.62 * L); h = p(e, a2, 0.6 * L); wline(d, [neck, e, h], t, seed + 10 + i, 8)
    for i, (a1, a2) in enumerate((legL, legR)):
        k = p((hx, hy), a1, 0.75 * L); f = p(k, a2, 0.75 * L); wline(d, [(hx, hy), k, f], t, seed + 20 + i, 8)
    wcircle(d, head[0], head[1], hr, t, seed + 30, 8, fill=PAPER)
    ex = head[0] + look * hr * 0.35; ey = head[1] - hr * 0.12
    for sx in (-0.32, 0.32):
        cx = ex + sx * hr
        if mood == "sad": wline(d, [(cx - 10, ey - 2), (cx + 10, ey + 4)], t, seed + 40, 6)
        elif mood == "happy": d.arc((cx - 12, ey - 8, cx + 12, ey + 10), 200, 340, fill=INK, width=6)
        else: d.ellipse((cx - 7, ey - 7, cx + 7, ey + 7), fill=INK)
    my = head[1] + hr * 0.38
    if m > 0.05:
        d.ellipse((ex - 16 - 6 * m, my - 6 - 12 * m, ex + 16 + 6 * m, my + 8 + 16 * m), fill=INK)
    elif mood == "sad": d.arc((ex - 20, my, ex + 20, my + 22), 200, 340, fill=INK, width=6)
    else: d.arc((ex - 22, my - 16, ex + 22, my + 14), 20, 160, fill=INK, width=6)
    return head, hr


# ------------------------------------------------------------------ set pieces
def desk(d, t):
    wline(d, [(560, 760), (1240, 760)], t, 101, 9)                      # desk top
    wline(d, [(600, 760), (600, 960)], t, 102, 8); wline(d, [(1200, 760), (1200, 960)], t, 103, 8)
    wline(d, [(80, 960), (1840, 960)], t, 104, 6)                       # floor
    wrect(d, 790, 738, 960, 758, t, 105, 5, fill=(225, 225, 225))      # keyboard
    wline(d, [(640, 812), (790, 812)], t, 106, 8)                       # chair seat
    wline(d, [(650, 812), (650, 960)], t, 107, 7); wline(d, [(780, 812), (780, 960)], t, 108, 7)
    wline(d, [(650, 812), (640, 660)], t, 109, 7)                       # chair back


def monitor(d, t, glow=0.0, stamps=0):
    x0, y0, x1, y1 = 860, 470, 1180, 690
    fill = tuple(int(c) for c in np.array((230, 236, 245)) * (1 - glow) + np.array((150, 230, 255)) * glow)
    wrect(d, x0, y0, x1, y1, t, 110, 8, fill=fill)
    wline(d, [(1020, 690), (1020, 760)], t, 111, 8); wline(d, [(960, 760), (1080, 760)], t, 112, 8)
    for i in range(stamps):
        ang = [-12, 8, -4][i]; im = Image.new("RGBA", (300, 90), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
        dd.rectangle((6, 6, 294, 84), outline=RED + (255,), width=7); dd.text((150, 46), "EXPIRED", font=font("impact.ttf", 58), fill=RED + (255,), anchor="mm")
        im = im.rotate(ang, expand=True, resample=Image.BICUBIC); yield_ = (1020 - im.width // 2 + [-30, 25, 0][i], 520 - im.height // 2 + i * 55)
        d._image.paste(im, yield_, im)


def tv(d, t, on=0.0, frame=None):
    x0, y0, x1, y1 = 1380, 220, 1800, 520
    wrect(d, x0 - 14, y0 - 14, x1 + 14, y1 + 14, t, 120, 9)
    wline(d, [(1530, y1 + 14), (1500, y1 + 70)], t, 121, 6); wline(d, [(1650, y1 + 14), (1680, y1 + 70)], t, 122, 6)
    if on <= 0:
        d.rectangle((x0, y0, x1, y1), fill=(60, 62, 70)); return
    if frame is None or on < 1:
        r = np.random.default_rng(dr(t)).integers(60, 230, (y1 - y0, x1 - x0), dtype=np.uint8)
        d._image.paste(Image.fromarray(r).convert("RGB"), (x0, y0)); return
    d._image.paste(frame.resize((x1 - x0, y1 - y0), Image.BILINEAR), (x0, y0))
    text(d, "BREAKING", x0 + 12, y1 - 26, 30, (255, 255, 255), "lm", "impact.ttf")


@lru_cache(maxsize=1)
def host_frames():
    import subprocess
    fs = sorted(glob.glob(str(HERE / "host" / "*.mp4")))
    src = HERE / "host" / "apresentadora.mp4"; tmp = HERE / "host_frames"; tmp.mkdir(exist_ok=True)
    if not list(tmp.glob("*.jpg")):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf", "fps=24", "-q:v", "3", str(tmp / "%04d.jpg")], check=True)
    out = []
    for p in sorted(tmp.glob("*.jpg")):
        im = Image.open(p).convert("RGB"); w, h = im.size
        ch = int(w * 300 / 420); top = int(h * 0.06)                  # crop head & shoulders to TV ratio
        out.append(im.crop((0, top, w, top + ch)))
    return out


@lru_cache(maxsize=64)
def gem(mq, mood, tq, blink, size):
    g = gemmy_frame(mq / 10, mood, tq / 12, blink)
    return g.resize((size, int(size * g.height / g.width)), Image.BILINEAR)


def paste_gemmy(img, t, cx, base_y, size, m=0.0, mood="happy", rot=0.0):
    g = gem(round(m * 10), mood, dr(t) % 24, (t % 3.3) < 0.12, size)
    if rot: g = g.rotate(rot, expand=True, resample=Image.BICUBIC)
    img.paste(g, (int(cx - g.width / 2), int(base_y - g.height)), g)


def poof(d, t, cx, cy, k):
    if k <= 0 or k >= 1: return
    r = random.Random(7)
    for i in range(10):
        a = i / 10 * 2 * math.pi; rr = 40 + 160 * eout(k); s = (60 - 40 * k) * r.uniform(0.7, 1.2)
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a) * 0.7
        wcircle(d, x, y, s, t, 300 + i, 5, fill=(255, 255, 255))


def gems_rain(d, t, t0):
    r = random.Random(5)
    for i in range(26):
        x = r.uniform(100, 1820); sp = r.uniform(380, 700); y = -60 + (t - t0 - r.uniform(0, 1.2)) * sp
        if -60 < y < 1000:
            s = 22; c = (x, y); pts = [(c[0], c[1] - s), (c[0] + s * 0.7, c[1]), (c[0], c[1] + s), (c[0] - s * 0.7, c[1])]
            d.polygon([jit(p, t, i * 9 + j) for j, p in enumerate(pts)], fill=CYAN, outline=INK)


def caption(d, s):
    text(d, s, W / 2, 1030, 40, INK, "mm", "segoeprb.ttf")


# ------------------------------------------------------------------ scenes
def render(t):
    img = paper().copy(); d = ImageDraw.Draw(img)
    if t < 26.5:
        desk(d, t)
    if t < 6.6:                                                              # S1: expired
        stamps = sum(1 for s in (1.2, 2.3, 3.6) if t >= s)
        monitor(d, t, 0.0, stamps)
        tv(d, t, 0)
        slump = eio(seg(t, 4.6, 5.6)); typing = math.sin(t * 30) * 8 * (1 - slump)
        stick(d, t, (720, 800), 1.0, lean=10 + 30 * slump, armL=(30 + typing, -10 + 60 * slump), armR=(20 - typing, -20 + 60 * slump),
              legL=(170, 100), legR=(160, 95), m=mouth(1, t), mood="sad" if t > 1.2 else "normal", look=0.6)
        if 0.6 < t < 6.2: caption(d, "\u201cUgh... expired. Expired. EXPIRED! Every code I find is dead!\u201d")
    elif t < 11.6:                                                           # S2: Gemmy pops out
        k = seg(t, 6.9, 7.6)
        monitor(d, t, eio(seg(t, 6.6, 6.9)) * (1 - seg(t, 8.0, 8.6)), 0)
        tv(d, t, 0)
        stick(d, t, (720, 800), 1.0, lean=-15 * eout(seg(t, 7.0, 7.4)), armL=(200, 230), armR=(-30, -60),
              legL=(170, 100), legR=(160, 95), m=0, mood="normal", look=0.8)
        poof(d, t, 1020, 570, seg(t, 6.85, 7.6))
        if t > 6.95:
            x = 1020 + 120 * eout(k); y = 650 - 260 * math.sin(math.pi * k) + 110 * k
            paste_gemmy(img, t, x, y + 110, 300, mouth(2, t), "happy", rot=-25 * (1 - k))
        if 7.2 < t < 11.5: caption(d, "\u201cYo! Gemmy here. Dead codes? Not on my watch!\u201d")
    elif t < 17.2:                                                           # S3: the TV host
        monitor(d, t, 0, 0)
        fr = None
        if t >= 12.0:
            hf = host_frames(); fr = hf[min(len(hf) - 1, int((t - 12.0) * 24))]
        tv(d, t, 0 if t < 11.7 else (0.5 if t < 12.0 else 1.0), fr)
        stick(d, t, (720, 800), 1.0, lean=-10, armL=(200, 230), armR=(-30, -60), legL=(170, 100), legR=(160, 95), mood="normal", look=1.0)
        paste_gemmy(img, t, 1140, 770, 300, 0.0, "smug" if t > 12.0 else "happy")
        if t < 12.2: wline(d, [(1230, 640), (1370, 420)], t, 140, 5, RED)  # zap to the TV
        if 12.0 < t < 16.9: caption(d, "\u201cBreaking news! Five fresh codes just dropped today, and they all work!\u201d")
    elif t < 21.5:                                                           # S4: joy
        monitor(d, t, 0.6, 0)
        tv(d, t, 1.0, host_frames()[-1])
        jump = abs(math.sin((t - 17.2) * 5.2)) * 120
        stick(d, t, (760, 820 - jump), 1.0, armL=(-130, -110), armR=(-50, -70), legL=(110, 80), legR=(70, 100),
              m=mouth(4, t), mood="happy")
        paste_gemmy(img, t, 1140, 770 - abs(math.sin((t - 17.2) * 5.2 + 1)) * 60, 300, 0.0, "happy")
        gems_rain(d, t, 17.4)
        if t > 18.0: text(d, "+5 CODES", 1000, 330, 90, RED, "mm", "impact.ttf")
        if 17.6 < t < 20.5: caption(d, "\u201cNo way! It worked! It actually worked!\u201d")
    elif t < 26.5:                                                           # S5: Gemmy pitch
        monitor(d, t, 0.3, 0)
        tv(d, t, 1.0, host_frames()[-1])
        stick(d, t, (640, 790), 1.0, armL=(200, 230), armR=(-60, -100), legL=(170, 100), legR=(160, 95), mood="happy")
        z = eout(seg(t, 21.5, 22.0)); paste_gemmy(img, t, 1080, 800, int(300 + 160 * z), mouth(5, t), "happy")
        sk = eout(seg(t, 22.4, 22.8))
        if sk > 0:
            wrect(d, 1260, 600 - 40 * sk, 1640, 720 - 40 * sk, t, 150, 7, fill=(255, 236, 120))
            text(d, "FOLLOW", 1450, 640 - 40 * sk, 46, INK, "mm", "impact.ttf"); text(d, "CodeGames", 1450, 690 - 40 * sk, 40, RED, "mm", "segoeprb.ttf")
        if 21.8 < t < 26.2: caption(d, "\u201cWant them first? Follow CodeGames, and check the description!\u201d")
    else:                                                                    # S6: title
        k = eout(seg(t, 26.6, 27.1))
        text(d, "CodeGames", W / 2, 470, int(40 + 120 * k), INK, "mm", "segoeprb.ttf")
        if t > 27.2: text(d, "codes the day they drop", W / 2, 600, 54, RED, "mm", "segoeprb.ttf")
        paste_gemmy(img, t, W / 2 + 520, 820, 260, 0.0, "smug")
        stick(d, t, (W / 2 - 560, 800), 0.9, armL=(200, 230), armR=(-60, -100), legL=(110, 80), legR=(70, 100), mood="happy")
    return img


DUR = 29.5
if __name__ == "__main__":
    out = HERE / "review"; out.mkdir(exist_ok=True)
    for x in [float(a) for a in sys.argv[1:]] or [2, 4.5, 7.4, 9, 12.5, 15, 18.5, 23, 28]:
        render(x).save(out / f"p_{x:05.1f}.jpg", quality=82)
    print("ok")
