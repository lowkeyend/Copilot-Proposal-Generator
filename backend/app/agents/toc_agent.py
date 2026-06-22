"""Agent 5 — Dynamic TOC Builder.

Produces an editable table of contents that becomes the generation plan. It
starts from the chosen/suggested template skeleton and lets the LLM tailor it
to this specific request (e.g. emphasise migration & security). The result is
a list of TocSection objects; the UI can add/remove/rename/reorder them.
"""

from __future__ import annotations

from app.models.schemas import (
    BuildTocRequest,
    TocSection,
)
from app.agents.pattern_discovery import pattern_for_family
from app.services.llm_service import LLMError, get_llm

_SYSTEM = (
    "You design the section outline (table of contents) for a business "
    "proposal. Respond with STRICT JSON only."
)

_TEMPLATE = """Build an editable proposal outline tailored to this request.

Start from the discovered skeleton for this proposal family, then adapt:
- keep the logical order,
- add/rename sections to honour the emphasis in the request,
- 6 to 11 sections total.

Discovered skeleton sections:
{skeleton}

Questionnaire-driven outline hints:
{intake_hints}

Return JSON list, each item:
{{ "title": "", "keywords": ["", ""], "description": "" }}

keywords = 2-5 retrieval hint terms for that section.

REQUEST:
\"\"\"{prompt}\"\"\"

CONTEXT:
client_name: {client}
industry: {industry}
project_type: {project}
proposal_family: {family}
tone: {tone}
special_instructions: {special}
"""


def _intake_hints(context) -> str:
    intake = context.intake
    lines = [
        f"- Client profile: {context.client_profile or 'unknown'}",
        f"- Implementation context: {context.implementation_context or 'unspecified'}",
        f"- Canonical product: {context.canonical_product or 'Temenos Transact'}",
        f"- Delivery methodology: {intake.implementation_methodology or 'TIM'}",
        f"- Delivery model: {intake.delivery_model or 'Phased MVP'}",
    ]
    if intake.launch_segments:
        lines.append(f"- Launch segments: {', '.join(intake.launch_segments)}")
    if intake.phase_1_products:
        lines.append(f"- Phase 1 products: {', '.join(intake.phase_1_products)}")
    if intake.phase_2_products:
        lines.append(f"- Phase 2 products: {', '.join(intake.phase_2_products)}")
    if intake.regulatory_interfaces_phase_1:
        lines.append(
            f"- Phase 1 regulatory interfaces: {', '.join(intake.regulatory_interfaces_phase_1)}"
        )
    if intake.regulatory_interfaces_phase_2:
        lines.append(
            f"- Phase 2 regulatory interfaces: {', '.join(intake.regulatory_interfaces_phase_2)}"
        )
    if intake.channels_phase_1:
        lines.append(f"- Phase 1 channels: {', '.join(intake.channels_phase_1)}")
    if intake.channels_phase_2:
        lines.append(f"- Phase 2 channels: {', '.join(intake.channels_phase_2)}")
    if intake.middleware_platform:
        lines.append(f"- Middleware: {intake.middleware_platform}")
    if intake.reporting_platform:
        lines.append(f"- Reporting platform: {intake.reporting_platform}")
    if intake.data_warehouse_platform:
        lines.append(f"- Data warehouse: {intake.data_warehouse_platform}")
    if intake.database_platform:
        lines.append(f"- Database: {intake.database_platform}")
    if intake.hosting_model:
        lines.append(f"- Hosting model: {intake.hosting_model}")
    if intake.container_platform:
        lines.append(f"- Container platform: {intake.container_platform}")
    if intake.target_customers_year_1 or intake.target_accounts_year_1:
        lines.append(
            f"- Year 1 targets: {intake.target_customers_year_1} customers / {intake.target_accounts_year_1} accounts"
        )
    if intake.target_customers_year_2 or intake.target_accounts_year_2:
        lines.append(
            f"- Year 2 targets: {intake.target_customers_year_2} customers / {intake.target_accounts_year_2} accounts"
        )
    if intake.target_customers_year_3 or intake.target_accounts_year_3:
        lines.append(
            f"- Year 3 targets: {intake.target_customers_year_3} customers / {intake.target_accounts_year_3} accounts"
        )
    if intake.launch_plan:
        lines.append(f"- Launch plan: {intake.launch_plan}")
    if intake.questionnaire_notes:
        lines.append(f"- Additional notes: {intake.questionnaire_notes}")
    return "\n".join(lines) or "- (no questionnaire hints provided)"


