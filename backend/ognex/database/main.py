"""SQLite persistence layer.

Repository functions run against a single SQLite file (``data/ognex.db``). The
app is single-tenant: there are no users, roles or per-account records.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ognex.config import settings

_SCHEMA_INITIALISED = False


def _db_path() -> Path:
    settings.ensure_directories()
    return settings.data_dir / "ognex.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db_cursor(commit: bool = False) -> Iterator[sqlite3.Cursor]:
    """Short-lived connection per operation (safe across request threads)."""
    conn = _connect()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table(name: str) -> str:
    return f"{settings.table_prefix}_{name}"


def init_db() -> None:
    """Create tables if needed."""
    global _SCHEMA_INITIALISED

    with db_cursor(commit=True) as cur:
        cur.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS {_table('chat_history')} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                data TEXT NOT NULL,
                name TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_{_table('chat_history')}_ts
                ON {_table('chat_history')} (timestamp DESC);

            CREATE TABLE IF NOT EXISTS {_table('task')} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT UNIQUE NOT NULL,
                kb_name TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                status INTEGER NOT NULL,
                status_text TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_{_table('task')}_ts
                ON {_table('task')} (timestamp DESC);
            """
        )

    _SCHEMA_INITIALISED = True


def ensure_db_ready() -> None:
    if not _SCHEMA_INITIALISED:
        init_db()