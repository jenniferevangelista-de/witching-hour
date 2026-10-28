"""Command line: witching-hour fetch | scan | index | narrate | ask | evaluate | serve"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

DEFAULT_RAW = Path("data/raw")


def load_house(args):
    from .data import fetch_uci, load_home_assistant, load_uci

    if args.source == "ha":
        if not args.path:
            sys.exit("--path is required for a Home Assistant export")
        return load_home_assistant(args.path, tz=args.tz)
    path = Path(args.path) if args.path else fetch_uci(DEFAULT_RAW)
    return load_uci(path)


def pick_nights(house, args, cfg):
    from .data import eligible_nights

    all_nights = eligible_nights(house, cfg.start_hour, cfg.end_hour, cfg.context_days)
    if args.nights and args.nights != "all":
        wanted = {date.fromisoformat(d) for d in args.nights.split(",")}
        all_nights = [n for n in all_nights if n in wanted]
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        all_nights = all_nights[i::n]
    if args.limit:
        all_nights = all_nights[: args.limit]
    return all_nights


def cmd_fetch(args):
    from .data import fetch_uci

    print(fetch_uci(args.dest))


def cmd_scan(args):
    from .scanner import ScanConfig, make_backend, scan_night
    from .store import build_index, save_scan

    house = load_house(args)
    cfg = ScanConfig(context_days=args.context_days)
    kw = {"n_estimators": args.n_estimators, "max_context": args.max_context} if args.backend.startswith("tabpfn") else {}
    backend = make_backend(args.backend, **kw)
    sensors = args.sensors.split(",") if args.sensors else None
    nights = pick_nights(house, args, cfg)
    print(f"{house.name}: {len(nights)} nights, backend {backend.name}", flush=True)
    t_all = time.time()
    for k, n in enumerate(nights, 1):
        t0 = time.time()
        scan = scan_night(house, n, backend, sensors, cfg)
        save_scan(scan, args.out)
        print(f"[{k}/{len(nights)}] {n} score {scan.score:.1f} events {len(scan.events)} ({time.time() - t0:.1f}s)", flush=True)
    if not args.no_index:
        build_index(args.out, {"house": house.name, "attribution": house.attribution, "backend": backend.name,
                               "window": [cfg.start_hour, cfg.end_hour], "context_days": cfg.context_days})
    print(f"done in {time.time() - t_all:.0f}s")


def cmd_index(args):
    from .store import build_index

    meta = json.loads(args.meta) if args.meta else None
    idx = build_index(args.out, meta)
    print(f"{len(idx['nights'])} nights indexed")


def cmd_narrate(args):
    from .agent import Haunting
    from .narrator import OllamaChat, narrate, template_story
    from .store import build_index, save_story

    h = Haunting(args.data)
    dates = args.dates.split(",") if args.dates else [n["night"] for n in sorted(h.nights, key=lambda n: -n["score"])[: args.top]]
    chat = None if args.template else OllamaChat(args.model)
    if chat is not None and not chat.available():
        sys.exit(f"Ollama model {args.model} is not available at {chat.host}. Run: ollama pull {args.model}")
    for d in dates:
        scan = h.night(d)
        if scan is None:
            print(f"skip {d}: no scan")
            continue
        for mode in args.modes.split(","):
            t0 = time.time()
            story = template_story(scan, mode) if chat is None else narrate(scan, mode, chat=chat)
            save_story(story, args.data)
            print(f"{d} {mode}: {len(story.sentences)} verified, {len(story.rejected)} dropped, "
                  f"{story.attempts} attempt(s), {time.time() - t0:.0f}s  | {story.title}", flush=True)
    build_index(args.data)


def cmd_ask(args):
    from .agent import Haunting, investigate
    from .narrator import OllamaChat

    chat = OllamaChat(args.model)
    run = investigate(args.question, Haunting(args.data), chat, max_steps=args.max_steps)
    for s in run.steps:
        print(f"-> {s['tool']}({json.dumps(s['args'])})")
    print("\n" + run.answer)
    if args.save:
        p = Path(args.save)
        p.parent.mkdir(parents=True, exist_ok=True)
        runs = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        runs = [r for r in runs if r["question"] != run.question] + [run.to_dict()]
        p.write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")


def cmd_evaluate(args):
    import numpy as np

    from .data import eligible_nights
    from .evaluate import evaluate
    from .scanner import ScanConfig, make_backend

    house = load_house(args)
    cfg = ScanConfig()
    nights = eligible_nights(house, cfg.start_hour, cfg.end_hour, cfg.context_days)
    idx = np.linspace(0, len(nights) - 1, min(args.nights, len(nights))).round().astype(int)
    nights = [nights[i] for i in sorted(set(idx))]
    sensors = args.sensors.split(",")
    backends = []
    for b in args.backends.split(","):
        kw = {"n_estimators": args.n_estimators, "max_context": args.max_context} if b.startswith("tabpfn") else {}
        backends.append(make_backend(b, **kw))
    res = evaluate(house, backends, nights, sensors, cfg, seed=args.seed)
    out = {"nights": [n.isoformat() for n in nights], "sensors": sensors, "results": [r.to_dict() for r in res]}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1), encoding="utf-8")
    for r in res:
        print(json.dumps(r.to_dict()))


def cmd_serve(args):
    import os

    import uvicorn

    os.environ["WH_DATA"] = str(args.data)
    uvicorn.run("witching_hour.app:app", host=args.host, port=args.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="witching-hour", description="What happened in your house at 3 AM?")
    sub = p.add_subparsers(dest="cmd", required=True)

    def house_args(sp):
        sp.add_argument("--source", choices=["uci", "ha"], default="uci")
        sp.add_argument("--path", help="UCI zip/csv, or a Home Assistant history CSV")
        sp.add_argument("--tz", default="UTC", help="time zone of the house (Home Assistant exports are in UTC)")

    sp = sub.add_parser("fetch", help="download the public UCI house")
    sp.add_argument("--dest", default=str(DEFAULT_RAW))
    sp.set_defaults(fn=cmd_fetch)

    sp = sub.add_parser("scan", help="scan nights with TabPFN (or a baseline)")
    house_args(sp)
    sp.add_argument("--out", default="demo_data")
    sp.add_argument("--backend", default="tabpfn")
    sp.add_argument("--nights", default="all", help="all, or comma separated YYYY-MM-DD")
    sp.add_argument("--shard", help="i/n: scan every n-th night starting at i (for parallel jobs)")
    sp.add_argument("--limit", type=int, default=0)
    sp.add_argument("--sensors", help="comma separated sensor ids (default: all)")
    sp.add_argument("--context-days", type=int, default=14)
    sp.add_argument("--n-estimators", type=int, default=4)
    sp.add_argument("--max-context", type=int, default=1200)
    sp.add_argument("--no-index", action="store_true")
    sp.set_defaults(fn=cmd_scan)

    sp = sub.add_parser("index", help="rebuild demo_data/index.json")
    sp.add_argument("--out", default="demo_data")
    sp.add_argument("--meta", help="JSON with house/backend metadata")
    sp.set_defaults(fn=cmd_index)

    sp = sub.add_parser("narrate", help="write the Medium and Skeptic stories with a local model")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--dates")
    sp.add_argument("--top", type=int, default=12)
    sp.add_argument("--modes", default="medium,skeptic")
    sp.add_argument("--model", default=None)
    sp.add_argument("--template", action="store_true", help="no model, deterministic sentences")
    sp.set_defaults(fn=cmd_narrate)

    sp = sub.add_parser("ask", help="ask the investigator agent a question")
    sp.add_argument("question")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--model", default=None)
    sp.add_argument("--max-steps", type=int, default=6)
    sp.add_argument("--save", help="append the run (question, tool calls, answer) to this JSON file")
    sp.set_defaults(fn=cmd_ask)

    sp = sub.add_parser("evaluate", help="planted ghosts benchmark")
    house_args(sp)
    sp.add_argument("--nights", type=int, default=40)
    sp.add_argument("--sensors", default="T1,T5,T9,RH_1,RH_5,Appliances")
    sp.add_argument("--backends", default="tabpfn,lightgbm,seasonal")
    sp.add_argument("--n-estimators", type=int, default=4)
    sp.add_argument("--max-context", type=int, default=1200)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--out", default="demo_data/eval.json")
    sp.set_defaults(fn=cmd_evaluate)

    sp = sub.add_parser("serve", help="open the web app")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    if getattr(args, "model", "x") is None:
        from .narrator import DEFAULT_MODEL

        args.model = DEFAULT_MODEL
    args.fn(args)


if __name__ == "__main__":
    main()
