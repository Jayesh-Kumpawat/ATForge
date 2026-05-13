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


# ─── trace_node: tags support ────────────────────────────────────────────────


def _make_fake_client() -> tuple[dict, object]:
    """Returns (calls_record, fake_client) for trace_node tests."""
    calls: dict = {"start": [], "update": [], "score": []}

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

        def score_current_span(self, **kwargs):
            calls["score"].append(kwargs)

    return calls, _FakeLangfuseClient()


def test_trace_node_passes_tags_to_langfuse_client() -> None:
    """tags list forwarded to obs.update (not start_as_current_observation — Langfuse 4.x rejects it there)."""
    from atforge.llm.tracing import trace_node

    calls, client = _make_fake_client()
    with trace_node("critic_node", enabled=True, client=client, tags=["critic", "phase9"]):
        pass

    assert len(calls["start"]) == 1
    assert "tags" not in calls["start"][0]
    assert len(calls["update"]) == 1
    assert calls["update"][0].get("tags") == ["critic", "phase9"]


def test_trace_node_without_tags_omits_tags_key() -> None:
    """When tags=None (default), 'tags' key absent from both start and update."""
    from atforge.llm.tracing import trace_node

    calls, client = _make_fake_client()
    with trace_node("explorer_node", enabled=True, client=client):
        pass

    assert len(calls["start"]) == 1
    assert "tags" not in calls["start"][0]
    assert len(calls["update"]) == 1
    assert "tags" not in calls["update"][0]


def test_trace_node_disabled_tags_never_reach_client() -> None:
    """When disabled, Langfuse client never called regardless of tags."""
    from atforge.llm.tracing import trace_node

    calls, client = _make_fake_client()
    with trace_node("any_node", enabled=False, client=client, tags=["explorer"]):
        pass

    assert calls["start"] == []


# ─── score_current_observation ───────────────────────────────────────────────


def test_score_current_observation_calls_langfuse_score() -> None:
    """score_current_observation delegates to client.score_current_observation."""
    from atforge.llm.tracing import score_current_observation

    calls, client = _make_fake_client()
    score_current_observation("veto_rate", 0.75, enabled=True, client=client)

    assert len(calls["score"]) == 1
    assert calls["score"][0]["name"] == "veto_rate"
    assert calls["score"][0]["value"] == 0.75


def test_score_current_observation_disabled_is_noop() -> None:
    """When disabled, score_current_observation does nothing."""
    from atforge.llm.tracing import score_current_observation

    calls, client = _make_fake_client()
    score_current_observation("veto_rate", 1.0, enabled=False, client=client)

    assert calls["score"] == []


def test_score_current_observation_passes_comment() -> None:
    """Optional comment kwarg forwarded to Langfuse."""
    from atforge.llm.tracing import score_current_observation

    calls, client = _make_fake_client()
    score_current_observation(
        "critic_veto", 1.0, enabled=True, client=client, comment="veto: tried before"
    )

    assert calls["score"][0].get("comment") == "veto: tried before"
