from __future__ import annotations

from atforge.llm.tracing import trace_completion
from atforge.llm.types import LlmRequest, LlmResponse


def _resp(provider: str = "gemini") -> LlmResponse:
    return LlmResponse(
        text="hi",
        model="m",
        provider=provider,
        input_tokens=3,
        output_tokens=5,
        latency_ms=10,
    )


def test_disabled_tracing_returns_noop_recorder_without_calling_langfuse() -> None:
    """When `enabled=False`, trace_completion must not import or call langfuse.get_client.
    The recorder yielded should accept record_response() without error.
    """
    req = LlmRequest(prompt="hi", trace_name="t")
    with trace_completion(req, "gemini", enabled=False) as rec:
        # Should not raise even though no Langfuse client is configured.
        rec.record_response(_resp())
    # No assertions on Langfuse — disabled means fully noop.


def test_disabled_tracing_yields_recorder_with_record_response() -> None:
    req = LlmRequest(prompt="hi")
    with trace_completion(req, "gemini", enabled=False) as rec:
        assert hasattr(rec, "record_response")
        rec.record_response(_resp())


def test_enabled_tracing_uses_provided_client(monkeypatch) -> None:
    """When enabled with an explicit client, observation methods are exercised."""
    calls: dict = {"start": [], "update": []}

    class _FakeObservation:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, **kwargs):
            calls["update"].append(kwargs)

    class _FakeLangfuseClient:
        def start_as_current_observation(self, **kwargs):
            calls["start"].append(kwargs)
            return _FakeObservation()

    req = LlmRequest(prompt="hi", trace_name="my-call", model="gemini-x", metadata={"foo": "bar"})
    with trace_completion(req, "gemini", enabled=True, client=_FakeLangfuseClient()) as rec:
        rec.record_response(_resp("gemini"))

    assert len(calls["start"]) == 1
    start = calls["start"][0]
    assert start["name"] == "my-call"
    assert start["as_type"] == "generation"
    assert start["model"] == "gemini-x"
    assert start["input"] == "hi"
    assert start["metadata"]["provider"] == "gemini"
    assert start["metadata"]["foo"] == "bar"

    assert len(calls["update"]) == 1
    update = calls["update"][0]
    assert update["output"] == "hi"
    assert update["usage_details"]["input"] == 3
    assert update["usage_details"]["output"] == 5
