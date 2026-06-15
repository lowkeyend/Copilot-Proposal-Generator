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


async def run_toc_agent(req: BuildTocRequest) -> list[TocSection]:
    template = req.template or pattern_for_family(req.proposal_family)
    skeleton_sections = template.sections if template else []
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
