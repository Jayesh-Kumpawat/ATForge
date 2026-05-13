"""Shared fixtures for API tests."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atforge.api.app import create_app
from atforge.api.deps import get_db
from atforge.storage.db import init_db


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = tmp_path / "atforge_test.db"
    init_db(path)
    return str(path)


@pytest.fixture
def client(db_path: str, monkeypatch):
    """FastAPI TestClient with DB dep overridden to use test db_path."""
    monkeypatch.setenv("ATFORGE_DB_PATH", db_path)
    app = create_app()

    def _override_get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = _override_get_db
    return TestClient(app)
