from typing import Any

from ognex.cache.main import STORE


def insert_history_into_cache(chat_session_id: str, chat_message: dict[str, Any]) -> None:
    STORE.append_message(chat_session_id, chat_message)


def list_history_cache(chat_session_id: str, should_empty: bool) -> list[dict[str, Any]]:
    return STORE.read_messages(chat_session_id, drain=should_empty)

def clear_history_cache(chat_session_id: str) -> None:
    STORE.clear(chat_session_id)
