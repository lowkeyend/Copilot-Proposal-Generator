from __future__ import annotations
import asyncio

from app.agents.section_writer import (
    _clean_model_output,
    _compile_reference_layout,
    _prune_unsupported_sentences,
    _validation_issues,
)
from app.agents.reference_adapter import _allow_heading_edit, _deterministic_patch, _effective_versions, _is_major_scope_shift, _needs_semantic_block_patch, _patch_reference_blocks, _prompt_requests_upgrade_wording, _semantic_patch_blocks, _should_use_patch_only, adapt_section
from app.models.schemas import AdaptSectionRequest, ClientContext, EvidenceChunk, GenerateSectionRequest, IntakeProfile, ProposalBrief, TemplateBlock


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


def test_preserve_structure_prompt_stays_in_patch_mode() -> None:
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
        prompt="Prepare a technical upgrade proposal for QIB. Replace all reference client names with QIB, change the upgrade from R17 to R24, preserve the reference structure and wording style.",
    )

    assert _should_use_patch_only(req) is True


def test_master_prompt_triggers_semantic_patch() -> None:
    req = AdaptSectionRequest(
        section_title="Executive Summary",
        reference_content="",
        reference_blocks=[],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Technical Upgrade",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R20", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt="Prepare a technical upgrade proposal for QIB, emphasize phased MVP delivery, and reflect the selected documents while preserving the reference structure and wording style.",
    )

    assert _needs_semantic_block_patch(req) is True


def test_semantic_patch_blocks_applies_prompt(monkeypatch) -> None:
    class FakeLLM:
        async def chat_json(self, *args, **kwargs):
            return {
                "patches": [
                    {"block_id": "p1", "text": "Systems Limited is pleased to submit this proposal for QIB, delivered through a phased MVP approach."},
                    {"block_id": "l1", "items": ["Phased MVP delivery", "Temenos Transact upgrade from R20 to R24"]},
                ]
            }

    monkeypatch.setattr("app.agents.reference_adapter.get_llm", lambda: FakeLLM())

    req = AdaptSectionRequest(
        section_title="Executive Summary",
        reference_content="",
        reference_blocks=[],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Technical Upgrade",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R20", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt="Prepare a technical upgrade proposal for QIB, emphasize phased MVP delivery, and preserve the reference structure and wording style.",
    )
    blocks = [
        TemplateBlock(block_id="p1", kind="paragraph", section_title="Executive Summary", text="Systems Limited is pleased to submit this proposal.", order=0),
        TemplateBlock(block_id="l1", kind="list", section_title="Executive Summary", text="Legacy bullet", items=["Legacy bullet"], order=1),
    ]
    patched = asyncio.run(
        _semantic_patch_blocks(
            req,
            ProposalBrief(must_change=["Apply phased MVP delivery wording."]),
            ["[Executive Summary] phased MVP delivery is requested"],
            blocks,
        )
    )

    assert "QIB" in patched[0].text
    assert "phased MVP" in patched[0].text
    assert patched[1].items == ["Phased MVP delivery", "Temenos Transact upgrade from R20 to R24"]


def test_heading_edit_only_allowed_when_explicit() -> None:
    req = AdaptSectionRequest(
        section_title="Proposed Solution",
        reference_content="",
        reference_blocks=[],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Technical Upgrade",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(),
        ),
        proposal_family="Temenos",
        prompt='Rename heading "Upgrade Analysis" to "Forex Module Scope" and preserve the reference structure.',
    )

    assert _allow_heading_edit(req, "Upgrade Analysis") is True
    assert _allow_heading_edit(req, "Environment Readiness Assessment") is False