def _fallback_outline(context) -> list[TocSection]:
    intake = context.intake
    sections = [
        TocSection(title="Executive Summary", keywords=["executive", "summary"], description="Set the strategic frame."),
        TocSection(title="Client Objectives & Scope", keywords=["objectives", "scope"], description="Tie the proposal to client goals."),
        TocSection(title="Solution Scope & Product Coverage", keywords=["scope", "products"], description="Detail the functional breadth."),
        TocSection(title="Architecture & Integrations", keywords=["architecture", "integration"], description="Cover channels, interfaces, middleware, and environment."),
        TocSection(title="Data Migration, Reporting & Controls", keywords=["migration", "reporting", "controls"], description="Cover data, reports, security, and compliance."),
        TocSection(title="TIM Delivery Approach", keywords=["tim", "methodology", "delivery"], description="Explain the implementation method and governance."),
        TocSection(title="Testing, Cutover & Go-Live", keywords=["testing", "cutover", "go-live"], description="Detail validation and rollout."),
        TocSection(title="Training, Handover & Support", keywords=["training", "handover", "support"], description="Describe enablement and stabilization."),
        TocSection(title="Project Governance & Timeline", keywords=["governance", "timeline"], description="Show cadence, milestones, and accountability."),
        TocSection(title="Assumptions & Dependencies", keywords=["assumptions", "dependencies"], description="State scope assumptions explicitly."),
    ]
    if context.client_profile == "greenfield":
        sections.insert(2, TocSection(title="Phased MVP Launch Plan", keywords=["mvp", "launch", "phase"], description="Break the launch into phases."))
    if intake.launch_segments:
        sections.insert(2, TocSection(title="Segment Strategy", keywords=["retail", "sme", "corporate"], description="Map scope to the launch segments."))
    if intake.phase_1_products or intake.phase_2_products:
        sections.insert(3, TocSection(title="Product Scope by Phase", keywords=["phase", "products"], description="Detail MVP and later-wave products."))
    if intake.regulatory_interfaces_phase_1 or intake.regulatory_interfaces_phase_2:
        sections.insert(4, TocSection(title="Interface & Regulatory Matrix", keywords=["interfaces", "regulatory"], description="Map interfaces to phases."))
    if intake.channels_phase_1 or intake.channels_phase_2:
        sections.insert(5, TocSection(title="Channel Integration Scope", keywords=["channel", "digital"], description="Cover digital and internal channels."))
    if intake.data_warehouse_platform or intake.reporting_platform:
        sections.insert(6, TocSection(title="Reporting & Analytics", keywords=["reporting", "warehouse"], description="Link reports and analytics to the architecture."))
    return sections[:11]


async def run_toc_agent(req: BuildTocRequest) -> list[TocSection]:
    template = req.template or pattern_for_family(req.proposal_family)
    skeleton_sections = template.sections if template else []
    if not skeleton_sections:
        skeleton_sections = _fallback_outline(req.context)
    skeleton_str = (
        "\n".join(f"- {s.title}" for s in skeleton_sections)
        or "- (none discovered; design a sensible outline)"
    )

    llm = get_llm()
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _TEMPLATE.format(
                        skeleton=skeleton_str,
                        intake_hints=_intake_hints(req.context),
                        prompt=req.prompt,
                        client=req.context.client_name or "?",
                        industry=req.context.industry or "?",
                        project=req.context.project_type or "?",
                        family=req.proposal_family or "?",
                        tone=req.context.tone or "Formal",
                        special=req.context.special_instructions or "none",
                    ),
                },
                ],
            model=req.model,
        )
        toc = _coerce(data)
        if toc:
            return toc
    except (LLMError, ValueError):
        pass

    # Fallback: use the skeleton directly.
    if skeleton_sections:
        return [
            TocSection(
                title=s.title, keywords=s.keywords, description=s.description
            )
            for s in skeleton_sections
        ]
    return [
        TocSection(title=t, keywords=[t.lower()])
        for t in [
            "Executive Summary",
            "Solution Overview",
            "Approach & Methodology",
            "Project Timeline",
            "Commercials & Pricing",
            "Conclusion",
        ]
    ]


def _coerce(data) -> list[TocSection]:
    items = data if isinstance(data, list) else data.get("sections", [])
    out: list[TocSection] = []
    for it in items:
        if isinstance(it, str):
            out.append(TocSection(title=it, keywords=[it.lower()]))
        elif isinstance(it, dict) and it.get("title"):
            out.append(
                TocSection(
                    title=str(it["title"]).strip(),
                    keywords=[str(k).strip() for k in it.get("keywords", []) if k],
                    description=str(it.get("description", "")).strip(),
                )
            )
    return out
