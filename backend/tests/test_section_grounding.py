from __future__ import annotations

from app.agents.section_writer import (
    _clean_model_output,
    _compile_reference_layout,
    _prune_unsupported_sentences,
    _validation_issues,
)
from app.agents.reference_adapter import _deterministic_patch, _effective_versions, _patch_reference_blocks
from app.models.schemas import AdaptSectionRequest, ClientContext, EvidenceChunk, GenerateSectionRequest, IntakeProfile, TemplateBlock


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


def test_validation_rejects_unsupported_consulting_benefits() -> None:
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
        "This upgrade is intended to deliver improved performance, enhanced architecture, "
        "stronger security controls, and access to new product capabilities."
    )

    issues = _validation_issues(content, req, evidence)

    assert any("improved performance" in issue for issue in issues)


def test_clean_model_output_converts_html_lists_to_bullets() -> None:
    cleaned = _clean_model_output(
        "<section><ul><li>Environment Readiness Assessment</li><li>Upgrade Analysis</li></ul></section>",
        "Scope of Work",
    )

    assert "<li>" not in cleaned.lower()
    assert "- Environment Readiness Assessment" in cleaned


def test_scope_validation_requires_reference_structure() -> None:
    req = _request()
    evidence = [
        EvidenceChunk(
            text=(
                "Environment Readiness Assessment. Upgrade Analysis. Core Technical Upgrade. "
                "Customization & Interface Retrofit. Testing. Deployment & Go-Live. Post Go-Live Support."
            ),
            score=1.0,
            summary="Scope structure",
            source_section="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
            source_document="Alkuraimi.docx",
            source_proposal="Alkuraimi.docx",
            proposal_family="Temenos",
        )
    ]
    content = "The engagement will proceed through a generic implementation approach with phased delivery."

    issues = _validation_issues(content, req, evidence)

    assert any("reference section structure" in issue for issue in issues)


def test_compile_reference_layout_for_scope_of_work() -> None:
    req = _request()
    evidence = [
        EvidenceChunk(
            text="SYS will execute a like-for-like technical upgrade of Alkuraimi Bank’s Temenos Transact Core Banking platform from the current release to the latest agreed Temenos release. The scope includes:",
            score=1.0,
            summary="Scope structure",
            source_section="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
            source_document="Alkuraimi.docx",
            source_proposal="Alkuraimi.docx",
            proposal_family="Temenos",
        ),
        EvidenceChunk(
            text="Hardware, operating system, middleware, compiler, and database compatibility assessment Review of infrastructure readiness for target release",
            score=1.0,
            summary="Environment Readiness Assessment",
            source_section="Environment Readiness Assessment",
            source_document="Alkuraimi.docx",
            source_proposal="Alkuraimi.docx",
            proposal_family="Temenos",
        ),
        EvidenceChunk(
            text="Inventory of existing modules, parameters, local developments, and integrations Upgrade impact assessment on customizations and interfaces",
            score=1.0,
            summary="Upgrade Analysis",
            source_section="Upgrade Analysis",
            source_document="Alkuraimi.docx",
            source_proposal="Alkuraimi.docx",
            proposal_family="Temenos",
        ),
    ]

    compiled = _compile_reference_layout(req, evidence)

    assert "## Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ" in compiled
    assert "### Environment Readiness Assessment" in compiled
    assert "### Upgrade Analysis" in compiled


def test_deterministic_patch_preserves_scope_structure() -> None:
    req = _request().model_copy(
        update={
            "context": ClientContext(
                client_name="QIB",
                industry="Banking",
                project_type="Technical Upgrade",
                client_profile="established",
                canonical_product="Temenos Transact",
                intake=IntakeProfile(current_version="R20", target_version="R24"),
            ),
            "reference_content": (
                "## Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ\n\n"
                "SYS will execute a like-for-like technical upgrade of Alkuraimi Bank's Temenos Transact Core Banking platform from the current release to the latest agreed Temenos release.\n\n"
                "The scope includes:\n\n"
                "### Environment Readiness Assessment\n\n"
                "Hardware, operating system, middleware, compiler, and database compatibility assessment\n"
                "Review of infrastructure readiness for target release\n\n"
                "### Upgrade Analysis\n\n"
                "Inventory of existing modules, parameters, local developments, and integrations\n"
                "Upgrade impact assessment on customizations and interfaces\n"
            ),
        }
    )

    patched = _deterministic_patch(req, [])

    assert "## Core Upgrade: Temenos Transact R20 TAFJ to R24 TAFJ" in patched
    assert "QIB" in patched
    assert "### Environment Readiness Assessment" in patched
    assert "### Upgrade Analysis" in patched
    assert "Alkuraimi" not in patched
    assert "R24 target release" not in patched


def test_prompt_version_override_takes_priority_over_context() -> None:
    req = AdaptSectionRequest(
        section_title="Scope of Work",
        reference_content="## Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
        reference_blocks=[],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Technical Upgrade",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R19", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt="Prepare a technical upgrade proposal for QIB and change the upgrade from R17 to R24.",
    )

    current_version, target_version = _effective_versions(req)
    patched = _deterministic_patch(req, [])

    assert current_version == "R17"
    assert target_version == "R24"
    assert "R17" in patched
    assert "R19" not in patched


def test_patch_reference_blocks_preserves_list_structure() -> None:
    req = AdaptSectionRequest(
        section_title="Scope of Work",
        reference_content="",
        reference_blocks=[
            TemplateBlock(kind="heading", section_title="Scope of Work", heading_level=2, text="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ", order=0),
            TemplateBlock(kind="paragraph", section_title="Scope of Work", text="SYS will execute a like-for-like technical upgrade of Alkuraimi Bank's Temenos Transact Core Banking platform from the current release to the latest agreed Temenos release.", order=1),
            TemplateBlock(kind="heading", section_title="Scope of Work", heading_level=3, text="Environment Readiness Assessment", order=2),
            TemplateBlock(kind="list", section_title="Scope of Work", text="Hardware, operating system, middleware, compiler, and database compatibility assessment", items=["Hardware, operating system, middleware, compiler, and database compatibility assessment"], order=3),
            TemplateBlock(kind="list", section_title="Scope of Work", text="Review of infrastructure readiness for target release", items=["Review of infrastructure readiness for target release"], order=4),
        ],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Technical Upgrade",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R20", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt="Prepare a technical upgrade proposal for QIB. Replace all reference client names with QIB, change the upgrade from R20 to R24.",
    )

    blocks = _patch_reference_blocks(req, [])

    assert blocks[0].text == "Core Upgrade: Temenos Transact R20 TAFJ to R24 TAFJ"
    assert "QIB" in blocks[1].text
    assert blocks[3].kind == "list"
    assert blocks[3].items == ["Hardware, operating system, middleware, compiler, and database compatibility assessment"]
    assert blocks[4].items == ["Review of infrastructure readiness for target release"]
