"""FastAPI dependency providers."""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator


def _resolve_db_path() -> str:
    return os.environ.get("ATFORGE_DB_PATH", "data/atforge.db")


def get_db() -> Iterator[sqlite3.Connection]:
    """Yield a SQLite connection per request, closed after response."""
    conn = sqlite3.connect(_resolve_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
