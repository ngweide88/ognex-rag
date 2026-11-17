"""Centralised application configuration.

Every environment variable used by the backend is declared here so the rest of
the code never has to guess a default or silently fall back to ``None``.
Environment values are read once per process from ``.env`` (backend root) and
the real environment, with the latter taking precedence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent

# ``override=False`` keeps real environment variables ahead of the file.
load_dotenv(BACKEND_DIR / ".env", override=False)
load_dotenv(PROJECT_DIR / ".env", override=False)


def _str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got {raw!r}") from exc


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a number, got {raw!r}") from exc


def _bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str, default: str = "") -> list[str]:
    raw = _str(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _normalise_openai_base_url(url: str) -> str:
    """Accept ``host:port``, ``host:port/v1`` or a full URL."""
    url = url.rstrip("/")
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = f"http://{url}"
    if not url.endswith("/v1"):
        url = f"{url}/v1"
    return url


@dataclass(frozen=True)
class Settings:
    # ------------------------------------------------------------------ app
    app_name: str = field(default_factory=lambda: _str("APP_NAME", "Ognex RAG"))
    debug: bool = field(default_factory=lambda: _bool("APP_DEBUG", True))
    host: str = field(default_factory=lambda: _str("APP_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _int("APP_PORT", 5000))

    # ----------------------------------------------------------------- data
    db_table_prefix: str = field(default_factory=lambda: _str("DB_TABLE_PREFIX", "ognex"))

    # -------------------------------------------------------------- chromadb
    chroma_collection_prefix: str = field(
        default_factory=lambda: _str("CHROMA_COLLECTION_PREFIX", "kb")
    )
    chroma_batch_size: int = field(default_factory=lambda: _int("CHROMA_BATCH_SIZE", 512))

    # --------------------------------------------------------------- models
    llm_base_url: str = field(
        default_factory=lambda: _normalise_openai_base_url(
            _str("LLM_BASE_URL", "http://127.0.0.1:8000")
        )
    )
    llm_model: str = field(
        default_factory=lambda: _str("LLM_MODEL", "your-chat-model")
    )
    llm_api_key: str = field(default_factory=lambda: _str("LLM_API_KEY", "EMPTY"))
    llm_temperature: float = field(default_factory=lambda: _float("LLM_TEMPERATURE", 0.5))
    llm_max_tokens: int = field(default_factory=lambda: _int("LLM_MAX_TOKENS", 262144))
    llm_context_window: int = field(default_factory=lambda: _int("LLM_CONTEXT_WINDOW", 32768))
    llm_request_timeout: int = field(default_factory=lambda: _int("LLM_REQUEST_TIMEOUT", 600))

    embedding_provider: str = field(
        default_factory=lambda: _str("EMBEDDING_PROVIDER", "local").lower()
    )
    embedding_dim: int = field(default_factory=lambda: _int("EMBEDDING_DIM", 1024))

    # ----------------------------------------------------------- retrieval
    top_k_contexts: int = field(default_factory=lambda: _int("TOP_K_CONTEXTS", 3))
    chunk_sizes: list[int] = field(
        default_factory=lambda: [
            int(size) for size in _csv("CHUNK_SIZES", "500,250,150")
        ]
    )
    child_chunk_overlap_ratio: float = field(
        default_factory=lambda: _float("CHILD_CHUNK_OVERLAP_RATIO", 0.05)
    )
    parent_chunk_size: int = field(default_factory=lambda: _int("PARENT_CHUNK_SIZE", 2400))
    parent_chunk_overlap: int = field(default_factory=lambda: _int("PARENT_CHUNK_OVERLAP", 25))
    min_parent_chunk_size: int = field(default_factory=lambda: _int("MIN_PARENT_CHUNK_SIZE", 64))

    # --------------------------------------------------------------- paths
    data_dir: Path = field(default_factory=lambda: Path(_str("DATA_DIR", str(BACKEND_DIR / "data"))))
    log_dir: Path = field(default_factory=lambda: Path(_str("LOG_DIR", str(BACKEND_DIR / "logs"))))
    max_upload_mb: int = field(default_factory=lambda: _int("MAX_UPLOAD_MB", 100))

    @property
    def pdf_upload_dir(self) -> Path:
        return self.data_dir / "pdf"

    @property
    def pickle_dir(self) -> Path:
        return self.data_dir / "pickle"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def table_prefix(self) -> str:
        """Validated SQL identifier prefix (never user supplied at runtime)."""
        prefix = "".join(ch for ch in self.db_table_prefix if ch.isalnum() or ch == "_")
        return prefix or "ognex"

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.pdf_upload_dir,
            self.pickle_dir,
            self.chroma_dir,
            self.log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
