"""The night watch as a Temporal workflow.

A watch that misses a night is worse than no watch. Each night is one workflow:
scan with TabPFN, then one narration per mode with Gemma. Activities are
idempotent (a finished scan or story on disk is reused), so a retry or a
restarted worker picks up exactly where the last one stopped. If Ollama is down,
the narration activity fails and Temporal retries it with backoff until it is back.
"""
from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "night-watch"


@dataclass
class NightJob:
    night: str
    data_dir: str = "demo_data"
    modes: list[str] = field(default_factory=lambda: ["family", "medium"])
    model: str = "gemma4:e4b"
    source_path: str = ""


_house_cache: dict = {}


def _house(source_path: str):
    from .data import fetch_uci, load_uci

    key = source_path or "uci"
    if key not in _house_cache:
        _house_cache[key] = load_uci(source_path or fetch_uci("data/raw"))
    return _house_cache[key]


@activity.defn
def scan_activity(job: NightJob) -> dict:
    from datetime import date

    from .scanner import TabPFNBackend, scan_night
    from .store import save_scan

    out = Path(job.data_dir) / "nights" / f"{job.night}.json"
    if out.exists():
        d = json.loads(out.read_text(encoding="utf-8"))
        return {"night": job.night, "reused": True, "events": d["n_events"], "score": d["score"]}
    scan = scan_night(_house(job.source_path), date.fromisoformat(job.night), TabPFNBackend(),
                      on_sensor=lambda sid: activity.heartbeat(sid))
    save_scan(scan, job.data_dir)
    return {"night": job.night, "reused": False, "events": len(scan.events), "score": round(scan.score, 1)}


@activity.defn
def narrate_activity(job: NightJob, mode: str) -> dict:
    from .agent import Haunting
    from .narrator import OllamaChat, narrate
    from .store import save_story

    out = Path(job.data_dir) / "stories" / f"{job.night}.{mode}.json"
    if out.exists():
        d = json.loads(out.read_text(encoding="utf-8"))
        return {"mode": mode, "reused": True, "verified": d["verified"]}
    chat = OllamaChat(job.model)
    if not chat.available():
        # Temporal records this failure and retries with backoff.
        raise RuntimeError(f"Ollama model {job.model} is not answering (attempt {activity.info().attempt})")
    story = narrate(Haunting(job.data_dir).night(job.night), mode, chat=chat)
    save_story(story, job.data_dir)
    return {"mode": mode, "reused": False, "verified": len(story.sentences), "dropped": len(story.rejected)}


@workflow.defn
class NightWatch:
    @workflow.run
    async def run(self, job: NightJob) -> dict:
        scan = await workflow.execute_activity(
            scan_activity, job,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(seconds=90),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        stories = []
        for mode in job.modes:
            stories.append(await workflow.execute_activity(
                narrate_activity, args=[job, mode],
                start_to_close_timeout=timedelta(minutes=15),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=5), backoff_coefficient=2.0,
                                         maximum_interval=timedelta(seconds=60), maximum_attempts=20),
            ))
        return {"night": job.night, "scan": scan, "stories": stories}


async def run_worker(address: str = "localhost:7233") -> None:
    from temporalio.client import Client
    from temporalio.worker import Worker

    client = await Client.connect(address)
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=[NightWatch],
                    activities=[scan_activity, narrate_activity], activity_executor=ThreadPoolExecutor(4))
    await worker.run()


async def start_watch(nights: list[str], job_kw: dict, address: str = "localhost:7233", wait: bool = True) -> list:
    from temporalio.client import Client

    client = await Client.connect(address)
    handles = []
    for n in nights:
        handles.append(await client.start_workflow(
            NightWatch.run, NightJob(night=n, **job_kw), id=f"night-watch-{n}", task_queue=TASK_QUEUE))
    if not wait:
        return [h.id for h in handles]
    return await asyncio.gather(*(h.result() for h in handles))
