
from ognex.cache.main import STORE


def insert_item_into_cache(chat_session_id: str, key: str, value: str) -> None:
    STORE.set_item(chat_session_id, key, value)


def get_and_clear_item_from_cache(chat_session_id: str, key: str) -> str | None:
    return STORE.pop_item(chat_session_id, key)