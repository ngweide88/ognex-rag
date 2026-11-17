"""ChromaDB persistence helpers.

Chroma runs embedded: a persistent client opens ``data/chroma`` directly. Each
knowledge base gets three collections, one per child-chunk size.

Swapping in a remote vector store later only requires a new implementation of
``RetrieverInterface``; the ingestion steps talk to this module.
"""

from __future__ import annotations

import logging
import re
import threading

import chromadb
from chromadb.config import Settings as ChromaClientSettings

from ognex.config import settings

logger = logging.getLogger(__name__)

_CLIENT: chromadb.ClientAPI | None = None
_CLIENT_LOCK = threading.Lock()

CHUNK_SUFFIXES = ["", "medium", "small"]
_SIZE_LABELS = {"": "large", "medium": "medium", "small": "small"}


def get_chroma_client() -> chromadb.ClientAPI:
    global _CLIENT
    if _CLIENT is None:
        with _CLIENT_LOCK:
            if _CLIENT is None:
                settings.ensure_directories()
                _CLIENT = chromadb.PersistentClient(
                    path=str(settings.chroma_dir),
                    settings=ChromaClientSettings(anonymized_telemetry=False),
                )
    return _CLIENT


def collection_name(knowledge_base_name: str, suffix: str = "") -> str:
    """Build a Chroma-safe collection name (3-63 chars, [a-zA-Z0-9._-])."""
    base = f"{settings.chroma_collection_prefix}_{knowledge_base_name}_{_SIZE_LABELS[suffix]}"
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("._-").lower()
    if len(name) < 3:
        name = f"kb-{name}".ljust(3, "x")
    return name[:63]


def get_or_create_collection(knowledge_base_name: str, suffix: str = ""):
    return get_chroma_client().get_or_create_collection(
        name=collection_name(knowledge_base_name, suffix),
        metadata={"hnsw:space": "cosine", "kb_name": knowledge_base_name},
    )


def get_collection(knowledge_base_name: str, suffix: str = ""):
    return get_chroma_client().get_collection(collection_name(knowledge_base_name, suffix))


def delete_collection(knowledge_base_name: str, suffix: str = "") -> bool:
    name = collection_name(knowledge_base_name, suffix)
    try:
        get_chroma_client().delete_collection(name)
        return True
    except Exception:  # noqa: BLE001 - missing collection is fine
        logger.debug("Collection %s not present", name)
        return False


def delete_knowledge_base_collections(knowledge_base_name: str) -> list[str]:
    deleted: list[str] = []
    for suffix in CHUNK_SUFFIXES:
        name = collection_name(knowledge_base_name, suffix)
        if delete_collection(knowledge_base_name, suffix):
            deleted.append(name)
    return deleted


def add_documents(
    knowledge_base_name: str,
    suffix: str,
    ids: list[str],
    documents: list[str],
    vectors: list[list[float]],
    doc_ids: list[str],
) -> None:
    collection = get_or_create_collection(knowledge_base_name, suffix)
    batch = max(1, settings.chroma_batch_size)

    for start in range(0, len(ids), batch):
        end = start + batch
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            embeddings=vectors[start:end],
            metadatas=[
                {"doc_id": doc_id, "kb_name": knowledge_base_name}
                for doc_id in doc_ids[start:end]
            ],
        )