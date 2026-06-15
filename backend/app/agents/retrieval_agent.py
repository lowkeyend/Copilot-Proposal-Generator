"""Agent 6 — Retrieval Agent.

For a single section, retrieve only the relevant chunks from the knowledge
base (not a generic query). We build a focused query from the section title +
its keyword hints + client/project context, embed it with the same bge model
used at ingestion, and search Qdrant. Returns evidence chunks carrying their
source proposal and section so the UI evidence drawer can show provenance.
"""

from __future__ import annotations

from app.models.schemas import ClientContext, EvidenceChunk
from app.services.embedding_service import get_embedder
from app.services.qdrant_service import get_qdrant


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
    except Exception:
        # Embedding model unavailable -> no evidence rather than a hard failure.
        return []

    chunks = qdrant.search(vector, top_k=top_k, keywords=keywords)

    # Light re-rank: nudge chunks whose family matches.
    if proposal_family:
        fam = proposal_family.lower()
        chunks.sort(
            key=lambda c: (c.proposal_family.lower() == fam, c.score), reverse=True
        )
    return chunks
