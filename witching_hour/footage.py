"""The Unheard: what a recording really contains, before any spirit is summoned.

Same algorithm as the browser version (static/paranormal.js), so a recording can be
investigated at home with OpenCV or in the visitor's own browser:
- every 0.25 s: mean brightness, motion (mean absolute frame difference), the share of
  pixels that changed and where they changed (left, center, right);
- the sound, in 0.25 s windows: loudness in dB;
- an event is a run of windows far from the clip's own median (robust z-score with the
  median absolute deviation), so a recording is compared with itself, not with a model
  of some other room.
None of this detects ghosts. It finds moments worth asking about, with a confidence.
"""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import numpy as np

STEP = 0.25
W, H = 160, 90


def frame_features(path: str | Path, max_seconds: float = 90.0) -> list[dict]:
    import cv2

    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    dur = min(n / fps if n else max_seconds, max_seconds)
    rows, prev, t = [], None, 0.0
    while t < dur:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = cap.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(frame, (W, H)), cv2.COLOR_BGR2GRAY).astype(np.float32)
        row = {"t": round(t, 2), "brightness": float(g.mean() / 255), "motion": 0.0, "area": 0.0, "cx": None}
        if prev is not None:
            d = np.abs(g - prev)
            mask = d > 25
            row["motion"] = float(d.mean() / 255)
            row["area"] = float(mask.mean())
            if row["area"] > 0.002:
                row["cx"] = float(np.nonzero(mask)[1].mean() / W)
        rows.append(row)
        prev, t = g, t + STEP
    cap.release()
    return rows


def audio_levels(path: str | Path, max_seconds: float = 90.0) -> list[float]:
    """Loudness in dB per 0.25 s window (ffmpeg extracts mono 16 kHz PCM)."""
    wav = Path(path).with_suffix(".probe.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-t", str(max_seconds), "-ac", "1", "-ar", "16000", str(wav)],
                   check=True)
    with wave.open(str(wav)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    wav.unlink(missing_ok=True)
    hop = int(16000 * STEP)
    return [float(20 * np.log10(np.sqrt(np.mean(x[i:i + hop] ** 2)) + 1e-6)) for i in range(0, len(x) - hop + 1, hop)]


def robust_z(x: np.ndarray) -> np.ndarray:
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826
    return (x - med) / max(mad, 1e-6)


def where(cx: float | None) -> str | None:
    if cx is None:
        return None
    return "left" if cx < 0.36 else "right" if cx > 0.64 else "center"


def _runs(mask: np.ndarray, max_gap: int = 1) -> list[tuple[int, int]]:
    runs, start, last = [], None, None
    for i, m in enumerate(mask):
        if m:
            if start is None:
                start = i
            elif i - last - 1 > max_gap:
                runs.append((start, last))
                start = i
            last = i
    if start is not None:
        runs.append((start, last))
    return runs


def detect(rows: list[dict], levels: list[float], z_thr: float = 4.0, min_windows: int = 1) -> list[dict]:
    """Evidence from features: light changes, motion and sounds that stand out from the clip itself."""
    if len(rows) < 8:
        return []
    t = np.array([r["t"] for r in rows])
    bright = np.array([r["brightness"] for r in rows])
    dbright = np.abs(np.diff(bright, prepend=bright[0]))
    motion = np.array([r["motion"] for r in rows])
    signals = [("light_change", dbright, None), ("motion", motion, None)]
    if levels:
        lv = np.array(levels[: len(rows)] + [levels[-1]] * max(0, len(rows) - len(levels)))
        signals.append(("audio", lv, None))
    evidence = []
    for kind, x, _ in signals:
        z = robust_z(x)
        floor = {"light_change": 0.03, "motion": 0.012, "audio": None}[kind]
        mask = z > z_thr
        if floor is not None:
            mask &= x > floor
        for a, b in _runs(mask):
            if b - a + 1 < min_windows:
                continue
            peak = a + int(np.argmax(z[a:b + 1]))
            e = {"type": kind, "start": float(t[a]), "end": float(t[b] + STEP), "confidence": round(min(1.0, float(z[peak]) / 8), 2)}
            if kind == "light_change":
                delta = (bright[peak] - bright[max(peak - 1, 0)]) / max(bright[max(peak - 1, 0)], 1e-3)
                e["description"] = f"the light {'rose' if delta > 0 else 'dipped'} {abs(delta) * 100:.0f}% in a quarter second"
            elif kind == "motion":
                cxs = [rows[i]["cx"] for i in range(a, b + 1) if rows[i]["cx"] is not None]
                e["where"] = where(float(np.median(cxs)) if cxs else None) or "center"
                e["description"] = f"movement on the {e['where']} side ({max(r['area'] for r in rows[a:b + 1]) * 100:.0f}% of the frame changed)"
            else:
                base = float(np.median(x))
                e["description"] = f"a sound {x[peak] - base:.0f} dB above the room"
            evidence.append(e)
    evidence.sort(key=lambda e: e["start"])
    for i, e in enumerate(evidence, 1):
        e["id"] = f"ev-{i:03d}"
    return evidence


def investigate(path: str | Path) -> dict:
    rows = frame_features(path)
    levels = audio_levels(path)
    ev = detect(rows, levels)
    return {"source": Path(path).name, "duration": rows[-1]["t"] + STEP if rows else 0.0, "evidence": ev,
            "series": {"t": [r["t"] for r in rows], "brightness": [round(r["brightness"], 4) for r in rows],
                       "motion": [round(r["motion"], 4) for r in rows], "audio_db": [round(v, 1) for v in levels[: len(rows)]]}}
