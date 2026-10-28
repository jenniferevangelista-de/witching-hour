"""Which open model answers live.

At home: Gemma 4 through Ollama. On the public demo (no GPU): Gemma 3 27B served
by a provider through one Backboard API key. Without either: the deterministic
template spirits, clearly labelled as such.
"""
from __future__ import annotations

import os

PUBLIC_GEMMA = os.environ.get("WH_PUBLIC_MODEL", "google/gemma-3-27b-it")


def make_chat():
    from .bakeoff import BackboardChat
    from .narrator import DEFAULT_MODEL, OllamaChat

    pref = os.environ.get("WH_LLM", "auto").lower()
    if pref in ("auto", "ollama"):
        chat = OllamaChat(os.environ.get("WH_MODEL", DEFAULT_MODEL), timeout=180)
        if chat.available():
            return chat
        if pref == "ollama":
            return None
    if pref in ("auto", "backboard") and os.environ.get("BACKBOARD_API_KEY"):
        return BackboardChat(PUBLIC_GEMMA, timeout=60)
    return None


def describe(chat) -> str:
    if chat is None:
        return "template spirits (no model attached)"
    return f"{chat.model} ({'Ollama, local' if chat.__class__.__name__ == 'OllamaChat' else 'via Backboard'})"
