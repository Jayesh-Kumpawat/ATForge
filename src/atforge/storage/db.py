from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _configure_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row


def init_db(db_path: Path | str) -> None:
    """Create tables on a fresh DB (idempotent)."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ddl = _SCHEMA_PATH.read_text()
    with sqlite3.connect(db_path) as conn:
        _configure_connection(conn)
        conn.executescript(ddl)
        conn.commit()


@contextmanager
def connect(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    db_path = Path(db_path)
    conn = sqlite3.connect(
        db_path, isolation_level=None
    )  # autocommit-friendly; use txn() explicitly
    _configure_connection(conn)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def txn(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Explicit transaction boundary. `with txn(conn): ...`."""
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")