def test_semantic_patch_blocks_can_rename_one_heading(monkeypatch) -> None:
    class FakeLLM:
        async def chat_json(self, *args, **kwargs):
            return {
                "patches": [
                    {"block_id": "h2", "text": "Forex Module Scope"},
                    {"block_id": "p1", "text": "The proposed solution includes the addition of a Forex module for QIB."},
                ]
            }

    monkeypatch.setattr("app.agents.reference_adapter.get_llm", lambda: FakeLLM())

    req = AdaptSectionRequest(
        section_title="Proposed Solution",
        reference_content="",
        reference_blocks=[],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Implementation",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(),
        ),
        proposal_family="Temenos",
        prompt='Rename heading "Upgrade Analysis" to "Forex Module Scope". Add a Forex module in the solution while preserving the reference structure and wording style.',
    )
    blocks = [
        TemplateBlock(block_id="h1", kind="heading", section_title="Proposed Solution", heading_level=2, text="Proposed Solution", order=0, editable=False),
        TemplateBlock(block_id="h2", kind="heading", section_title="Proposed Solution", heading_level=3, text="Upgrade Analysis", order=1, editable=False),
        TemplateBlock(block_id="p1", kind="paragraph", section_title="Proposed Solution", text="Legacy solution text.", order=2),
    ]
    patched = asyncio.run(
        _semantic_patch_blocks(
            req,
            ProposalBrief(must_change=["Rename Upgrade Analysis heading and add Forex module content."]),
            ["[Forex Module] Add Forex module within the proposed solution scope."],
            blocks,
        )
    )

    assert patched[0].text == "Proposed Solution"
    assert patched[1].text == "Forex Module Scope"
    assert "Forex module" in patched[2].text


def test_patch_reference_blocks_applies_explicit_module_addition() -> None:
    req = AdaptSectionRequest(
        section_title="Scope of Work",
        reference_content="",
        reference_blocks=[
            TemplateBlock(block_id="h1", kind="heading", section_title="Scope of Work", heading_level=2, text="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ", order=0, editable=False),
            TemplateBlock(block_id="p1", kind="paragraph", section_title="Scope of Work", text="SYS will execute a like-for-like technical upgrade of Alkuraimi Bank's Temenos Transact Core Banking platform from the current release to the latest agreed Temenos release.", order=1),
            TemplateBlock(block_id="h2", kind="heading", section_title="Scope of Work", heading_level=3, text="Upgrade Analysis", order=2, editable=False),
            TemplateBlock(block_id="l1", kind="list", section_title="Scope of Work", text="Inventory of existing modules, parameters, local developments, and integrations", items=["Inventory of existing modules, parameters, local developments, and integrations"], order=3),
        ],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Implementation",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R20", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt='Prepare a proposal for QIB. Preserve the reference structure and wording style. Add the Forex module where supported by the selected documents. Rename heading "Upgrade Analysis" to "Forex Module Scope".',
    )

    patched = _patch_reference_blocks(req, ["[Forex Module] Add Forex module within the selected scope."])

    assert patched[1].text.lower().find("forex module") != -1
    assert patched[2].text == "Forex Module Scope"
    assert any("Forex module" in item for item in patched[3].items)


def test_module_only_prompt_disables_upgrade_wording() -> None:
    req = AdaptSectionRequest(
        section_title="Executive Summary",
        reference_content="",
        reference_blocks=[],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Implementation",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R20", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt="Prepare a proposal for QIB. Add the Forex module where supported by the selected documents. Preserve the reference structure and wording style.",
    )

    assert _prompt_requests_upgrade_wording(req) is False


def test_module_only_scope_omits_upgrade_versions() -> None:
    req = AdaptSectionRequest(
        section_title="Scope of Work",
        reference_content="",
        reference_blocks=[
            TemplateBlock(block_id="h1", kind="heading", section_title="Scope of Work", heading_level=2, text="Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ", order=0, editable=False),
            TemplateBlock(block_id="p1", kind="paragraph", section_title="Scope of Work", text="SYS will execute a like-for-like technical upgrade of Alkuraimi Bank's Temenos Transact Core Banking platform from the current release to the latest agreed Temenos release.", order=1),
        ],
        context=ClientContext(
            client_name="QIB",
            industry="Banking",
            project_type="Implementation",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(current_version="R20", target_version="R24"),
        ),
        proposal_family="Temenos",
        prompt='Prepare a proposal for QIB. Add the Forex module where supported by the selected documents. Rename heading "Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ" to "Forex Module Scope". Preserve the reference structure and wording style.',
    )

    patched = _patch_reference_blocks(req, ["[Forex Module] Add Forex module within the selected scope."])

    assert "R20" not in patched[0].text
    assert "R24" not in patched[0].text
    assert "Forex Module Scope" == patched[0].text
    assert "technical upgrade" not in patched[1].text.lower()
    assert "forex module" in patched[1].text.lower()


