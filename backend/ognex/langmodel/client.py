"""Chat client for any OpenAI-compatible inference server.

Reasoning output is normalised across servers: SGLang/DeepSeek expose it as
``delta.reasoning_content``; some expose ``delta.reasoning``. Token usage is
requested with ``stream_options.include_usage`` and returned as a final
``TokenChunk`` so the UI can show context consumption.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from ognex import runtime_settings
from ognex.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TokenChunk:
    content: str = ""
    reasoning: str = ""
    usage: dict[str, int] | None = None


class ChatClient(ABC):
    @abstractmethod
    def stream(self, messages: list[dict], **kwargs) -> Iterator[TokenChunk]:
        ...

    @abstractmethod
    def invoke(self, messages: list[dict], **kwargs) -> str:
        ...


def _delta_field(delta, name: str) -> str:
    value = getattr(delta, name, None)
    if value:
        return value
    extra = getattr(delta, "model_extra", None) or {}
    return extra.get(name) or ""


def _usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        raw = usage.model_dump()
    elif isinstance(usage, dict):
        raw = usage
    else:
        try:
            raw = dict(usage)
        except Exception:  # noqa: BLE001
            return None
    values = {
        str(key): int(value)
        for key, value in raw.items()
        if isinstance(value, (int, float))
    }
    details = raw.get("completion_tokens_details")
    if isinstance(details, dict) and isinstance(details.get("reasoning_tokens"), int):
        values.setdefault("reasoning_tokens", details["reasoning_tokens"])
    return values or None


class OpenAICompatibleClient(ChatClient):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: int | None = None,
    ) -> None:
        from openai import OpenAI

        self.model = model
        self._client = OpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout or settings.llm_request_timeout,
            max_retries=2,
            default_headers={"User-Agent": "Ognex-RAG"},
        )

    def _params(self, kwargs: dict) -> dict:
        params = {
            "model": self.model,
            "temperature": kwargs.get("temperature", settings.llm_temperature),
            "max_tokens": kwargs.get("max_tokens", settings.llm_max_tokens),
        }
        if kwargs.get("stop"):
            params["stop"] = kwargs["stop"]
        return params

    def stream(self, messages: list[dict], **kwargs) -> Iterator[TokenChunk]:
        started = time.perf_counter()
        params = {"messages": messages, "stream": True, **self._params(kwargs)}
        try:
            response = self._client.chat.completions.create(
                stream_options={"include_usage": True}, **params
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) not in (400, 404, 422):
                raise
            response = self._client.chat.completions.create(**params)

        first_token_seen = False
        final_usage: dict[str, int] | None = None
        for chunk in response:
            usage = _usage_dict(getattr(chunk, "usage", None))
            if usage:
                final_usage = usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            content = _delta_field(delta, "content")
            reasoning = _delta_field(delta, "reasoning_content") or _delta_field(
                delta, "reasoning"
            )
            if not content and not reasoning:
                continue
            if not first_token_seen:
                first_token_seen = True
                logger.debug("Time to first token: %.3fs", time.perf_counter() - started)
            yield TokenChunk(content=content, reasoning=reasoning)

        if final_usage:
            yield TokenChunk(usage=final_usage)

    def invoke(self, messages: list[dict], **kwargs) -> str:
        response = self._client.chat.completions.create(
            messages=messages, stream=False, **self._params(kwargs)
        )
        return (response.choices[0].message.content or "").strip()


_CLIENT: ChatClient | None = None
_CLIENT_KEY: tuple[str, str, str] | None = None


def get_chat_client(runtime: runtime_settings.RuntimeSettings | None = None) -> ChatClient:
    global _CLIENT, _CLIENT_KEY
    runtime = runtime or runtime_settings.load()
    key = (runtime.api_base, runtime.model, runtime.api_key)
    if _CLIENT is None or _CLIENT_KEY != key:
        _CLIENT = OpenAICompatibleClient(
            base_url=runtime.api_base,
            model=runtime.model,
            api_key=runtime.api_key,
        )
        _CLIENT_KEY = key
    return _CLIENT


def reset_chat_client() -> None:
    global _CLIENT, _CLIENT_KEY
    _CLIENT = None
    _CLIENT_KEY = None