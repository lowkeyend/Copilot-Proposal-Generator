"""OpenRouter chat-completion client.

A thin async wrapper around the OpenRouter REST API. The model is always
selectable per-request (the UI passes it through); we fall back to the
configured default otherwise. A small JSON-extraction helper is provided
because the agents frequently ask the model for structured output.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from app.config import get_settings


class LLMError(RuntimeError):
    pass


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def available(self) -> bool:
        return bool(self.settings.openrouter_api_key)

    def resolve_model(self, model: Optional[str]) -> str:
        if model and model in self.settings.supported_models:
            return model
        if model:  # allow any model id the user typed, but default if blank
            return model
        return self.settings.default_model

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.4,
        max_tokens: int = 2200,
    ) -> str:
        if not self.available:
            raise LLMError(
                "OPENROUTER_API_KEY is not set. Add it to backend/.env to enable generation."
            )

        model_id = self.resolve_model(model)
        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.settings.openrouter_app_url,
            "X-Title": self.settings.openrouter_app_name,
        }
        payload: dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        url = f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise LLMError(
                    f"OpenRouter error {resp.status_code}: {resp.text[:500]}"
                )
            data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:  # pragma: no cover
            raise LLMError(f"Unexpected OpenRouter response shape: {data}") from exc

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
