"""Pipeline timing instrumentation.

Each LangGraph node is wrapped with ``time_node``; durations are buffered and
written as one CSV row per query when the final node completes.
"""

from __future__ import annotations

import csv
import logging
import threading
import time
from datetime import datetime
from functools import wraps

from ognex.config import settings

logger = logging.getLogger(__name__)

NODE_ORDER = [
    "guardrail",
    "sentence_structure_editor",
    "retrieve_context",
    "process_reference",
    "construct_prompt",
    "generate_response",
    "generate_title",
]

_BUFFER: dict[str, float] = {}
_LOCK = threading.Lock()


def _flush() -> None:
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        path = settings.log_dir / "node_timings.csv"
        is_new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            if is_new:
                writer.writerow(["Timestamp", "session"] + NODE_ORDER)
            row = [datetime.now().isoformat(timespec="seconds"), _BUFFER.pop("session", "-")]
            row += [f"{_BUFFER.get(name, 0.0):.4f}" for name in NODE_ORDER]
            writer.writerow(row)
    except OSError:
        logger.exception("Could not write node timing log")
    finally:
        _BUFFER.clear()


def time_node(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        name = func.__name__
        started = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration = time.perf_counter() - started
            with _LOCK:
                _BUFFER[name] = duration
                if name == NODE_ORDER[-1] and _BUFFER:
                    _flush()
            logger.debug("%s finished in %.4fs", name, duration)

    return wrapper