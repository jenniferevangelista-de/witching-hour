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
    if args.dates:
        dates = args.dates.split(",")
    else:
        dates = [n["night"] for n in sorted(h.nights, key=lambda n: -n["score"])[: args.top]]
        cold = [n["night"] for n in sorted(h.nights, key=lambda n: -n.get("n_cold", 0)) if n.get("n_cold")]
        dates += [d for d in cold if d not in dates][: args.cold]
    if args.shard:
        i, k = (int(x) for x in args.shard.split("/"))
        dates = dates[i::k]
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
    if not args.no_index:
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


def cmd_voice(args):
    from .agent import Haunting
    from .voice import load_env, voice_stories

    load_env(args.env)
    h = Haunting(args.data)
    dates = args.dates.split(",") if args.dates else [n["night"] for n in sorted(h.nights, key=lambda n: -n["score"])[: args.top]]
    print(voice_stories(args.data, dates, args.modes.split(",")))


def cmd_tonight(args):
    from .scanner import make_backend
    from .tonight import fetch_forecast, forecast_house
    from .voice import load_env

    load_env(args.env)
    house = load_house(args)
    fc = fetch_forecast(args.place)
    res = forecast_house(house, fc, make_backend(args.backend))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in res["rooms"]:
        print(f"{r['room']}: {r['expected']} °C at {r['coldest_time']} (90% {r['low']} to {r['high']}), P(<18 °C) {r['p_below_18']}")


