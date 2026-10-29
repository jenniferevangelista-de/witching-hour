"""Read-only media diagnostics for the two public Witching Hour videos.

Run after rendering on the remote runner. Originals are never overwritten.
Sparse frames and short excerpts support human review; metrics do not certify QA.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

VIDEO_NAMES = ("witching_hour_film.mp4", "witching_hour_tour.mp4")
MAX_IMAGE_BYTES = 180_000
MAX_AUDIO_BYTES = 250_000
MAX_PREVIEW_LOG_BYTES = 950_000
LOG_CHUNK = 12_000


def command(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=timeout,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace")[-2400:]
        raise RuntimeError(f"{args[0]} failed ({result.returncode}): {detail}")
    return result


def probe(path: Path) -> dict:
    result = command([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size,bit_rate,format_name:"
        "stream=index,codec_type,codec_name,width,height,r_frame_rate,"
        "avg_frame_rate,sample_rate,channels,channel_layout,duration,bit_rate",
        "-of", "json", str(path),
    ], timeout=30)
    return json.loads(result.stdout)


def finite_number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def last_number(pattern: str, text: str):
    values = re.findall(pattern, text, flags=re.MULTILINE)
    return finite_number(values[-1]) if values else None


def audio_levels(path: Path) -> dict:
    # ebur128 and volumedetect inspect the decoded source; no normalized
    # audio is written, and neither filter changes the source file.
    result = command([
        "ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-i", str(path),
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-af", "ebur128=peak=true:framelog=verbose,volumedetect",
        "-f", "null", "-",
    ], timeout=180)
    log = result.stderr.decode("utf-8", "replace")
    numeric = r"([-+]?(?:\d+(?:\.\d+)?|inf))"
    summary_at = log.rfind("Summary:")
    return {
        "integrated_lufs": last_number(r"^\s*I:\s*" + numeric + r"\s+LUFS", log),
        "loudness_range_lu": last_number(r"^\s*LRA:\s*" + numeric + r"\s+LU", log),
        "true_peak_dbfs": last_number(r"^\s*Peak:\s*" + numeric + r"\s+dBFS", log),
        "mean_volume_db": last_number(r"mean_volume:\s*" + numeric + r"\s+dB", log),
        "max_sample_volume_db": last_number(r"max_volume:\s*" + numeric + r"\s+dB", log),
        "summary": log[summary_at:][-5000:] if summary_at >= 0 else log[-5000:],
        "measurement_only": True,
    }


def timestamp(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{seconds % 60:06.3f}"


def contact_sheet(path: Path, seconds: float, output: Path) -> dict:
    positions = [0.0, .2 * seconds, .4 * seconds, .6 * seconds,
                 .8 * seconds, max(0.0, seconds - 1.0)]
    width, height, gap, header = 1600, 900, 12, 48
    cell_w = (width - gap * 4) // 3
    cell_h = (height - header - gap * 3) // 2
    label_h = 28
    canvas = Image.new("RGB", (width, height), "#100d1c")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18,
        )
    except OSError:
        font = ImageFont.load_default()
    draw.text((gap, 12), f"{path.name} | sparse frame samples | {seconds:.3f}s",
              fill="white", font=font)
    for index, at in enumerate(positions):
        frame = command([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-threads", "1", "-ss", f"{at:.6f}", "-i", str(path),
            "-map", "0:v:0", "-frames:v", "1",
            "-vf", f"scale={cell_w}:{cell_h-label_h}:force_original_aspect_ratio=decrease",
            "-f", "image2pipe", "-vcodec", "png", "-",
        ], timeout=45).stdout
        image = Image.open(io.BytesIO(frame)).convert("RGB")
        x = gap + (index % 3) * (cell_w + gap)
        y = header + gap + (index // 3) * (cell_h + gap)
        draw.rectangle((x, y, x + cell_w, y + cell_h), fill="#211a31")
        canvas.paste(
            image,
            (x + (cell_w - image.width) // 2,
             y + label_h + (cell_h - label_h - image.height) // 2),
        )
        draw.text((x + 6, y + 4), f"{index + 1} | {timestamp(at)}",
                  fill="#b4ffd9", font=font)

    quality = 65
    while True:
        buffer = io.BytesIO()
        canvas.save(buffer, format="JPEG", quality=quality,
                    optimize=True, progressive=True)
        data = buffer.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            output.write_bytes(data)
            break
        if quality > 25:
            quality -= 10
        else:
            canvas = canvas.resize(
                (int(canvas.width * .85), int(canvas.height * .85)),
                Image.Resampling.LANCZOS,
            )
            if canvas.width < 640:
                raise RuntimeError("Contact sheet cannot meet its payload budget.")
    return {
        "source": path.name, "file": output.name, "timestamps_seconds": positions,
        "width": canvas.width, "height": canvas.height, "jpeg_quality": quality,
        "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "note": "Six sampled frames cannot establish motion quality or lip sync.",
    }


def srt_seconds(value: str) -> float:
    hours, minutes, seconds = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def subtitle_cues(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = block.splitlines()
        match = next((
            re.fullmatch(r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s+-->\s+"
                         r"(\d{2}:\d{2}:\d{2}[,.]\d{3})", line.strip())
            for line in lines if "-->" in line
        ), None)
        if match is None:
            continue
        time_index = next(i for i, line in enumerate(lines) if "-->" in line)
        cues.append({
            "start": srt_seconds(match.group(1)),
            "end": srt_seconds(match.group(2)),
            "text": " ".join(lines[time_index + 1:]),
        })
    return cues


def guardian_start(path: Path, seconds: float) -> tuple[float, str]:
    cues = subtitle_cues(path.with_suffix(".srt"))
    # The renderer encloses only the inserted recorded Guardian audio in
    # curly quotes. Start four seconds before it to retain brief context.
    for cue in cues:
        if cue["text"].lstrip().startswith(("“", '"')):
            return max(0.0, cue["start"] - 4.0), "first quoted recorded reply in SRT"
    for index, cue in enumerate(cues):
        window = " ".join(c["text"] for c in cues[index:index + 3]).lower()
        if re.search(r"recorded\s+guardian|guardian\s+session", window):
            return max(0.0, cue["start"]), "Guardian introduction in SRT"
    return min(50.0, max(0.0, seconds - 20.0)), "heuristic fallback; inspect source"


def encode_audio(source: Path, output: Path, start: float, length: float) -> None:
    command([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
        "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{length:.6f}",
        "-map", "0:a:0", "-vn", "-sn", "-dn", "-ac", "1", "-ar", "22050",
        "-c:a", "libmp3lame", "-b:a", "32k",
        "-write_xing", "0", "-id3v2_version", "0", str(output),
    ], timeout=60)


def audio_previews(media: list[dict], directory: Path) -> list[dict]:
    audible = [item for item in media if item.get("has_audio")]
    if not audible:
        return []
    film = next((item for item in audible if item["name"].endswith("_film.mp4")),
                audible[0])
    tour = next((item for item in audible if item["name"].endswith("_tour.mp4")),
                audible[-1])
    guardian_at, guardian_method = guardian_start(
        directory / tour["name"], tour["duration_seconds"],
    )
    specs = [
        ("intro", film, 0.0, "first twenty seconds"),
        ("guardian", tour, guardian_at, guardian_method),
        ("credits", tour, max(0.0, tour["duration_seconds"] - 20.0),
         "last twenty seconds"),
    ]
    previews = []
    for role, item, start, method in specs:
        length = min(20.0, item["duration_seconds"])
        start = max(0.0, min(start, item["duration_seconds"] - length))
        output = directory / f"qa_audio_{role}.mp3"
        previews.append({
            "role": role, "source": item["name"], "file": output.name,
            "start_seconds": start, "requested_duration_seconds": length,
            "selection_method": method,
        })

    # Three ~20-second clips at 32 kbps are ~240 kB total. Shorten only the
    # diagnostic excerpts if container overhead would exceed the strict cap.
    for attempt in range(3):
        for item in previews:
            encode_audio(
                directory / item["source"], directory / item["file"],
                item["start_seconds"], item["requested_duration_seconds"],
            )
            item["size_bytes"] = (directory / item["file"]).stat().st_size
        total = sum(item["size_bytes"] for item in previews)
        if total <= MAX_AUDIO_BYTES:
            break
        factor = .96 * MAX_AUDIO_BYTES / total
        for item in previews:
            item["requested_duration_seconds"] *= factor
    else:
        raise RuntimeError("Audio previews exceeded the aggregate 250 kB limit.")

    for item in previews:
        path = directory / item["file"]
        info = probe(path)
        item["encoded_duration_seconds"] = finite_number(info.get("format", {}).get("duration"))
        item["codec"] = "mp3"
        item["channels"] = 1
        item["target_bitrate_bps"] = 32000
        item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return previews


def emit_preview(kind: str, path: Path, used: int) -> tuple[int, bool]:
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    lines = [f"WH_{kind}_START:{path.name}"]
    lines += [
        f"WH_{kind}_DATA:{payload[index:index + LOG_CHUNK]}"
        for index in range(0, len(payload), LOG_CHUNK)
    ]
    lines.append(f"WH_{kind}_END:{path.name}")
    size = sum(len(line.encode("utf-8")) + 1 for line in lines)
    if used + size > MAX_PREVIEW_LOG_BYTES:
        return used, False
    for line in lines:
        print(line, flush=True)
    return used + size, True


def main(directory: Path) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_policy": "Only the two named public product videos; originals are read only.",
        "limits": {
            "per_contact_sheet_bytes": MAX_IMAGE_BYTES,
            "aggregate_audio_bytes": MAX_AUDIO_BYTES,
            "aggregate_preview_marker_bytes": MAX_PREVIEW_LOG_BYTES,
            "base64_chunk_characters": LOG_CHUNK,
        },
        "notes": [
            "Diagnostics support human review; they do not constitute audiovisual approval.",
            "Frames are sparse samples. Audio contains three excerpts total, not every passage.",
            "Audio previews prefer film introduction and tour Guardian/credits; source and times are recorded.",
        ],
        "media": [], "contact_sheets": [], "audio_previews": [], "errors": [],
    }
    for name in VIDEO_NAMES:
        path = directory / name
        if not path.is_file():
            continue
        item = {"name": name}
        report["media"].append(item)
        try:
            metadata = probe(path)
            item["metadata"] = metadata
            seconds = finite_number(metadata.get("format", {}).get("duration"))
            if seconds is None or seconds <= 0:
                raise ValueError("Video duration is missing or invalid.")
            item["duration_seconds"] = seconds
            streams = metadata.get("streams", [])
            item["has_video"] = any(s.get("codec_type") == "video" for s in streams)
            item["has_audio"] = any(s.get("codec_type") == "audio" for s in streams)
            if not item["has_video"]:
                raise ValueError("Expected a video stream.")
            if not item["has_audio"]:
                raise ValueError("Expected an audio stream.")
            item["audio_levels"] = audio_levels(path)
            output = directory / f"qa_{path.stem}_contact.jpg"
            report["contact_sheets"].append(contact_sheet(path, seconds, output))
        except Exception as exc:
            item["error"] = str(exc)
            report["errors"].append(f"{name}: {exc}")

    if not report["media"]:
        report["errors"].append("Neither expected Witching Hour MP4 exists.")
    eligible = [
        item for item in report["media"]
        if item.get("has_audio") and item.get("duration_seconds")
    ]
    if eligible:
        try:
            report["audio_previews"] = audio_previews(eligible, directory)
        except Exception as exc:
            report["errors"].append(f"audio previews: {exc}")

    used = 0
    for kind, items in (("IMAGE", report["contact_sheets"]),
                        ("AUDIO", report["audio_previews"])):
        for item in items:
            used, emitted = emit_preview(kind, directory / item["file"], used)
            item["emitted_to_log"] = emitted
            if not emitted:
                report["errors"].append(f"Preview log budget skipped {item['file']}.")
    report["preview_log_bytes"] = used
    report["audio_preview_bytes"] = sum(
        item["size_bytes"] for item in report["audio_previews"]
    )
    report["status"] = "diagnostics_complete" if not report["errors"] else "diagnostic_errors"
    destination = directory / "qa_media.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print("WH_QA_METADATA:" + json.dumps(
        report, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ), flush=True)
    print(
        f"WH_QA_REPORT:{destination.name} status={report['status']} "
        f"media={len(report['media'])} preview_log_bytes={used}",
        flush=True,
    )
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "video/out")))
