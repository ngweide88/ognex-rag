import time

from ognex.database.main import _table, db_cursor, ensure_db_ready

TASK_STATUS_PENDING = 0
TASK_STATUS_COMPLETED = 1
TASK_STATUS_FAILED = -1

TASK_STATUS_ENUM_TO_TEXT = {
    TASK_STATUS_PENDING: "Pending",
    TASK_STATUS_COMPLETED: "Completed",
    TASK_STATUS_FAILED: "Failed",
}


def insert_task(task_id: str, kb_name: str, task_status: int, status_desc: str) -> None:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO {_table('task')} (task_id, kb_name, timestamp, status, status_text) "
            f"VALUES (?, ?, ?, ?, ?)",
            (task_id, kb_name, int(time.time()), task_status, status_desc),
        )


def update_task(task_id: str, task_status: int, status_desc: str) -> None:
    ensure_db_ready()
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE {_table('task')} SET status=?, status_text=? WHERE task_id=?",
            (task_status, status_desc, task_id),
        )


def list_tasks() -> list[dict]:
    ensure_db_ready()
    with db_cursor() as cur:
        cur.execute(
            f"SELECT task_id, kb_name, timestamp, status, status_text "
            f"FROM {_table('task')} ORDER BY timestamp DESC LIMIT 50"
        )
        records = cur.fetchall()

    return [
        {
            "task_id": record["task_id"],
            "kb_name": record["kb_name"],
            "timestamp": record["timestamp"],
            "status": TASK_STATUS_ENUM_TO_TEXT.get(record["status"], "Unknown"),
            "status_text": record["status_text"],
        }
        for record in records
    ]