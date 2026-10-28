"""Which open model makes things up the least? A bake-off through Backboard.

Same nights, same prompts, same validator. Each open-weight model is reached
through one Backboard API key (OpenRouter provider), one shot per story, no
retry, so the score is the model's own grounding: the share of sentences whose
numbers match the events they cite.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .agent import Haunting
from .narrator import narrate

API = "https://app.backboard.io/api/threads/messages"
MODELS = [
    "google/gemma-3-27b-it",
    "meta-llama/llama-3.3-70b-instruct",
    "qwen/qwen-2.5-72b-instruct",
    "mistralai/mistral-small-3.1-24b-instruct",
]


class BackboardConfigError(RuntimeError):
    """Key, credit or request problem: stop the whole bake-off instead of scoring zeros."""


class BackboardChat:
    """Same call shape as OllamaChat, but through Backboard."""

    def __init__(self, model: str, api_key: str | None = None, timeout: int = 180):
        self.model = model
        self.key = api_key or os.environ.get("BACKBOARD_API_KEY", "").strip()
        self.timeout = timeout
        self.seconds = 0.0
        if not self.key:
            raise RuntimeError("BACKBOARD_API_KEY is not set")

    def __call__(self, messages: list[dict], schema: dict | None = None, temperature: float = 0.5) -> str:
        import requests

        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [m for m in messages if m["role"] != "system"]
        content = "\n\n".join(f"[{m['role']}]\n{m['content']}" if len(turns) > 1 else m["content"] for m in turns)
        if schema is not None:
            content += "\n\nReturn ONLY a JSON object matching this JSON schema:\n" + json.dumps(schema, separators=(",", ":"))
        body = {"content": content, "system_prompt": system, "llm_provider": "openrouter", "model_name": self.model,
                "json_output": True, "memory": "off", "web_search": "off", "stream": False}
        t0 = time.perf_counter()
        for attempt in range(3):
            r = requests.post(API, headers={"X-API-Key": self.key}, json=body, timeout=self.timeout)
            if r.status_code in (408, 425, 429) or r.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code >= 400:
                raise BackboardConfigError(f"Backboard HTTP {r.status_code} for {self.model}")  # never print the body
            data = r.json()
            self.seconds += time.perf_counter() - t0
            return str(data.get("content") or "")
        raise RuntimeError(f"Backboard kept failing for {self.model}")


def run_bakeoff(data_dir: str | Path, dates: list[str], modes: list[str], models: list[str]) -> dict:
    h = Haunting(data_dir)
    results = []
    for model in models:
        chat = BackboardChat(model)
        verified = dropped = stories = clean = failed = 0
        for d in dates:
            scan = h.night(d)
            for mode in modes:
                try:
                    st = narrate(scan, mode, chat=chat, retries=0)
                except BackboardConfigError:
                    raise
                except Exception as e:  # a model that cannot answer in JSON scores zero for that story
                    failed += 1
                    print(f"  {model} {d} {mode}: {type(e).__name__}", flush=True)
                    continue
                stories += 1
                verified += len(st.sentences)
                dropped += len(st.rejected)
                clean += int(not st.rejected and len(st.sentences) > 0)
        total = verified + dropped
        row = {"model": model, "via": "Backboard (openrouter)", "stories": stories, "failed": failed,
               "sentences": total, "verified": verified,
               "grounded_share": round(verified / total, 3) if total else 0.0,
               "clean_stories": clean, "avg_seconds": round(chat.seconds / max(stories, 1), 1)}
        print(json.dumps(row), flush=True)
        results.append(row)
    return {"nights": dates, "modes": modes, "one_shot": True, "results": results}


def local_reference(data_dir: str | Path, dates: list[str], modes: list[str]) -> dict:
    """The stories already written by the local model, scored the same way (after its one retry)."""
    h = Haunting(data_dir)
    verified = dropped = stories = 0
    model = ""
    for d in dates:
        for m in modes:
            s = h.story(d, m)
            if s:
                stories += 1
                verified += s["verified"]
                dropped += s["dropped"]
                model = s["model"]
    total = verified + dropped
    return {"model": model, "via": "Ollama, local (with one retry)", "stories": stories, "sentences": total,
            "verified": verified, "grounded_share": round(verified / total, 3) if total else 0.0}
