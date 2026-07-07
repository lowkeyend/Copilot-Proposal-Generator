from __future__ import annotations

import json

from app.services.llm_service import LLMService


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.headers = {}

    def json(self):
        return self._payload


def test_candidate_models_include_fallbacks() -> None:
    service = LLMService()
    candidates = service._candidate_models("openrouter/free")
    assert candidates
    assert candidates[0] == "openrouter/free"
    assert any(item != "openrouter/free" for item in candidates)
