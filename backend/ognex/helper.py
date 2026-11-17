"""Small utilities shared across the backend."""

from __future__ import annotations

import csv
import gzip
import os
import pickle
import re
from datetime import datetime

from bs4 import BeautifulSoup

from ognex.config import settings

_SAFE_KB_NAME = re.compile(r"[^a-z0-9_-]+")


def remove_html_tags(text: str) -> str:
    return BeautifulSoup(text, "html.parser").get_text()


def save_to_pickle(path, data) -> None:
    path = os.fspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with gzip.open(path, "wb") as file:
        pickle.dump(data, file)


def load_from_pickle(path):
    with gzip.open(os.fspath(path), "rb") as file:
        return pickle.load(file)


def sanitise_knowledge_base_name(name: str) -> str:
    """Turn an uploaded filename into a safe, stable knowledge-base id.

    The result is used for file paths and as a primary-ish key, so it is
    restricted to ``[a-z0-9_-]``. Raises ``ValueError`` when nothing usable
    remains.
    """
    base = os.path.basename(name).rsplit(".", 1)[0].lower().strip()
    base = base.replace(" ", "_")
    base = _SAFE_KB_NAME.sub("", base).strip("_-")
    if not base:
        raise ValueError("Filename does not contain any usable characters")
    if len(base) > 120:
        base = base[:120]
    return base


def log_query(kb_names, prompt: str) -> None:
    """Append one query to a CSV log (best effort, never raises)."""
    try:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_path = settings.log_dir / "queries.csv"
        file_exists = file_path.exists()
        with file_path.open("a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow(["Timestamp", "KB Names", "Query"])
            writer.writerow(
                [
                    datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                    ",".join(kb_names or []),
                    prompt,
                ]
            )
    except OSError:
        # Logging must never break the chat request.
        pass


def merge_pages(pages) -> list[tuple[int, int]]:
    """Merge sorted page numbers into contiguous ranges: [1,2,3,7] -> [(1,3),(7,7)]."""
    pages = sorted(set(pages))
    if not pages:
        return []
    merged = []
    start = end = pages[0]
    for page in pages[1:]:
        if page == end + 1:
            end = page
        else:
            merged.append((start, end))
            start = end = page
    merged.append((start, end))
    return merged