"""Parent-chunk construction (cached per knowledge base)."""

from __future__ import annotations

import os

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ognex.config import settings
from ognex.dataprep.common.chunker import iterative_chunk_recombination
from ognex.helper import load_from_pickle, save_to_pickle


def build_parent_chunks(combined_text: str, knowledge_base_name: str) -> list[str]:
    cache_path = os.path.join(settings.pickle_dir, f"{knowledge_base_name}_parent_chunks.pkl.gz")
    if os.path.exists(cache_path):
        return load_from_pickle(cache_path)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.parent_chunk_size,
        chunk_overlap=settings.parent_chunk_overlap,
    )
    chunks = [doc.page_content for doc in splitter.create_documents([combined_text])]
    chunks = iterative_chunk_recombination(chunks, settings.min_parent_chunk_size)

    save_to_pickle(cache_path, chunks)
    return chunks