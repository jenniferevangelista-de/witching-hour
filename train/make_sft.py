"""Fine-tuning data for Tinker: the crew's verified stories, split by time.

Each example is the exact prompt a narrator gets and, as the answer, only the
sentences that passed the validator. Nights before the split date train; nights
after it are held out for the evaluation.

  python train/make_sft.py demo_data train/out 2016-04-15
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from witching_hour.agent import Haunting  # noqa: E402
from witching_hour.narrator import build_messages  # noqa: E402

data, out, split = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
out.mkdir(parents=True, exist_ok=True)
h = Haunting(data)
train, held_out = [], []
for p in sorted((data / "stories").glob("*.json")):
    st = json.loads(p.read_text(encoding="utf-8"))
    scan = h.night(st["night"])
    if scan is None or st["model"] in ("template",) or st["dropped"] or len(st["sentences"]) < 2:
        continue
    if not any(s["cites"] for s in st["sentences"]):
        continue
    answer = {"title": st["title"], "sentences": [{"text": s["text"], "cites": s["cites"]} for s in st["sentences"]]}
    if st["night"] < split:
        train.append({"messages": build_messages(scan, st["mode"]) + [{"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)}]})
    else:
        held_out.append({"night": st["night"], "mode": st["mode"]})
with open(out / "sft_train.jsonl", "w", encoding="utf-8") as f:
    for row in train:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
(out / "held_out.json").write_text(json.dumps(held_out, indent=1), encoding="utf-8")
print(f"train {len(train)} examples, held out {len(held_out)} (split {split})")
