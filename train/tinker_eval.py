"""Base vs fine-tuned on held-out nights, scored by the same validator the demo uses.

  python train/tinker_eval.py demo_data train/out [tinker://.../sampler_weights/final]
Without a model path it scores the base model.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import tinker
from tinker import types
from tinker_cookbook import renderers
from tinker_cookbook.tokenizer_utils import get_tokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witching_hour.agent import Haunting  # noqa: E402
from witching_hour.narrator import _parse_json, build_messages, validate  # noqa: E402

import os  # noqa: E402

MODEL = os.environ.get("WH_TINKER_MODEL", "Qwen/Qwen3-8B")
RENDERER = os.environ.get("WH_TINKER_RENDERER", "qwen3_disable_thinking")


async def main(data: str, out: str, model_path: str | None):
    h = Haunting(data)
    cases = json.loads(Path(out, "held_out.json").read_text(encoding="utf-8"))
    client = tinker.ServiceClient().create_sampling_client(base_model=MODEL, model_path=model_path)
    renderer = renderers.get_renderer(RENDERER, get_tokenizer(MODEL))
    params = types.SamplingParams(max_tokens=700, temperature=0.0, stop=renderer.get_stop_sequences())

    async def one(case):
        scan = h.night(case["night"])
        t0 = time.time()
        r = await client.sample_async(prompt=renderer.build_generation_prompt(build_messages(scan, case["mode"])),
                                      num_samples=1, sampling_params=params)
        msg, _ = renderer.parse_response(r.sequences[0].tokens)
        content = msg["content"] if isinstance(msg["content"], str) else renderers.format_content_as_string(msg["content"])
        try:
            raw = _parse_json(content)
            kept, rejected = validate(raw, scan)
            ok = True
        except Exception:
            kept, rejected, ok = [], [], False
        return {"night": case["night"], "mode": case["mode"], "json_ok": ok, "verified": len(kept),
                "dropped": len(rejected), "seconds": round(time.time() - t0, 1), "sample": content[:400]}

    rows = await asyncio.gather(*[one(c) for c in cases])
    v = sum(r["verified"] for r in rows)
    d = sum(r["dropped"] for r in rows)
    summary = {
        "model": model_path or MODEL, "cases": len(rows), "json_ok": sum(r["json_ok"] for r in rows),
        "sentences": v + d, "verified": v, "grounded_share": round(v / (v + d), 3) if v + d else 0.0,
        "clean_stories": sum(1 for r in rows if r["json_ok"] and r["verified"] and not r["dropped"]),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 1),
    }
    tag = "tuned" if model_path else "base"
    Path(out, f"eval_{tag}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
