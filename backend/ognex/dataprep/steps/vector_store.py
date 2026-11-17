"""Embed child chunks and persist them in ChromaDB."""

from __future__ import annotations

import os
import uuid

from ognex.config import settings
from ognex.embeddings import get_embeddings
from ognex.helper import save_to_pickle
from ognex.retriever.vectorstore import add_documents, delete_collection

EMBED_BATCH_SIZE = 64


def create_vector_database(
    parent_chunks: list[str],
    doc_ids: list[str],
    child_chunks_per_parent: list[list[str]],
    knowledge_base_name: str,
    suffix: str = "",
    replace: bool = True,
) -> None:
    if replace:
        delete_collection(knowledge_base_name, suffix)

    flat_texts: list[str] = []
    flat_parent_ids: list[str] = []
    for parent_index, children in enumerate(child_chunks_per_parent):
        for child in children:
            if not child.strip():
                continue
            flat_texts.append(child)
            flat_parent_ids.append(doc_ids[parent_index])

    embedding = get_embeddings()
    for start in range(0, len(flat_texts), EMBED_BATCH_SIZE):
        texts = flat_texts[start : start + EMBED_BATCH_SIZE]
        vectors = embedding.embed_documents(texts)
        add_documents(
            knowledge_base_name,
            suffix,
            ids=[str(uuid.uuid4()) for _ in texts],
            documents=texts,
            vectors=vectors,
            doc_ids=flat_parent_ids[start : start + EMBED_BATCH_SIZE],
        )

    # Parent chunks are identical across granularities; each collection keeps
    # its own copy so collections stay self-contained and easy to delete.
    docstore_name = f"{knowledge_base_name}{'_' + suffix if suffix else ''}_docstore.pkl.gz"
    save_to_pickle(
        os.path.join(settings.pickle_dir, docstore_name),
        list(zip(doc_ids, parent_chunks)),
    )