"""Optional Sentry agent tracing. Off unless SENTRY_DSN is set.

Spans follow Sentry's gen_ai conventions (invoke_agent, chat, execute_tool) so
they show up in Sentry's AI Agents view with model, token counts and latency.
Privacy rule: spans carry metadata only (model, tokens, tool names, validator
counts). Prompts, sensor readings and story text are never sent.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

_enabled = False


def init() -> bool:
    global _enabled
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn or _enabled:
        return _enabled
    try:
        import sentry_sdk
    except ImportError:
        return False
    sentry_sdk.init(dsn=dsn, traces_sample_rate=1.0, send_default_pii=False,
                    environment=os.environ.get("WH_ENV", "local"), release=os.environ.get("GITHUB_SHA", "")[:7] or None)
    _enabled = True
    return True


def enabled() -> bool:
    return _enabled


@contextmanager
def span(op: str, name: str, **data):
    if not _enabled:
        yield None
        return
    import sentry_sdk

    with sentry_sdk.start_span(op=op, name=name) as s:
        for k, v in data.items():
            s.set_data(k, v)
        yield s


@contextmanager
def agent_transaction(name: str, **data):
    """Root span for one agent run or one narration."""
    if not _enabled:
        yield None
        return
    import sentry_sdk

    with sentry_sdk.start_transaction(op="gen_ai.invoke_agent", name=name) as t:
        t.set_data("gen_ai.operation.name", "invoke_agent")
        t.set_data("gen_ai.agent.name", "Witching Hour")
        for k, v in data.items():
            t.set_data(k, v)
        yield t


def set_data(s, **data) -> None:
    if s is not None:
        for k, v in data.items():
            s.set_data(k, v)


def flush() -> None:
    if _enabled:
        import sentry_sdk

        sentry_sdk.flush(timeout=10)