def cmd_bakeoff(args):
    from .agent import Haunting
    from .bakeoff import MODELS, local_reference, run_bakeoff
    from .voice import load_env

    load_env(args.env)
    h = Haunting(args.data)
    dates = args.dates.split(",") if args.dates else [n["night"] for n in sorted(h.nights, key=lambda n: -n["score"])[: args.top]]
    modes = args.modes.split(",")
    res = run_bakeoff(args.data, dates, modes, args.models.split(",") if args.models else MODELS)
    res["local"] = local_reference(args.data, dates, modes)
    Path(args.data, "bakeoff.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res["local"]))


def cmd_fieldwork(args):
    from .fieldwork import field_trip
    from .voice import load_env

    load_env(args.env)
    out_dir = Path(args.data)
    out_dir.mkdir(parents=True, exist_ok=True)
    res = field_trip(args.url, screenshot_path=str(out_dir / "fieldwork.png"))
    (out_dir / "fieldwork.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print({k: res.get(k) for k in ("status", "title", "cold_warning", "excerpt")})


def cmd_season(args):
    from .season import season_report
    from .voice import load_env

    load_env(args.env)
    res = season_report(args.data)
    Path(args.data, "season_report.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(res["title"], f"{len(res['findings'])} findings, {res['dropped']} dropped, cost ${res['cost_usd']}")


def cmd_atlas(args):
    from . import atlas_memory
    from .voice import load_env

    load_env(args.env)
    out = {"sync": atlas_memory.sync(args.data)}
    out["examples"] = {d: atlas_memory.seen_before(d) for d in args.nights.split(",")}
    Path(args.data, "atlas_memory.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, default=str)[:600])


def cmd_tiger(args):
    from . import tiger_store
    from .voice import load_env

    load_env(args.env)
    out = {"load": tiger_store.load(load_house(args), args.data)}
    out["coldest_living_room_nights"] = tiger_store.coldest_nights("T2", 5)
    out["searches"] = {q: tiger_store.search_stories(q, 3) for q in args.queries.split("|")}
    Path(args.data, "tiger_store.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out, default=str)[:600])


def cmd_ouija(args):
    from .agent import Haunting
    from .narrator import OllamaChat
    from .ouija import save, spirit_message

    h = Haunting(args.data)
    chat = None if args.template else OllamaChat(args.model)
    nights = [n["night"] for n in sorted(h.nights, key=lambda n: -n["score"]) if n["n_events"]][: args.top]
    for d in nights:
        msg = spirit_message(h.night(d), chat=chat)
        save(d, msg, args.data)
        print(f"{d}: {msg['archetype']} spells {msg['message']!r} ({msg['by']})", flush=True)


def cmd_worker(args):
    import asyncio

    from .durable import run_worker

    asyncio.run(run_worker(args.address))


def cmd_watch(args):
    import asyncio

    from .durable import start_watch

    job = {"data_dir": args.data, "modes": args.modes.split(","), "model": args.model}
    res = asyncio.run(start_watch(args.nights.split(","), job, args.address, wait=not args.no_wait))
    print(json.dumps(res, indent=1))


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
    sp.add_argument("--max-context", type=int, default=1000)
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
    sp.add_argument("--modes", default="medium,skeptic,family")
    sp.add_argument("--cold", type=int, default=4, help="also narrate the N nights with the most cold-room checks")
    sp.add_argument("--shard", help="i/n: narrate every n-th of the chosen nights (parallel jobs)")
    sp.add_argument("--no-index", action="store_true")
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
    sp.add_argument("--max-context", type=int, default=1000)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--out", default="demo_data/eval.json")
    sp.set_defaults(fn=cmd_evaluate)

    sp = sub.add_parser("voice", help="read the verified stories out loud with ElevenLabs")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--dates")
    sp.add_argument("--top", type=int, default=8)
    sp.add_argument("--modes", default="family,medium")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_voice)

    sp = sub.add_parser("tonight", help="live forecast (SerpApi) + TabPFN guess of each room tonight")
    house_args(sp)
    sp.add_argument("--place", default="Stambruges, Belgium")
    sp.add_argument("--backend", default="tabpfn")
    sp.add_argument("--out", default="demo_data/tonight.json")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_tonight)

    sp = sub.add_parser("bakeoff", help="grounding bake-off of open models through Backboard")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--dates")
    sp.add_argument("--top", type=int, default=6)
    sp.add_argument("--modes", default="medium,family")
    sp.add_argument("--models", help="comma separated OpenRouter model ids")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_bakeoff)

    sp = sub.add_parser("fieldwork", help="Dr. Bigotes checks official warnings in a Browserbase browser")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--url", default="https://meteoalarm.org/en/live/region/BE")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_fieldwork)

    sp = sub.add_parser("season", help="Ultramarine reads every case file and writes the season report")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_season)

    sp = sub.add_parser("atlas", help="case files + embeddings into MongoDB Atlas, vector search examples")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--nights", default="2016-04-19,2016-03-09")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_atlas)

    sp = sub.add_parser("tiger", help="readings hypertable + hybrid story search on Tiger Data")
    house_args(sp)
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--queries", default="the bathroom air at night|machines waking before dawn|a cold living room")
    sp.add_argument("--env", default=".env")
    sp.set_defaults(fn=cmd_tiger)

    sp = sub.add_parser("ouija", help="Luna's spirit board: a short spelled message per haunted night")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--top", type=int, default=25)
    sp.add_argument("--model", default=None)
    sp.add_argument("--template", action="store_true")
    sp.set_defaults(fn=cmd_ouija)

    sp = sub.add_parser("worker", help="run a Temporal worker for the night watch")
    sp.add_argument("--address", default="localhost:7233")
    sp.set_defaults(fn=cmd_worker)

    sp = sub.add_parser("watch", help="start one durable Temporal workflow per night")
    sp.add_argument("--nights", required=True, help="comma separated YYYY-MM-DD")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--modes", default="family,medium")
    sp.add_argument("--model", default=None)
    sp.add_argument("--address", default="localhost:7233")
    sp.add_argument("--no-wait", action="store_true")
    sp.set_defaults(fn=cmd_watch)

    sp = sub.add_parser("serve", help="open the web app")
    sp.add_argument("--data", default="demo_data")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000)
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    if getattr(args, "model", "x") is None:
        from .narrator import DEFAULT_MODEL

        args.model = DEFAULT_MODEL
    from . import tracing

    tracing.init()
    try:
        args.fn(args)
    finally:
        tracing.flush()


if __name__ == "__main__":
    main()
