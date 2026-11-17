"""Split parent chunks into the three child-chunk granularities."""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ognex.config import settings
from ognex.dataprep.common.text import normalize_text
from ognex.helper import remove_html_tags


def split_children(parent_chunks: list[str], child_chunk_size: int) -> list[list[str]]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=child_chunk_size,
        chunk_overlap=round(child_chunk_size * settings.child_chunk_overlap_ratio),
        length_function=len,
        add_start_index=True,
    )

    return [
        splitter.split_text(remove_html_tags(normalize_text(parent)))
        for parent in parent_chunks
    ]