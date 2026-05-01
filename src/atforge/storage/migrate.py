from __future__ import annotations

import re
import sqlite3
from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_FILE_RE = re.compile(r"^(\d{4})_.*\.sql$")


def _list_migrations() -> list[tuple[int, Path]]:
    if not _MIGRATIONS_DIR.is_dir():
        return []
    out: list[tuple[int, Path]] = []
    for f in sorted(_MIGRATIONS_DIR.iterdir()):
        m = _MIGRATION_FILE_RE.match(f.name)
        if m:
            out.append((int(m.group(1)), f))
    return out


def _user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending `.sql` migrations in order, gated by `PRAGMA user_version`.

    Each migration filename is `NNNN_<name>.sql` where NNNN is the target version.
    A migration with target <= current version is skipped. The migration file is
    expected to set `PRAGMA user_version = NNNN` itself; we double-check after.
    """
    current = _user_version(conn)
    for target, path in _list_migrations():
        if target <= current:
            continue
        conn.executescript(path.read_text())
        post = _user_version(conn)
        if post < target:
            conn.execute(f"PRAGMA user_version = {target}")
        current = max(current, target)
    return _user_version(conn)
