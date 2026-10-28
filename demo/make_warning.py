"""Render "The Warning", the staged demo recording (python demo/make_warning.py out_dir).

A hallway camera at night. A woman takes her coat and walks to the front door.
The lamp flickers, something whispers, three knocks, a tall shadow passes behind
her along the wall by the door. She hesitates, walks back, hangs the coat again and stays home.
Everything here is drawn and synthesised by this script: it is a staged clip for
the demo, not found footage.
"""
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS, DUR = 640, 360, 24, 20.0
SR = 44100
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/out")
rng = np.random.default_rng(31)


def lerp(a, b, u):
    return a + (b - a) * max(0.0, min(1.0, u))


def path_x(t):
    """Where the woman stands (None: out of frame)."""
    keys = [(0.0, -40), (0.6, 40), (3.0, 128), (5.6, 128), (9.2, 432), (10.6, 432), (13.0, 140), (15.0, 140), (18.0, -60)]
    for (t0, x0), (t1, x1) in zip(keys, keys[1:]):
        if t0 <= t <= t1:
            return lerp(x0, x1, (t - t0) / (t1 - t0))
    return None


def walking(t):
    return (0.6 < t < 3.0) or (5.6 < t < 9.2) or (10.6 < t < 13.0) or (15.0 < t < 18.0)


def wearing_coat(t):
    return 5.0 <= t < 14.2


def lamp(t):
    """Lamp brightness multiplier: steady, then the flicker at 7.0 s."""
    if 7.0 <= t < 7.25:
        return 0.42
    if 7.25 <= t < 7.4:
        return 1.18
    if 7.4 <= t < 7.6:
        return 0.55
    return 1.0