def test_module_prompt_triggers_major_scope_shift() -> None:
    req = AdaptSectionRequest(
        section_title="Scope of Work",
        reference_content="## Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
        reference_blocks=[],
        context=ClientContext(
            client_name="MMBL",
            industry="Banking",
            project_type="Implementation",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(),
        ),
        proposal_family="Temenos",
        prompt="Prepare a proposal for MMBL and add the Forex module based on the selected documents.",
    )

    assert _is_major_scope_shift(req) is True


def test_adapt_section_uses_grounded_rewrite_for_module_scope(monkeypatch) -> None:
    class FakeLLM:
        available = True

        def resolve_model(self, model):
            return model or "fake-model"

        async def chat_json(self, *args, **kwargs):
            return {
                "summary": "Add Forex module scope for MMBL.",
                "must_change": ["Replace upgrade scope with Forex module implementation scope."],
                "must_preserve": ["Keep proposal tone factual and operational."],
                "forbidden_claims": [],
                "prompt_directives": ["Add Forex module scope."],
            }

        async def chat(self, *args, **kwargs):
            return (
                "MMBL requires implementation of the Temenos Treasury Forex capability to support deal capture, "
                "lifecycle processing, and operational control for spot, forward, and swap transactions. "
                "The scope covers product configuration, workflow setup, limit and control parameterization, "
                "interface alignment with upstream and downstream systems, and deployment support for the agreed operating model.\n\n"
                "The implementation activities include:\n"
                "- configuration of Forex products, transaction events, and settlement rules;\n"
                "- validation of interfaces, accounting entries, and operational controls;\n"
                "- execution support for testing, cutover preparation, and controlled go-live."
            )

    monkeypatch.setattr("app.agents.reference_adapter.get_llm", lambda: FakeLLM())
    monkeypatch.setattr(
        "app.agents.reference_adapter.retrieve_for_section",
        lambda **kwargs: [
            EvidenceChunk(
                text=(
                    "Temenos Treasury Module's Forex component covers deal capture, processing, risk management, "
                    "regulatory compliance, and support for spot, forward, and swap deals with automated defaults "
                    "and lifecycle management."
                ),
                score=1.0,
                summary="Forex component scope",
                source_section="mmbl forex info",
                source_document="mmbl forex info.txt",
                source_proposal="mmbl forex info.txt",
                proposal_family="Temenos",
            )
        ],
    )

    req = AdaptSectionRequest(
        section_title="Scope of Work",
        reference_content=(
            "## Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ\n\n"
            "SYS will execute a like-for-like technical upgrade of Alkuraimi Bank's Temenos Transact Core Banking platform."
        ),
        reference_blocks=[],
        context=ClientContext(
            client_name="MMBL",
            industry="Banking",
            project_type="Implementation",
            client_profile="established",
            canonical_product="Temenos Transact",
            intake=IntakeProfile(),
        ),
        proposal_family="Temenos",
        prompt="Prepare a proposal for MMBL. Add the Forex module based on the selected documents.",
    )

    result = asyncio.run(adapt_section(req))

    assert result.section.model.endswith(":grounded-rewrite")
    assert "Forex capability" in result.section.content
    assert "like-for-like technical upgrade" not in result.section.content.lower()
    assert "Environment Readiness Assessment" not in result.section.content
    assert "deployment support" not in result.section.content.lower()
    assert "cutover preparation" not in result.section.content.lower()
    assert "go-live" not in result.section.content.lower()
