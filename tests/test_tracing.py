from witching_hour import tracing


def test_tracing_is_a_no_op_without_a_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert tracing.init() is False
    with tracing.agent_transaction("invoke_agent test") as t, tracing.span("gen_ai.chat", "chat m", x=1) as s:
        assert t is None and s is None
        tracing.set_data(s, y=2)  # must not fail
    tracing.flush()
