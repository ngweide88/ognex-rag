import json
import time
from typing import Any

from ognex.database.main import _table, db_cursor, ensure_db_ready


def insert_chat_history(chat_messages: list[dict[str, Any]], title: str | None) -> int:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO {_table('chat_history')} (timestamp, data, name) VALUES (?, ?, ?)",
            (int(time.time()), json.dumps(chat_messages), title),
        )
        return int(cur.lastrowid)


def update_chat_history(
    chat_id: int, chat_messages: list[dict[str, Any]], title: str | None
) -> bool:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"SELECT data FROM {_table('chat_history')} WHERE id=?",
            (chat_id,),
        )
        record = cur.fetchone()
        if record is None:
            return False

        previous = json.loads(record["data"]) if record["data"] else []
        cur.execute(
            f"UPDATE {_table('chat_history')} SET timestamp=?, data=?, name=COALESCE(?, name) WHERE id=?",
            (int(time.time()), json.dumps(previous + chat_messages), title, chat_id),
        )
        return True


def replace_chat_history(chat_id: int, chat_messages: list[dict[str, Any]]) -> bool:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE {_table('chat_history')} SET timestamp=?, data=? WHERE id=?",
            (int(time.time()), json.dumps(chat_messages), chat_id),
        )
        return cur.rowcount > 0


def delete_chat_history(chat_id: int) -> bool:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(f"DELETE FROM {_table('chat_history')} WHERE id=?", (chat_id,))
        return cur.rowcount > 0


def rename_chat_history(chat_name: str, chat_id: int) -> bool:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE {_table('chat_history')} SET name=? WHERE id=?",
            (chat_name, chat_id),
        )
        return cur.rowcount > 0


def list_chat_history_within_last_month() -> list[dict[str, Any]]:
    ensure_db_ready()
    with db_cursor() as cur:
        cur.execute(
            f"SELECT id, timestamp, name FROM {_table('chat_history')} "
            f"ORDER BY timestamp DESC LIMIT 50"
        )
        records = cur.fetchall()

    now = int(time.time())
    arranged = [
        {"category": "Past 24 hours", "chats": []},
        {"category": "Past week", "chats": []},
        {"category": "Past month", "chats": []},
    ]

    for record in records:
        age = now - record["timestamp"]
        if age < 24 * 3600:
            bucket = 0
        elif age < 7 * 24 * 3600:
            bucket = 1
        elif age < 30 * 24 * 3600:
            bucket = 2
        else:
            continue

        arranged[bucket]["chats"].append(
            {"id": record["id"], "title": record["name"] or f"Chat #{record['id']}"}
        )

    return arranged


def get_chat_history(chat_id: int) -> dict[str, Any] | None:
    ensure_db_ready()
    with db_cursor() as cur:
        cur.execute(
            f"SELECT id, data FROM {_table('chat_history')} WHERE id=?",
            (chat_id,),
        )
        record = cur.fetchone()

    if record is None:
        return None
    return {
        "id": record["id"],
        "content": json.loads(record["data"]) if record["data"] else [],
    }