def frame(t, font, small):
    img = Image.new("RGB", (W, H))
    px = np.zeros((H, W, 3), np.float32)
    y = np.linspace(0, 1, H)[:, None]
    px[..., 0] = 34 + 18 * (1 - y)
    px[..., 1] = 36 + 20 * (1 - y)
    px[..., 2] = 52 + 26 * (1 - y)
    px[285:, :, :] *= 0.62  # floor
    xs = np.arange(W)[None, :]
    glow = np.exp(-(((xs - 320) / 210.0) ** 2 + ((np.arange(H)[:, None] - 10) / 150.0) ** 2))
    px += glow[..., None] * np.array([70, 62, 40])
    img = Image.fromarray(np.clip(px, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.line([(0, 285), (W, 285)], fill=(20, 20, 28), width=3)
    # front door on the right, with light under it
    d.rectangle([462, 64, 572, 286], fill=(58, 38, 30), outline=(28, 20, 16), width=5)
    d.rectangle([474, 78, 560, 160], outline=(40, 26, 20), width=3)
    d.rectangle([474, 176, 560, 272], outline=(40, 26, 20), width=3)
    kx = 478 + (2 * math.sin(t * 60) if 9.2 <= t < 9.9 else 0)
    d.ellipse([kx - 6, 182, kx + 6, 194], fill=(196, 160, 90))
    gap = (236, 214, 160)
    if 9.95 <= t < 10.5:  # a shadow crosses the light under the door
        u = (t - 9.95) / 0.55
        d.rectangle([462, 284, 572, 290], fill=gap)
        sx = 462 + 140 * u - 40
        d.rectangle([max(462, sx), 284, min(572, sx + 60), 290], fill=(30, 26, 22))
        d.rectangle([max(462, sx + 10), 64, min(572, sx + 50), 286], fill=(46, 30, 24))
    else:
        d.rectangle([462, 284, 572, 290], fill=gap)
    # coat rack on the left
    d.line([(96, 110), (96, 286)], fill=(44, 32, 26), width=7)
    d.line([(80, 112), (112, 112)], fill=(44, 32, 26), width=5)
    d.ellipse([78, 278, 114, 292], fill=(36, 26, 22))
    if not wearing_coat(t):
        d.polygon([(84, 116), (108, 116), (118, 200), (74, 200)], fill=(124, 34, 44), outline=(70, 18, 24))
    # the woman
    x = path_x(t)
    if x is not None:
        step = math.sin(t * 9) * 7 if walking(t) else 0
        body = (24, 26, 40)
        d.ellipse([x - 13, 96, x + 13, 124], fill=body)
        coat = (124, 34, 44) if wearing_coat(t) else body
        d.rounded_rectangle([x - 22, 124, x + 22, 214], radius=10, fill=coat)
        d.line([(x - 8, 210), (x - 8 - step, 284)], fill=body, width=11)
        d.line([(x + 8, 210), (x + 8 + step, 284)], fill=body, width=11)
        if 3.0 <= t < 5.0 or 13.0 <= t < 15.0:  # reaching for the coat rack
            d.line([(x - 18, 136), (104, 120)], fill=coat, width=9)
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    # lamp, grain, scanlines, vignette
    a = np.asarray(img).astype(np.float32) * lamp(t)
    a += rng.normal(0, 9, (H, W, 1))
    a[::2] *= 0.94
    vy, vx = np.ogrid[:H, :W]
    a *= (1 - 0.55 * (((vx - W / 2) / (W / 2)) ** 2 + ((vy - H / 2) / (H / 2)) ** 2) / 2)[..., None]
    if 9.95 <= t < 10.5:  # the shadow of someone tall passes behind her, along the wall by the door
        u = (t - 9.95) / 0.55
        sx = int(360 + 260 * u)
        x0, x1 = max(0, sx), min(W, sx + 80)
        if x1 > x0:
            a[36:292, x0:x1] *= 0.3
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    if int(t * 2) % 2 == 0:
        d.ellipse([18, 18, 30, 30], fill=(220, 40, 50))
    d.text((38, 14), "REC", font=font, fill=(235, 235, 235))
    d.text((W - 170, 16), "HALLWAY CAM 02", font=small, fill=(220, 220, 220))
    d.text((18, H - 32), f"OCT 28 2026  21:43:{int(t) + 17:02d}", font=small, fill=(235, 235, 235))
    return img


def tone(n, f, sr=SR):
    return np.sin(2 * np.pi * f * np.arange(n) / sr)


def audio():
    n = int(DUR * SR)
    x = rng.normal(0, 1, n) * 0.003  # room tone
    x = np.convolve(x, np.ones(8) / 8, mode="same")

    def add(t0, sig):
        i = int(t0 * SR)
        x[i:i + len(sig)] += sig[: max(0, n - i)]

    for t0 in np.arange(0.7, 18.0, 0.5):  # soft footsteps while walking
        if walking(t0):
            k = int(0.06 * SR)
            add(t0, rng.normal(0, 1, k) * np.exp(-np.arange(k) / (0.012 * SR)) * 0.006)
    k = int(0.6 * SR)  # the lamp buzzes during the flicker
    buzz = (tone(k, 100) + 0.5 * tone(k, 200) + 0.3 * tone(k, 300)) * 0.03
    add(7.0, buzz * np.hanning(k))
    k = int(0.65 * SR)  # the whisper nobody heard
    wn = rng.normal(0, 1, k)
    wn = np.convolve(wn, np.hanning(40) / 20, mode="same") - np.convolve(wn, np.hanning(400) / 200, mode="same")
    env = np.hanning(k) * (0.6 + 0.4 * np.sin(np.linspace(0, 9 * np.pi, k)) ** 2)
    add(8.3, wn * env * 0.05)
    for t0 in (9.2, 9.45, 9.7):  # three knocks
        k = int(0.18 * SR)
        knock = (tone(k, 78) + 0.4 * tone(k, 160)) * np.exp(-np.arange(k) / (0.035 * SR)) * 0.42
        knock[:120] += rng.normal(0, 0.25, 120)
        add(t0, knock)
    return np.clip(x, -1, 1)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    frames = OUT / "frames"
    frames.mkdir(exist_ok=True)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 18)
        small = ImageFont.truetype("DejaVuSansMono.ttf", 15)
    except OSError:
        font = small = ImageFont.load_default()
    for i in range(int(DUR * FPS)):
        frame(i / FPS, font, small).save(frames / f"{i:04d}.png")
    a = (audio() * 32767).astype(np.int16)
    with wave.open(str(OUT / "the_warning.wav"), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(a.tobytes())
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames / "%04d.png"),
                    "-i", str(OUT / "the_warning.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "27",
                    "-preset", "slow", "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart",
                    str(OUT / "the_warning.mp4")], check=True)
    print("rendered", OUT / "the_warning.mp4")


if __name__ == "__main__":
    main()
