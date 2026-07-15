"""OpenRouter chat-completion client.

A thin async wrapper around the OpenRouter REST API. The model is always
selectable per-request (the UI passes it through); the configured default is
used only when the request leaves the model blank. A small JSON-extraction
helper is provided because the agents frequently ask the model for structured
output.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Optional

import httpx

from app.config import get_settings
from app.services.runtime_settings_service import (
    get_grok_api_key,
    get_openrouter_api_key,
    get_openrouter_key_source,
)


class LLMError(RuntimeError):
    pass


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def available(self) -> bool:
        return bool(get_openrouter_api_key() or get_grok_api_key())

    def key_source(self) -> str:
        return get_openrouter_key_source()

    def resolve_model(self, model: Optional[str]) -> str:
        if model and model in self.settings.supported_models:
            return model
        if model:  # allow any model id the user typed, but default if blank
            return model
        return self.settings.preferred_default_model

    def _provider_for_model(self, model_id: str) -> str:
        return "groq" if (model_id or "").startswith("groq/") else "openrouter"

    def _provider_model_id(self, model_id: str) -> str:
        return model_id.split("groq/", 1)[1] if model_id.startswith("groq/") else model_id

    def _candidate_models(self, model: Optional[str]) -> list[str]:
        resolved = self.resolve_model(model)
        candidates: list[str] = [resolved]
        provider = self._provider_for_model(resolved)
        for item in self.settings.supported_models:
            if item not in candidates and self._provider_for_model(item) == provider:
                candidates.append(item)
        return candidates

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 2200,
    ) -> str:
        if not self.available:
            raise LLMError(
                "No configured LLM provider key is available. Add a working key in Settings."
            )
        async with httpx.AsyncClient(timeout=120.0) as client:
            errors: list[str] = []
            for model_id in self._candidate_models(model):
                provider = self._provider_for_model(model_id)
                provider_model = self._provider_model_id(model_id)
                if provider == "groq":
                    api_key = get_grok_api_key()
                    if not api_key:
                        errors.append(f"{model_id}: Groq API key is not configured.")
                        continue
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    }
                    url = "https://api.groq.com/openai/v1/chat/completions"
                else:
                    api_key = get_openrouter_api_key()
                    if not api_key:
                        errors.append(f"{model_id}: OpenRouter API key is not configured.")
                        continue
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": self.settings.openrouter_app_url,
                        "X-Title": self.settings.openrouter_app_name,
                    }
                    url = f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"
                payload: dict[str, Any] = {
                    "model": provider_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                last_error = ""
                for attempt in range(3):
                    try:
                        resp = await client.post(url, headers=headers, json=payload)
                    except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
                        last_error = f"{model_id}: {provider} transport error: {type(exc).__name__}: {str(exc)[:220]}"
                        if attempt < 2:
                            await asyncio.sleep(min(2 ** attempt, 5))
                            continue
                        break
                    if resp.status_code == 429 and attempt < 2:
                        retry_after = resp.headers.get("Retry-After", "").strip()
                        delay = 0.0
                        if retry_after.isdigit():
                            delay = float(retry_after)
                        else:
                            try:
                                body = resp.json()
                                delay = float(
                                    body.get("error", {})
                                    .get("metadata", {})
                                    .get("retry_after_seconds", 0)
                                )
                            except Exception:
                                delay = 0.0
                        await asyncio.sleep(max(1.0, min(delay or 3.0, 20.0)))
                        continue
                    if resp.status_code in {500, 502, 503, 504} and attempt < 2:
                        await asyncio.sleep(min(2 ** attempt, 5))
                        last_error = f"{model_id}: {provider} transient error {resp.status_code}: {resp.text[:220]}"
                        continue
                    if resp.status_code >= 400:
                        last_error = f"{model_id}: {provider} error {resp.status_code}: {resp.text[:280]}"
                        break
                    try:
                        data = resp.json()
                    except Exception as exc:
                        last_error = f"{model_id}: {provider} invalid JSON response: {type(exc).__name__}: {str(exc)[:220]}"
                        if attempt < 2:
                            await asyncio.sleep(min(2 ** attempt, 5))
                            continue
                        break
                    break
                else:  # pragma: no cover
                    last_error = f"{model_id}: {provider} request failed after retries."

                if not last_error:
                    break
                errors.append(last_error)
            else:
                raise LLMError(" | ".join(errors)[:1600] or "OpenRouter request failed.")
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:  # pragma: no cover
            raise LLMError(f"Unexpected OpenRouter response shape: {data}") from exc

    async def check(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> dict[str, str | bool]:
        key = (api_key or get_openrouter_api_key()).strip()
        model_id = self.resolve_model(model)
        provider = self._provider_for_model(model_id)
        effective_key = (api_key or (get_grok_api_key() if provider == "groq" else get_openrouter_api_key())).strip()
        if not effective_key:
            return {
                "ok": False,
                "fallback": True,
                "message": f"No {provider.title()} API key is configured.",
                "detail": "Set a key in Settings or backend env. Proposal generation is blocked until the key works.",
            }
        provider_model = self._provider_model_id(model_id)
        headers = {
            "Authorization": f"Bearer {effective_key}",
            "Content-Type": "application/json",
        }
        if provider == "openrouter":
            headers["HTTP-Referer"] = self.settings.openrouter_app_url
            headers["X-Title"] = self.settings.openrouter_app_name
        payload: dict[str, Any] = {
            "model": provider_model,
            "messages": [
                {"role": "system", "content": "Reply with OK."},
                {"role": "user", "content": "OK"},
            ],
            "temperature": 0,
            "max_tokens": 1,
        }
        url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code >= 400:
                    return {
                        "ok": False,
                        "fallback": True,
                        "message": f"{provider.title()} rejected the configured key or model.",
                        "detail": f"{resp.status_code}: {resp.text[:500]}",
                    }
                data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "ok": True,
                "fallback": False,
                "message": f"{provider.title()} key and model are valid. Proposal generation will use the live LLM path.",
                "detail": content.strip()[:100] or "Validated",
            }
        except Exception as exc:
            return {
                "ok": False,
                "fallback": True,
                "message": f"{provider.title()} check failed. Proposal generation is blocked until the key or model is fixed.",
                "detail": str(exc)[:500],
            }

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1600,
    ) -> Any:
        """Ask the model for JSON and parse it defensively."""
        raw = await self.chat(messages, model, temperature, max_tokens)
        return extract_json(raw)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of a model response.

    Handles ```json fences and leading/trailing prose, which smaller models
    sometimes emit despite instructions.
    """
    text = text.strip()
    # Strip code fences.
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fall back to first balanced object/array.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"Could not parse JSON from model output:\n{text[:400]}")


_llm_singleton: Optional[LLMService] = None


def get_llm() -> LLMService:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLMService()
    return _llm_singleton
