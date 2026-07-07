from __future__ import annotations

from app.agents.section_writer import _prune_unsupported_sentences, _validation_issues
from app.models.schemas import ClientContext, EvidenceChunk, GenerateSectionRequest, IntakeProfile


def _request() -> GenerateSectionRequest:
    return GenerateSectionRequest(
        section_title="Scope of Work",
        keywords=["scope", "upgrade", "testing", "cutover"],
        context=ClientContext(
            client_name="Bank ABC",
            industry="Banking",
            project_type="Technical Upgrade",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(),
        ),
        proposal_family="Temenos",
        prompt="Prepare a scope of work section for a Temenos technical upgrade.",
        require_evidence=True,
    )


def test_prune_unsupported_sentences_removes_unbacked_claims() -> None:
    req = _request()
    evidence = [
        EvidenceChunk(
            text=(
                "SYS will execute a like-for-like technical upgrade. "
                "The scope includes environment readiness assessment, upgrade analysis, "
                "technical uplift, testing, cutover, and post-go-live support."
            ),
            score=1.0,
            summary="Scope includes upgrade activities",
            source_section="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
            source_document="Alkuraimi.docx",
            source_proposal="Alkuraimi.docx",
            proposal_family="Temenos",
        )
    ]
    content = (
        "The scope includes environment readiness assessment, upgrade analysis, and cutover support. "
        "A dedicated technical review board will publish weekly issue aging reports for all squads."
    )

    pruned = _prune_unsupported_sentences(content, req, evidence)

    assert "environment readiness assessment" in pruned
    assert "issue aging reports" not in pruned


def test_validation_allows_grounded_scope_section() -> None:
    req = _request()
    evidence = [
        EvidenceChunk(
            text=(
                "SYS will execute a like-for-like technical upgrade. "
                "The scope includes environment readiness assessment, upgrade analysis, "
                "technical uplift, testing, cutover, and post-go-live support."
            ),
            score=1.0,
            summary="Scope includes upgrade activities",
            source_section="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
            source_document="Alkuraimi.docx",
            source_proposal="Alkuraimi.docx",
            proposal_family="Temenos",
        )
    ]
    content = (
        "Bank ABC requires a like-for-like technical upgrade of Temenos Transact. "
        "The scope covers environment readiness assessment, upgrade analysis, technical uplift, "
        "testing, cutover, and post-go-live support."
    )

    issues = _validation_issues(content, req, evidence)

    assert not [issue for issue in issues if "weak evidence grounding" in issue]
