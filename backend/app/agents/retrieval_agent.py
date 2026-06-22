"""Agent 6 - Retrieval Agent.

For a single section, retrieve only the relevant chunks from the knowledge
base (not a generic query). We first try the shared embedding path used at
ingestion, then fall back to lexical matching over stored payloads so Railway
deployments still return evidence when the embedding model is unavailable.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from app.config import get_settings
from app.models.schemas import ClientContext, EvidenceChunk
from app.services.official_knowledge import temenos_official_chunks
from app.services.embedding_service import get_embedder
from app.services.qdrant_service import get_qdrant

_GREENFIELD_TERMS = (
    "greenfield bank",
    "greenfield environment",
    "greenfield implementation",
    "brand-new bank",
    "brand new bank",
    "new bank",
    "new digital bank",
    "rapid market entry",
    "market entry",
    "mvp launch",
)

_TIM_TERMS = (
    "tim",
    "temenos implementation methodology",
    "project preparation",
    "business process review",
    "business process transformation",
    "business process alignment",
    "model bank",
    "adopt not adapt",
)


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def _token_list(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


def _lexical_fallback(
    qdrant,
    query: str,
    section_title: str,
    keywords: list[str],
    proposal_family: str,
    top_k: int,
) -> list[EvidenceChunk]:
    query_terms = _token_list(" ".join([query, section_title, " ".join(keywords or [])]))
    if not query_terms:
        query_terms = _token_list(section_title)
    query_tokens = set(query_terms)

    docs: list[tuple[dict[str, str], list[str], str]] = []
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
        docs.append(
            (
                {**norm, "point_id": str(payload.get("_point_id") or "")},
                _token_list(haystack),
                haystack,
            )
        )

    if not docs:
        return []

    avgdl = sum(len(tokens) for _norm, tokens, _haystack in docs) / max(len(docs), 1)
    doc_freq = Counter()
    for _norm, tokens, _haystack in docs:
        doc_freq.update(set(tokens))

    scored: list[tuple[float, EvidenceChunk]] = []
    k1 = 1.4
    b = 0.72
    total_docs = len(docs)

    for norm, tokens, haystack in docs:
        text = norm["text"]
        counts = Counter(tokens)
        dl = len(tokens) or 1
        score = 0.0
        for term in query_tokens:
            tf = counts.get(term, 0)
            if tf == 0:
                continue
            df = doc_freq.get(term, 0)
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1 - b + b * (dl / max(avgdl, 1)))
            score += idf * ((tf * (k1 + 1)) / denom)

        section_lower = norm["section"].lower()
        family_lower = norm["family"].lower()

        if section_title and section_title.lower() in section_lower:
            score += 4.0
        if proposal_family and family_lower and proposal_family.lower() in family_lower:
            score += 1.5
        if keywords:
            keyword_hits = sum(1 for kw in keywords if kw and kw.lower() in haystack)
            score += float(keyword_hits) * 0.75
        tim_hits = sum(1 for term in _TIM_TERMS if term in haystack)
        score += float(tim_hits) * 1.5

        scored.append(
            (
                score,
                EvidenceChunk(
                    text=text,
                    score=score,
                    summary=" ".join(text.split()[:12]) + ("..." if len(text.split()) > 12 else ""),
                    source_proposal=norm["source"],
                    source_section=norm["section"],
                    proposal_family=norm["family"],
                    chunk_id=norm["point_id"],
                    source_type="document_bm25",
                ),
            )
        )

    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _score, chunk in scored[:top_k]]


def _greenfield_allowed(context: ClientContext, query: str) -> bool:
    if context.client_profile == "greenfield":
        return True
    explicit = " ".join(
        [
            query,
            context.implementation_context or "",
            context.special_instructions or "",
        ]
    ).lower()
    return any(term in explicit for term in ("greenfield", "new bank", "new licence", "new license"))


def _is_greenfield_specific(chunk: EvidenceChunk) -> bool:
    haystack = " ".join(
        [
            chunk.text or "",
            chunk.summary or "",
            chunk.source_section or "",
            chunk.source_proposal or "",
        ]
    ).lower()
    return any(term in haystack for term in _GREENFIELD_TERMS)


def _filter_context_mismatch(
    chunks: list[EvidenceChunk], context: ClientContext, query: str
) -> list[EvidenceChunk]:
    if _greenfield_allowed(context, query):
        return chunks
    if context.client_profile not in {"established", "unknown"}:
        return chunks
    return [chunk for chunk in chunks if not _is_greenfield_specific(chunk)]


def retrieve_for_section(
    section_title: str,
    keywords: list[str],
    context: ClientContext,
    proposal_family: str,
    top_k: int = 6,
    include_temenos_official: bool = False,
    use_hybrid_retrieval: bool = True,
) -> list[EvidenceChunk]:
    qdrant = get_qdrant()
    settings = get_settings()

    # Build a section-specific query, not a generic one.
    query_parts = [
        section_title,
        " ".join(keywords or []),
        proposal_family,
        context.project_type,
        context.implementation_context,
        context.canonical_product,
        " ".join(context.intake.launch_segments or []),
        " ".join(context.intake.phase_1_products or []),
        " ".join(context.intake.phase_2_products or []),
        " ".join(context.intake.regulatory_interfaces_phase_1 or []),
        " ".join(context.intake.regulatory_interfaces_phase_2 or []),
        " ".join(context.intake.channels_phase_1 or []),
        " ".join(context.intake.channels_phase_2 or []),
        context.intake.middleware_platform,
        context.intake.reporting_platform,
        context.intake.database_platform,
        context.intake.hosting_model,
        context.intake.container_platform,
        context.intake.data_warehouse_platform,
        context.intake.implementation_methodology,
        context.intake.delivery_model,
        context.intake.launch_plan,
        context.intake.questionnaire_notes,
    ]
    query = " ".join(p for p in query_parts if p).strip()

    chunks: list[EvidenceChunk] = []
    try:
        if settings.embedding_provider.strip().lower() == "qdrant":
            chunks = qdrant.search_text(
                query_text=query,
                model=settings.embedding_model,
                top_k=top_k,
            )
        else:
            vector = get_embedder().embed_query(query)
            chunks = qdrant.search(vector, top_k=top_k, keywords=keywords)
    except Exception:
        chunks = []

    if use_hybrid_retrieval or not chunks:
        lexical = _lexical_fallback(
            qdrant=qdrant,
            query=query,
            section_title=section_title,
            keywords=keywords,
            proposal_family=proposal_family,
            top_k=max(top_k, 10),
        )
        by_id: dict[str, EvidenceChunk] = {}
        for chunk in chunks:
            key = chunk.chunk_id or f"semantic:{chunk.source_section}:{chunk.text[:80]}"
            by_id[key] = chunk
        for chunk in lexical:
            key = chunk.chunk_id or f"bm25:{chunk.source_section}:{chunk.text[:80]}"
            if key in by_id:
                existing = by_id[key]
                existing.score = max(existing.score, chunk.score) + 0.35
                existing.source_type = "document_hybrid"
            else:
                by_id[key] = chunk
        chunks = list(by_id.values())

    if include_temenos_official:
        temenos_chunks = temenos_official_chunks(query=query, top_k=max(2, top_k // 2))
        chunks = temenos_chunks + chunks

    chunks = _filter_context_mismatch(chunks, context, query)

    # Light re-rank: nudge chunks whose family matches.
    if proposal_family:
        fam = proposal_family.lower()
        chunks.sort(
            key=lambda c: (c.proposal_family.lower() == fam, c.score), reverse=True
        )
    return chunks[: max(top_k, 8)]
