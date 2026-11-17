"""Process-local session cache.

Chat state is kept in memory for the current process, with TTL eviction and a
bounded number of sessions. Replace this module with a shared cache when running
multiple worker processes.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

DEFAULT_TTL_SECONDS = 60 * 60 * 6
MAX_SESSIONS = 500
MAX_MESSAGES_PER_SESSION = 200


class _SessionStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._expiry: dict[str, float] = {}

    # -------------------------------------------------------------- helpers
    def _evict_expired(self) -> None:
        now = time.time()
        expired = [sid for sid, ts in self._expiry.items() if ts < now]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._expiry.pop(sid, None)

        while len(self._sessions) > MAX_SESSIONS:
            sid, _ = self._sessions.popitem(last=False)
            self._expiry.pop(sid, None)

    def _session(self, session_id: str, create: bool = True) -> dict[str, Any] | None:
        self._evict_expired()
        session = self._sessions.get(session_id)
        if session is None and create:
            session = {"messages": [], "items": {}}
            self._sessions[session_id] = session
        if session is not None:
            self._sessions.move_to_end(session_id)
            self._expiry[session_id] = time.time() + DEFAULT_TTL_SECONDS
        return session

    # ------------------------------------------------------------ messages
    def append_message(self, session_id: str, message: dict[str, Any]) -> None:
        with self._lock:
            session = self._session(session_id)
            messages: list[dict[str, Any]] = session["messages"]
            messages.append(message)
            if len(messages) > MAX_MESSAGES_PER_SESSION:
                del messages[: len(messages) - MAX_MESSAGES_PER_SESSION]

    def read_messages(self, session_id: str, drain: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            session = self._session(session_id, create=drain)
            if session is None:
                return []
            messages = list(session["messages"])
            if drain:
                session["messages"] = []
            return messages

    # --------------------------------------------------------------- items
    def set_item(self, session_id: str, key: str, value: str) -> None:
        with self._lock:
            session = self._session(session_id)
            session["items"][key] = value

    def pop_item(self, session_id: str, key: str) -> str | None:
        with self._lock:
            session = self._session(session_id, create=False)
            if session is None:
                return None
            return session["items"].pop(key, None)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)
            self._expiry.pop(session_id, None)


STORE = _SessionStore()