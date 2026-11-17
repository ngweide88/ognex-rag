"""Background ingestion tasks.

Ingestion runs on a bounded thread pool: the API returns immediately with a task
id, progress is persisted in SQLite, and the knowledge-base page polls for
status.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from ognex.database.tasks import (
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    insert_task,
    update_task,
)
from ognex.dataprep.main import create_knowledge_base

logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ingest")


def _run(task_id: str, knowledge_base_name: str, filepath: str) -> None:
    try:
        create_knowledge_base(
            knowledge_base_name,
            filepath,
            {"task_id": task_id},
        )
        update_task(task_id, TASK_STATUS_COMPLETED, "Success")
    except Exception as exc:
        logger.exception("Knowledge-base ingestion failed for %s", knowledge_base_name)
        update_task(task_id, TASK_STATUS_FAILED, f"{type(exc).__name__}: {exc}"[:400])


def submit_knowledge_base_task(knowledge_base_name: str, filepath: str) -> str:
    task_id = uuid.uuid4().hex
    insert_task(task_id, knowledge_base_name, TASK_STATUS_PENDING, "Queued")
    _EXECUTOR.submit(_run, task_id, knowledge_base_name, filepath)
    return task_id