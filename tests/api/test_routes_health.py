"""Health route smoke test."""
from __future__ import annotations


def test_health_returns_ok(client) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_openapi_schema_renders(client) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["openapi"].startswith("3.")
    assert "/health" in schema["paths"]
