from __future__ import annotations

from types import SimpleNamespace

from app.agents.pattern_discovery import _extra_curated_patterns
from app.agents.retrieval_agent import retrieve_for_section
from app.models.schemas import ClientContext, IntakeProfile
from app.models.schemas import EvidenceChunk


def test_upgrade_technical_template_sections() -> None:
    templates = _extra_curated_patterns()
    assert len(templates) == 1
    template = templates[0]
    assert template.name == "Technical Upgrade"
    assert [section.title for section in template.sections] == [
        "Executive Summary",
        "Introduction",
        "Company Profile",
        "Scope of Work",
        "Proposed Solution",
        "Upgrade Methodology",
        "Project Timeline",
        "Project Governance",
        "Assumptions",
    ]


def test_selected_document_retrieval_stays_within_selected_docs(monkeypatch) -> None:
    selected_chunk = {
        "text": "The current Temenos version is Release R20 and the target environment is R26.",
        "section": "Technology Components",
        "source": "Selected RFP",
        "family": "Temenos",
    }
    other_chunk = {
        "text": "This unrelated document mentions a different launch approach.",
        "section": "General Overview",
        "source": "Other Bank Proposal",
        "family": "Temenos",
    }

    class FakeQdrant:
        def search_text(self, query_text: str, model: str, top_k: int = 6):
            return [
                EvidenceChunk(
                    text=other_chunk["text"],
                    summary="Unrelated chunk",
                    score=9.0,
                    source_proposal=other_chunk["source"],
                    source_section=other_chunk["section"],
                    source_document="Other Doc",
                    proposal_family=other_chunk["family"],
                    chunk_id="other",
                )
            ]

        def search(self, query_vector, top_k: int = 6, keywords=None):
            return []

        def scroll_payloads(self, limit: int = 5000):
            return [
                {
                    "text": selected_chunk["text"],
                    "section": selected_chunk["section"],
                    "source": selected_chunk["source"],
                    "family": selected_chunk["family"],
                    "document_name": "Selected Doc",
                    "_point_id": "selected-1",
                },
                {
                    "text": other_chunk["text"],
                    "section": other_chunk["section"],
                    "source": other_chunk["source"],
                    "family": other_chunk["family"],
                    "document_name": "Other Doc",
                    "_point_id": "other-1",
                },
            ]

        @staticmethod
        def normalize_payload(payload):
            return {
                "text": payload["text"],
                "source": payload["source"],
                "document": payload.get("document_name", ""),
                "section": payload["section"],
                "family": payload["family"],
            }

    fake_settings = SimpleNamespace(embedding_provider="qdrant", embedding_model="dummy")
    fake_context = ClientContext(
        client_name="Bank Alfalah",
        industry="Banking",
        client_profile="established",
        canonical_product="Temenos Transact",
        selected_documents=["Selected Doc"],
        intake=IntakeProfile(),
    )

    monkeypatch.setattr("app.agents.retrieval_agent.get_qdrant", lambda: FakeQdrant())
    monkeypatch.setattr("app.agents.retrieval_agent.get_settings", lambda: fake_settings)

    chunks = retrieve_for_section(
        section_title="Current Version",
        keywords=["version", "release"],
        context=fake_context,
        proposal_family="Temenos",
        top_k=4,
        include_temenos_official=False,
        use_hybrid_retrieval=True,
    )

    assert chunks
    assert all(chunk.source_document == "Selected Doc" for chunk in chunks)
    assert any("R20" in chunk.text for chunk in chunks)


def test_selected_document_retrieval_matches_without_extension(monkeypatch) -> None:
    class FakeQdrant:
        def search_text(self, query_text: str, model: str, top_k: int = 6):
            return []

        def search(self, query_vector, top_k: int = 6, keywords=None):
            return []

        def scroll_payloads(self, limit: int = 5000):
            return [
                {
                    "text": "SYS will execute a like-for-like technical upgrade.",
                    "section": "Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
                    "source": "Alkuraimibank - Core Banking Upgrade(1).docx",
                    "family": "Uploaded Knowledge",
                    "document_name": "Alkuraimibank - Core Banking Upgrade(1).docx",
                    "_point_id": "alk-1",
                }
            ]

        @staticmethod
        def normalize_payload(payload):
            return {
                "text": payload["text"],
                "source": payload["source"],
                "document": payload.get("document_name", ""),
                "section": payload["section"],
                "family": payload["family"],
            }

    fake_settings = SimpleNamespace(embedding_provider="qdrant", embedding_model="dummy")
    fake_context = ClientContext(
        client_name="Bank ABC",
        industry="Banking",
        client_profile="established",
        canonical_product="Temenos Transact",
        selected_documents=["Alkuraimibank - Core Banking Upgrade(1)"],
        intake=IntakeProfile(),
    )

    monkeypatch.setattr("app.agents.retrieval_agent.get_qdrant", lambda: FakeQdrant())
    monkeypatch.setattr("app.agents.retrieval_agent.get_settings", lambda: fake_settings)

    chunks = retrieve_for_section(
        section_title="Scope of Work",
        keywords=["scope", "upgrade"],
        context=fake_context,
        proposal_family="Temenos",
        top_k=4,
        include_temenos_official=False,
        use_hybrid_retrieval=True,
    )

    assert chunks
    assert all("Alkuraimibank" in chunk.source_document for chunk in chunks)
