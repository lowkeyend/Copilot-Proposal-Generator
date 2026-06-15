"""Query embedding using the same model Notebook 1 used for ingestion.

We only ever *embed queries* here — ingestion is owned by Notebook 1 and is
never rebuilt. The model is loaded lazily so the API can boot (and serve
status/health) even on machines where sentence-transformers / the model
weights are not yet downloaded.
"""

from __future__ import annotations

import threading
from typing import Optional

from app.config import get_settings


class EmbeddingService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._model = None
        self._lock = threading.Lock()
        self._load_error: Optional[str] = None

    @property
    def ready(self) -> bool:
        return self._model is not None

    def _ensure_model(self):
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(self.settings.embedding_model)
            except Exception as exc:  # pragma: no cover - environment dependent
                self._load_error = str(exc)
                raise
        return self._model

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query.

        bge-* models expect an instruction prefix for retrieval, which is what
        Notebook 1 used. We mirror that here so query/document vectors live in
        the same space.
        """
        model = self._ensure_model()
        prefixed = f"{self.settings.embedding_query_prefix} {text}".strip()
        vec = model.encode(
            prefixed, normalize_embeddings=True, convert_to_numpy=True
        )
        return vec.tolist()

    @property
    def load_error(self) -> Optional[str]:
        return self._load_error


_embedding_singleton: Optional[EmbeddingService] = None


def get_embedder() -> EmbeddingService:
    global _embedding_singleton
    if _embedding_singleton is None:
        _embedding_singleton = EmbeddingService()
    return _embedding_singleton
