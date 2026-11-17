"""Embedding providers.

Two implementations ship with the app:

* :class:`ChromaLocalEmbedder` uses Chroma's bundled ONNX MiniLM model. It runs
  on CPU and needs no embeddings server.
* :class:`HashingEmbedder` is a dependency-free lexical fallback used when the
  ONNX model cannot be loaded, and by the test suite.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from abc import ABC, abstractmethod
from collections.abc import Sequence

from ognex.config import settings

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")


class Embedder(ABC):
    """Minimal embedding interface used by the retriever and dataprep."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]


class HashingEmbedder(Embedder):
    """Character/word hashing embedder (a deterministic feature-hashing baseline)."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = _WORD_RE.findall(text.lower())
        features = list(tokens)
        for token in tokens:
            padded = f"^{token}$"
            features.extend(padded[i : i + 3] for i in range(max(1, len(padded) - 2)))

        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            vector = [value / norm for value in vector]
        return vector

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


class ChromaLocalEmbedder(Embedder):
    """Chroma's bundled ONNX MiniLM embedder (all-MiniLM-L6-v2, 384-dim).

    Runs fully locally on CPU, so the demo needs no embeddings server. The
    model is downloaded once on first use (~80 MB) and cached by Chroma.
    """

    def __init__(self) -> None:
        from chromadb.utils import embedding_functions

        self._ef = embedding_functions.DefaultEmbeddingFunction()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [[float(value) for value in vector] for vector in self._ef(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class FallbackEmbedder(Embedder):
    """Use ``primary`` until it fails once, then permanently switch to ``fallback``."""

    def __init__(self, primary: Embedder, fallback: Embedder) -> None:
        self._primary = primary
        self._fallback = fallback
        self._lock = threading.Lock()
        self._degraded = False

    def _active(self) -> Embedder:
        return self._fallback if self._degraded else self._primary

    def _degrade(self, exc: Exception) -> None:
        with self._lock:
            if not self._degraded:
                self._degraded = True
                logger.warning(
                    "Embedding endpoint unavailable (%s). Falling back to hashing embedder; "
                    "retrieval will be lexical until the endpoint is restored.",
                    exc,
                )

    def embed_query(self, text: str) -> list[float]:
        if self._degraded:
            return self._fallback.embed_query(text)
        try:
            return self._primary.embed_query(text)
        except Exception as exc:  # noqa: BLE001 - any transport/provider error
            self._degrade(exc)
            return self._fallback.embed_query(text)

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self._degraded:
            return self._fallback.embed_documents(texts)
        try:
            return self._primary.embed_documents(texts)
        except Exception as exc:  # noqa: BLE001
            self._degrade(exc)
            return self._fallback.embed_documents(texts)


def build_embedder() -> Embedder:
    provider = settings.embedding_provider
    hashing = HashingEmbedder(dim=settings.embedding_dim)

    if provider == "hash":
        return hashing

    if provider in {"local", "default", "chroma"}:
        return FallbackEmbedder(ChromaLocalEmbedder(), hashing)

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")


_EMBEDDER: Embedder | None = None
_EMBEDDER_LOCK = threading.Lock()


def get_embeddings() -> Embedder:
    global _EMBEDDER
    if _EMBEDDER is None:
        with _EMBEDDER_LOCK:
            if _EMBEDDER is None:
                _EMBEDDER = build_embedder()
    return _EMBEDDER