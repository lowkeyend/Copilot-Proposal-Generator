"""Query embedding service.

Supports either:
  * local `sentence-transformers` embeddings, or
  * a hosted embeddings API (OpenAI-compatible) so the backend does not have
    to load model weights in-process.
"""

from __future__ import annotations

import threading
from typing import Optional

import httpx

from app.config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None

    @property
    def ready(self) -> bool:
        if self.settings.embedding_provider.strip().lower() == "qdrant":
            return bool(self.settings.qdrant_url.strip() and self.settings.qdrant_api_key.strip())
        if self.settings.use_hosted_embeddings:
            return bool(self.settings.embedding_api_key.strip())
        return self._model is not None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            if self.settings.embedding_provider.strip().lower() == "qdrant":
                self._model = "qdrant-cloud-inference"
                return self._model
            if self.settings.use_hosted_embeddings:
                self._model = "hosted"
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.settings.embedding_model)
            except Exception as exc:  # pragma: no cover - environment dependent
                self._load_error = str(exc)
                raise
        return self._model

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.settings.use_hosted_embeddings:
            return self._embed_hosted(texts)

        model = self._ensure_model()
        prefixed = [
            f"{self.settings.embedding_query_prefix} {text}".strip() for text in texts
        ]
        vecs = model.encode(
            prefixed, normalize_embeddings=True, convert_to_numpy=True
        )
        return vecs.tolist()

    def _embed_hosted(self, texts: list[str]) -> list[list[float]]:
        api_key = self.settings.embedding_api_key.strip()
        if not api_key:
            raise RuntimeError(
                "EMBEDDING_API_KEY is not set. Add it to backend/.env when using hosted embeddings."
            )
        url = f"{self.settings.embedding_api_root.rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.embedding_model,
            "input": texts,
            "normalized": True,
        }
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Embedding API error {resp.status_code}: {resp.text[:500]}"
                )
            data = resp.json()
        try:
            rows = data["data"]
            return [row["embedding"] for row in rows]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected embedding response shape: {data}") from exc

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error


_embedding_singleton: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    global _embedding_singleton
    if _embedding_singleton is None:
        _embedding_singleton = EmbeddingService()
    return _embedding_singleton
