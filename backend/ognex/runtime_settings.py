"""Runtime-selectable inference endpoint and model.

The environment (``.env``) provides defaults. Changes made in the UI are stored
in ``data/runtime_settings.json`` so the endpoint/model can be switched without
restarting the service. The endpoint's ``/v1/models`` metadata (including its
context window) is saved to ``backend/endpoint_metadata.json``.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

from ognex.config import settings as env

BACKEND_DIR = Path(__file__).resolve().parent.parent
METADATA_PATH = BACKEND_DIR / "endpoint_metadata.json"
_LOCK = threading.RLock()
_CONTEXT_KEYS = ("context_length", "max_model_len", "max_context_length", "context_window", "max_context")


def _normalise_base(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    if not value.endswith("/v1"):
        value = f"{value}/v1"
    return value


@dataclass
class RuntimeSettings:
    api_base: str = ""
    api_key: str = ""
    model: str = ""
    context_window: int = 0


def _defaults() -> RuntimeSettings:
    return RuntimeSettings(
        api_base=_normalise_base(env.llm_base_url),
        api_key=env.llm_api_key,
        model=env.llm_model,
        context_window=env.llm_context_window,
    )


def settings_path() -> Path:
    env.ensure_directories()
    return env.data_dir / "runtime_settings.json"


def load() -> RuntimeSettings:
    defaults = _defaults()
    path = settings_path()
    if not path.exists():
        return defaults
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults
    if not isinstance(raw, dict):
        return defaults
    try:
        context_window = int(raw.get("context_window") or defaults.context_window)
    except (TypeError, ValueError):
        context_window = defaults.context_window
    return RuntimeSettings(
        api_base=_normalise_base(str(raw.get("api_base") or "")) or defaults.api_base,
        api_key=str(raw.get("api_key") if raw.get("api_key") is not None else defaults.api_key),
        model=str(raw.get("model") or defaults.model),
        context_window=max(context_window, 1024),
    )


def save(runtime: RuntimeSettings) -> None:
    path = settings_path()
    with _LOCK:
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(runtime), indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)


def public(runtime: RuntimeSettings) -> dict[str, Any]:
    key = (runtime.api_key or "").strip()
    return {
        "api_base": runtime.api_base,
        "model": runtime.model,
        "context_window": runtime.context_window,
        "api_key_set": bool(key and key.upper() not in {"EMPTY", "NONE", "NOT-NEEDED"}),
    }


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Accept": "application/json", "User-Agent": "Ognex-RAG"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _write_metadata(payload: dict[str, Any]) -> None:
    try:
        temp = METADATA_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, METADATA_PATH)
    except OSError:
        pass


def fetch_models(
    api_base: str | None = None,
    api_key: str | None = None,
    *,
    persist: bool = True,
) -> dict[str, Any]:
    runtime = load()
    base = _normalise_base(api_base) if api_base else runtime.api_base
    key = runtime.api_key if api_key is None else api_key
    if not base:
        return {"ok": False, "models": [], "error": "No endpoint configured", "fetched_at": None}

    try:
        response = requests.get(f"{base}/models", headers=_headers(key), timeout=15)
        if response.status_code >= 400:
            return {
                "ok": False,
                "models": [],
                "error": f"HTTP {response.status_code}: {response.text[:300]}",
                "api_base": base,
                "fetched_at": int(time.time()),
            }
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        return {
            "ok": False,
            "models": [],
            "error": f"{type(exc).__name__}: {exc}",
            "api_base": base,
            "fetched_at": int(time.time()),
        }

    raw = payload.get("data") if isinstance(payload, dict) else payload
    models: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and item.get("id"):
                models.append(dict(item))
            elif isinstance(item, str):
                models.append({"id": item})
    models.sort(key=lambda item: str(item.get("id", "")))

    result = {
        "ok": True,
        "models": models,
        "error": None,
        "api_base": base,
        "fetched_at": int(time.time()),
    }
    if persist:
        _write_metadata(result)
    return result


def context_for(model: str, models: list[dict[str, Any]]) -> int | None:
    for item in models:
        if item.get("id") != model:
            continue
        for key in _CONTEXT_KEYS:
            value = item.get(key)
            if isinstance(value, (int, float)) and value > 1024:
                return int(value)
    return None


def load_metadata() -> dict[str, Any]:
    try:
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "models": [], "error": "No metadata fetched yet", "fetched_at": None}


def ensure_initialized() -> None:
    """Create the runtime settings file once, detecting the context window."""
    if settings_path().exists():
        return
    runtime = load()
    result = fetch_models(runtime.api_base, runtime.api_key)
    if result["ok"]:
        detected = context_for(runtime.model, result["models"])
        if detected:
            runtime.context_window = detected
    save(runtime)