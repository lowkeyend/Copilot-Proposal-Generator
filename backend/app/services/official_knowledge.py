"""Supplemental official Temenos knowledge.

These are concise paraphrased summaries derived from official Temenos pages.
They are intentionally short and source-attributed so the proposal generator
can ground Temenos-related sections even when the customer KB is thin or the
embedding model is unavailable.
"""

from __future__ import annotations

import re

from app.models.schemas import EvidenceChunk


_OFFICIAL_FACTS: list[EvidenceChunk] = [
    EvidenceChunk(
        chunk_id="temenos-home",
        source_proposal="Temenos official website",
        source_section="Home",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Home",
        source_type="temenos_official",
        text=(
            "Temenos presents itself as a cloud-native and AI-driven banking "
            "software leader, serving a large global base of banks across core, "
            "digital, and wealth use cases."
        ),
    ),
    EvidenceChunk(
        chunk_id="temenos-core",
        source_proposal="Temenos official website",
        source_section="Core Banking",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Core Banking",
        source_type="temenos_official",
        text=(
            "Temenos Core Banking is modular and scalable. The official product "
            "pages describe long-running core functionality, cloud-native "
            "capabilities, and flexible deployment across cloud, SaaS, and "
            "on-premise environments."
        ),
    ),
    EvidenceChunk(
        chunk_id="temenos-platform",
        source_proposal="Temenos official website",
        source_section="Banking Platform",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Banking Platform",
        source_type="temenos_official",
        text=(
            "The Temenos Banking Platform is positioned as a modern foundation "
            "for banks that want to reduce modernization risk while moving "
            "toward a legacy-free architecture."
        ),
    ),
    EvidenceChunk(
        chunk_id="temenos-cloud",
        source_proposal="Temenos official website",
        source_section="Cloud",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Cloud",
        source_type="temenos_official",
        text=(
            "Temenos highlights cloud-native, cloud-agnostic deployment and "
            "emphasizes scalability, efficiency, and support for SaaS delivery."
        ),
    ),
    EvidenceChunk(
        chunk_id="temenos-digital",
        source_proposal="Temenos official website",
        source_section="Digital Banking",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Digital Banking",
        source_type="temenos_official",
        text=(
            "Temenos Digital Banking is described as a cloud-native platform "
            "for delivering AI-powered financial services and faster digital "
            "customer experiences."
        ),
    ),
    EvidenceChunk(
        chunk_id="temenos-products",
        source_proposal="Temenos official website",
        source_section="Products",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Products",
        source_type="temenos_official",
        text=(
            "Temenos says its products span core, digital, AI, risk, data, "
            "pricing, compliance, and wealth, delivered through an end-to-end "
            "banking platform."
        ),
    ),
    EvidenceChunk(
        chunk_id="temenos-transact",
        source_proposal="Temenos official website",
        source_section="Temenos Transact",
        proposal_family="Temenos",
        score=0.0,
        summary="Temenos official website - Temenos Transact",
        source_type="temenos_official",
        text=(
            "Temenos Transact is presented as the market-leading core banking "
            "solution, with broad functional coverage across retail, corporate, "
            "treasury, wealth, and payments."
        ),
    ),
]


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


def temenos_official_chunks(query: str, top_k: int = 4) -> list[EvidenceChunk]:
    query_tokens = _tokens(query)
    scored: list[tuple[float, EvidenceChunk]] = []
    for chunk in _OFFICIAL_FACTS:
        haystack = _tokens(
            " ".join(
                [chunk.text, chunk.source_section, chunk.source_proposal, chunk.proposal_family]
            )
        )
        overlap = len(query_tokens & haystack)
        if overlap == 0:
            continue
        score = float(overlap)
        if "temenos" in query.lower() or "transact" in query.lower():
            score += 3.0
        scored.append((score, chunk.model_copy(update={"score": score})))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _score, chunk in scored[:top_k]]
