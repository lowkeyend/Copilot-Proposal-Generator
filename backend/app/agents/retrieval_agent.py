"""Agent 6 - Retrieval Agent.

For a single section, retrieve only the relevant chunks from the knowledge
base (not a generic query). We first try the shared embedding path used at
ingestion, then fall back to lexical matching over stored payloads so Railway
deployments still return evidence when the embedding model is unavailable.
"""

from __future__ import annotations

import re

from app.models.schemas import ClientContext, EvidenceChunk
from app.services.official_knowledge import temenos_official_chunks
from app.services.embedding_service import get_embedder
from app.services.qdrant_service import get_qdrant


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _lexical_fallback(
    qdrant,
    query: str,
    section_title: str,
    keywords: list[str],
    proposal_family: str,
    top_k: int,
) -> list[EvidenceChunk]:
    query_tokens = _tokens(" ".join([query, section_title, " ".join(keywords or [])]))
    if not query_tokens:
        query_tokens = _tokens(section_title)

    scored: list[tuple[float, EvidenceChunk]] = []
    for payload in qdrant.scroll_payloads(limit=5000):
        norm = qdrant.normalize_payload(payload)
        text = norm["text"]
        if not text:
            continue

        haystack = " ".join(
            part
            for part in (norm["text"], norm["section"], norm["source"], norm["family"])
            if part
        ).lower()
        tokens = _tokens(haystack)
        overlap = len(query_tokens & tokens)
        if overlap == 0:
            continue

        score = float(overlap)
        section_lower = norm["section"].lower()
        family_lower = norm["family"].lower()

        if section_title and section_title.lower() in section_lower:
            score += 4.0
        if proposal_family and family_lower and proposal_family.lower() in family_lower:
            score += 1.5
        if keywords:
            keyword_hits = sum(1 for kw in keywords if kw and kw.lower() in haystack)
            score += float(keyword_hits) * 0.75

        scored.append(
            (
                score,
                EvidenceChunk(
                    text=text,
                    score=score,
                    source_proposal=norm["source"],
                    source_section=norm["section"],
                    proposal_family=norm["family"],
                    chunk_id=str(
                        payload.get("chunk_hash")
                        or payload.get("id")
                        or payload.get("point_id")
                        or ""
                    ),
                ),
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _score, chunk in scored[:top_k]]


def retrieve_for_section(
    section_title: str,
    keywords: list[str],
    context: ClientContext,
    proposal_family: str,
    top_k: int = 6,
) -> list[EvidenceChunk]:
    qdrant = get_qdrant()

    # Build a section-specific query, not a generic one.
    query_parts = [
        section_title,
        " ".join(keywords or []),
        proposal_family,
        context.project_type,
    ]
    query = " ".join(p for p in query_parts if p).strip()

    try:
        vector = get_embedder().embed_query(query)
        chunks = qdrant.search(vector, top_k=top_k, keywords=keywords)
    except Exception:
        chunks = []

    if not chunks:
        chunks = _lexical_fallback(
            qdrant=qdrant,
            query=query,
            section_title=section_title,
            keywords=keywords,
            proposal_family=proposal_family,
            top_k=top_k,
        )

    temenos_chunks = temenos_official_chunks(query=query, top_k=max(2, top_k // 2))
    if temenos_chunks:
        chunks = temenos_chunks + chunks

    # Light re-rank: nudge chunks whose family matches.
    if proposal_family:
        fam = proposal_family.lower()
        chunks.sort(
            key=lambda c: (c.proposal_family.lower() == fam, c.score), reverse=True
        )
    return chunks
