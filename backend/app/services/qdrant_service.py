"""Read-only access to the existing Qdrant knowledge base.

This module NEVER writes to the collection — ingestion/embedding/population
is owned by Notebook 1. We only connect, count, search, and scroll payloads
for pattern discovery.

Because we don't control the exact payload schema Notebook 1 wrote, payload
field access is defensive: we probe a list of common key aliases for text,
source proposal, section name, and proposal family.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import get_settings
from app.models.schemas import EvidenceChunk
from app.services.embedding_service import get_embedder

logger = logging.getLogger(__name__)

# Candidate payload keys, most-specific first.
_TEXT_KEYS = ("text", "chunk", "content", "body", "passage", "chunk_text")
_SOURCE_KEYS = (
    "source_proposal",
    "source",
    "document",
    "doc",
    "file",
    "filename",
    "source_file",
    "proposal",
    "title",
)
_SECTION_KEYS = (
    "section",
    "section_name",
    "section_title",
    "heading",
    "heading_path",
    "section_path",
)
_FAMILY_KEYS = (
    "proposal_family",
    "family",
    "category",
    "proposal_type",
    "type",
)


def _first(payload: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
    for k in keys:
        v = payload.get(k)
        if v:
            if isinstance(v, list):
                return " > ".join(str(x) for x in v)
            return str(v)
    return default


class QdrantService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        self._connect_error: Optional[str] = None
        self._last_search_error: Optional[str] = None

    def _client_or_none(self):
        if self._client is not None:
            return self._client
        try:
            from qdrant_client import QdrantClient

            if self.settings.use_qdrant_cloud:
                self._client = QdrantClient(
                    url=self.settings.qdrant_url,
                    api_key=self.settings.qdrant_api_key or None,
                )
            else:
                self._client = QdrantClient(path=str(self.settings.qdrant_local_path))
        except Exception as exc:  # pragma: no cover - environment dependent
            self._connect_error = str(exc)
            self._client = None
        return self._client

    # ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        client = self._client_or_none()
        mode = "cloud" if self.settings.use_qdrant_cloud else "local"
        embedder = get_embedder()
        if client is None:
            return {
                "connected": False,
                "collection": self.settings.qdrant_collection,
                "points": 0,
                "mode": mode,
                "embedding_ready": embedder.ready,
                "embedding_model": self.settings.embedding_model,
                "message": self._connect_error or "Qdrant client unavailable.",
            }
        try:
            collections = {c.name for c in client.get_collections().collections}
            if self.settings.qdrant_collection not in collections:
                return {
                    "connected": True,
                    "collection": self.settings.qdrant_collection,
                    "points": 0,
                    "mode": mode,
                    "embedding_ready": embedder.ready,
                    "embedding_model": self.settings.embedding_model,
                    "message": (
                        f"Collection '{self.settings.qdrant_collection}' not found. "
                        f"Available: {sorted(collections) or 'none'}. "
                        "Point QDRANT_PATH at the DB created by Notebook 1."
                    ),
                }
            count = client.count(
                self.settings.qdrant_collection, exact=True
            ).count
            return {
                "connected": True,
                "collection": self.settings.qdrant_collection,
                "points": int(count),
                "mode": mode,
                "embedding_ready": embedder.ready,
                "embedding_model": self.settings.embedding_model,
                "message": self._last_search_error or "ok",
            }
        except Exception as exc:  # pragma: no cover
            return {
                "connected": False,
                "collection": self.settings.qdrant_collection,
                "points": 0,
                "mode": mode,
                "embedding_ready": embedder.ready,
                "embedding_model": self.settings.embedding_model,
                "message": str(exc),
            }

    @property
    def has_data(self) -> bool:
        return self.status().get("points", 0) > 0

    # ------------------------------------------------------------------
    def search(
        self,
        query_vector: list[float],
        top_k: int = 6,
        keywords: Optional[list[str]] = None,
    ) -> list[EvidenceChunk]:
        client = self._client_or_none()
        if client is None:
            return []
        try:
            self._last_search_error = None
            hits = client.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            self._last_search_error = str(exc)
            logger.warning("Qdrant search failed: %s", exc)
            return []

        results: list[EvidenceChunk] = []
        for h in hits:
            payload = h.payload or {}
            results.append(
                EvidenceChunk(
                    text=_first(payload, _TEXT_KEYS),
                    score=float(getattr(h, "score", 0.0) or 0.0),
                    source_proposal=_first(payload, _SOURCE_KEYS),
                    source_section=_first(payload, _SECTION_KEYS),
                    proposal_family=_first(payload, _FAMILY_KEYS),
                    chunk_id=str(getattr(h, "id", "")),
                )
            )
        return results

    # ------------------------------------------------------------------
    def scroll_payloads(self, limit: int = 5000) -> list[dict[str, Any]]:
        """Pull payloads (no vectors) for pattern discovery."""
        client = self._client_or_none()
        if client is None:
            return []
        payloads: list[dict[str, Any]] = []
        offset = None
        try:
            while len(payloads) < limit:
                points, offset = client.scroll(
                    collection_name=self.settings.qdrant_collection,
                    with_payload=True,
                    with_vectors=False,
                    limit=min(512, limit - len(payloads)),
                    offset=offset,
                )
                if not points:
                    break
                payloads.extend(p.payload or {} for p in points)
                if offset is None:
                    break
        except Exception:
            return payloads
        return payloads

    @staticmethod
    def normalize_payload(payload: dict[str, Any]) -> dict[str, str]:
        """Return a normalized view used by pattern discovery."""
        return {
            "text": _first(payload, _TEXT_KEYS),
            "source": _first(payload, _SOURCE_KEYS),
            "section": _first(payload, _SECTION_KEYS),
            "family": _first(payload, _FAMILY_KEYS),
        }


_qdrant_singleton: Optional[QdrantService] = None


def get_qdrant() -> QdrantService:
    global _qdrant_singleton
    if _qdrant_singleton is None:
        _qdrant_singleton = QdrantService()
    return _qdrant_singleton
