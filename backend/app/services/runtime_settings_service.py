"""Runtime settings persisted in storage.

This lets the deployed app update non-secret operational values from the UI
without rebuilding the backend image. The current use case is the OpenRouter
API key, which the LLM service reads before falling back to environment vars.
"""

from __future__ import annotations

import json
import threading
from contextvars import ContextVar
from pathlib import Path

from app.config import get_settings

_lock = threading.Lock()
_request_openrouter_api_key: ContextVar[str] = ContextVar(
    "request_openrouter_api_key", default=""
)


def set_request_openrouter_api_key(value: str) -> None:
    _request_openrouter_api_key.set((value or "").strip())


def clear_request_openrouter_api_key() -> None:
    _request_openrouter_api_key.set("")


def _runtime_settings_path() -> Path:
    settings = get_settings()
    settings.ensure_dirs()
    return settings.storage_path / "runtime_settings.json"


def load_runtime_settings() -> dict[str, str]:
    path = _runtime_settings_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in raw.items() if str(v).strip()}
    except Exception:
        return {}


def save_runtime_settings(openrouter_api_key: str) -> dict[str, str]:
    payload = {"openrouter_api_key": openrouter_api_key.strip()}
    path = _runtime_settings_path()
    with _lock:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def get_openrouter_api_key() -> str:
    request_value = _request_openrouter_api_key.get().strip()
    if request_value:
        return request_value
    runtime = load_runtime_settings().get("openrouter_api_key", "").strip()
    if runtime:
        return runtime
    return get_settings().openrouter_api_key.strip()


def get_openrouter_key_source() -> str:
    runtime = load_runtime_settings().get("openrouter_api_key", "").strip()
    if runtime:
        return "runtime"
    if get_settings().openrouter_api_key.strip():
        return "env"
    return "none"


def get_openrouter_config_status() -> dict[str, str | bool]:
    source = get_openrouter_key_source()
    key = get_openrouter_api_key()
    return {
        "api_key_set": bool(key),
        "source": source,
        "value": key,
    }
