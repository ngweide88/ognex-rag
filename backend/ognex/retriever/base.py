"""Hybrid retriever over ChromaDB collections.

Strategy:

1. Embed the query once.
2. For each child-chunk size (large / medium / small), run a plain
   cosine-similarity search *and* an MMR search, then deduplicate.
3. Fuse the six ranked lists with Reciprocal Rank Fusion (RRF).
4. Return the parent chunks in fused order, expanded with surrounding text so
   the model sees a coherent passage.

All operations run against embedded Chroma collections.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Sequence

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from ognex.config import settings
from ognex.constants import NO_RAG_KNOWLEDGE_BASE
from ognex.exception import KnowledgeBaseNotFound
from ognex.helper import load_from_pickle
from ognex.retriever.vectorstore import CHUNK_SUFFIXES, get_collection

logger = logging.getLogger(__name__)


class RetrieverInterface(ABC):
    @abstractmethod
    def get_context(self, query: str) -> list[str]:
        ...


class NullRetriever(RetrieverInterface):
    def get_context(self, query: str) -> list[str]:
        return []


class ChromaRetriever(RetrieverInterface):
    def __init__(self, knowledge_base_names: list[str], embedding) -> None:
        self.embedding = embedding
        self.knowledge_base_names = knowledge_base_names
        self.docstore = self._load_parent_docstores(knowledge_base_names)
        self.extended_docstore = self._build_extended_docstore(self.docstore)

    # ------------------------------------------------------------- docstores
    @staticmethod
    def _load_parent_docstores(kb_names: list[str]) -> dict[str, str]:
        docstore: dict[str, str] = {}
        for kb_name in kb_names:
            path = os.path.join(settings.pickle_dir, f"{kb_name}_docstore.pkl.gz")
            if not os.path.exists(path):
                raise KnowledgeBaseNotFound(
                    f"Knowledge base '{kb_name}' has no parent docstore. Re-ingest the document."
                )
            docstore.update(dict(load_from_pickle(path)))
        return docstore

    @staticmethod
    def _build_extended_docstore(docstore: dict[str, str]) -> dict[str, str]:
        """Expand each parent chunk with ±800/1800 characters of neighbours.

        Recording offsets while joining keeps lookup linear and avoids matching
        an earlier duplicate passage.
        """
        extended: dict[str, str] = {}
        part_offsets: list[tuple[str, int, int]] = []
        pieces: list[str] = []
        cursor = 0
        for doc_id, text in docstore.items():
            pieces.append(text)
            part_offsets.append((doc_id, cursor, cursor + len(text)))
            cursor += len(text)

        combined = "".join(pieces)
        for doc_id, start, end in part_offsets:
            extended[doc_id] = combined[max(0, start - 800) : min(len(combined), end + 1800)]
        return extended

    # --------------------------------------------------------------- queries
    def _collections_for_suffix(self, suffix: str):
        collections = []
        for kb_name in self.knowledge_base_names:
            try:
                collections.append(get_collection(kb_name, suffix))
            except Exception as exc:  # noqa: BLE001 - a missing collection is skipped
                logger.debug("Skipping %s/%s: %s", kb_name, suffix or "large", exc)
        return collections

    @staticmethod
    def _count(collection) -> int:
        try:
            return int(collection.count())
        except Exception:  # noqa: BLE001
            return 0

    def _query(self, collections, query_vector: Sequence[float], n: int) -> list[dict]:
        hits: list[dict] = []
        for collection in collections:
            available = self._count(collection)
            if available == 0:
                continue
            result = collection.query(
                query_embeddings=[list(query_vector)],
                n_results=min(n, available),
                include=["metadatas", "distances", "embeddings"],
            )
            ids = result.get("ids") or [[]]
            metadatas = result.get("metadatas") or [[]]
            distances = result.get("distances") or [[]]
            embeddings = result.get("embeddings")
            if embeddings is None:
                embeddings = [[]]
            for doc_id, metadata, distance, vector in zip(
                ids[0], metadatas[0], distances[0], embeddings[0]
            ):
                parent_id = (metadata or {}).get("doc_id")
                if not parent_id:
                    continue
                hits.append(
                    {
                        "doc_id": parent_id,
                        "distance": float(distance),
                        "vector": vector,
                    }
                )
        return hits

    def calculate_k(self, total_chunks: int, mode: str) -> int:
        if mode == "similarity":
            k = int(0.2 * total_chunks)
            return min(max(k, 150), 450)
        if mode == "mmr":
            k = int(0.1 * total_chunks)
            return min(max(k, 90), 270)
        raise ValueError("Mode must be 'similarity' or 'mmr'")

    def similarity_search(self, collections, query_vector, k: int) -> list[str]:
        hits = self._query(collections, query_vector, k)
        hits.sort(key=lambda hit: hit["distance"])
        return self._unique_preserve_order([hit["doc_id"] for hit in hits])

    def mmr_search(self, collections, query_vector, k: int) -> list[str]:
        hits = self._query(collections, query_vector, k)
        hits = [hit for hit in hits if hit["vector"] is not None]
        if not hits:
            return []

        query_vec = np.array(query_vector, dtype=np.float32).reshape(1, -1)
        retrieved = np.array([hit["vector"] for hit in hits], dtype=np.float32)

        query_sim = cosine_similarity(retrieved, query_vec).flatten()
        doc_sim = cosine_similarity(retrieved)

        selected = self._mmr(query_sim, doc_sim, lambda_param=0.9, top_n=min(150, len(hits)))
        return self._unique_preserve_order([hits[index]["doc_id"] for index in selected])

    @staticmethod
    def _mmr(query_sim: np.ndarray, doc_sim: np.ndarray, lambda_param: float, top_n: int) -> list[int]:
        selected: list[int] = []
        remaining = list(range(len(query_sim)))
        diversity = np.zeros(len(remaining), dtype=np.float32)

        while len(selected) < top_n and remaining:
            if not selected:
                next_index = int(np.argmax(query_sim))
            else:
                diversity[remaining] = np.maximum(
                    diversity[remaining], doc_sim[np.ix_(remaining, [selected[-1]])].ravel()
                )
                scores = (
                    lambda_param * query_sim[remaining]
                    - (1 - lambda_param) * diversity[remaining]
                )
                next_index = remaining[int(np.argmax(scores))]

            selected.append(next_index)
            remaining.remove(next_index)

        return selected

    @staticmethod
    def _unique_preserve_order(items: list[str]) -> list[str]:
        return list(dict.fromkeys(items))

    @staticmethod
    def aggregate_rankings(doc_id_lists: list[list[str]], k: int = 60) -> list[str]:
        """Fuse ranked lists with Reciprocal Rank Fusion (RRF).

        RRF is scale-free, handles documents missing from some lists, and is a
        standard choice for combining heterogeneous retrievers.
        """
        scores: dict[str, float] = defaultdict(float)
        for ranked_list in doc_id_lists:
            for position, doc_id in enumerate(ranked_list):
                scores[doc_id] += 1.0 / (k + position + 1)

        return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda item: -item[1])]

    # ---------------------------------------------------------------- public
    def get_context(self, query: str) -> list[str]:
        query_vector = self.embedding.embed_query(query)
        total_chunks = max(len(self.docstore), 1)

        similarity_k = self.calculate_k(total_chunks, "similarity")
        mmr_k = self.calculate_k(total_chunks, "mmr")

        combined_rankings: list[list[str]] = []
        for suffix in CHUNK_SUFFIXES:
            collections = self._collections_for_suffix(suffix)
            if not collections:
                continue
            combined_rankings.append(
                self.similarity_search(collections, query_vector, similarity_k)
            )
            combined_rankings.append(self.mmr_search(collections, query_vector, mmr_k))

        if not combined_rankings:
            return []

        aggregated = self.aggregate_rankings(combined_rankings)
        return [
            self.extended_docstore[doc_id]
            for doc_id in aggregated
            if doc_id in self.extended_docstore
        ]


def initialise_retriever_from_config(
    knowledge_base_names: str | list[str] | None, embedding
) -> RetrieverInterface:
    if not knowledge_base_names:
        return NullRetriever()

    if isinstance(knowledge_base_names, str):
        knowledge_base_names = [knowledge_base_names]

    requested = [kb for kb in knowledge_base_names if kb != NO_RAG_KNOWLEDGE_BASE]
    if any(kb == NO_RAG_KNOWLEDGE_BASE for kb in knowledge_base_names) or not requested:
        return NullRetriever()

    return ChromaRetriever(requested, embedding)