"""Agent 7 — Section Writer Agent.

Generates the proposal ONE section at a time (never the whole document at
once). Each call receives the client context, the section name, retrieved
evidence chunks, the proposal family, and pattern guidance, and produces
professional, grounded section content. Supports targeted regeneration via a
free-form `instruction` (e.g. "make it shorter", "rewrite the timeline").
"""

from __future__ import annotations

from app.agents.retrieval_agent import retrieve_for_section
from app.models.schemas import (
    EvidenceChunk,
    GenerateSectionRequest,
    SectionResult,
)
from app.services.llm_service import LLMError, get_llm

_SYSTEM = (
    "You are a senior bid writer producing polished, client-ready proposal "
    "sections for enterprise technology engagements. Write in clean Markdown "
    "(headings, short paragraphs, bullets, and pipe tables where useful). "
    "Be specific and grounded in the supplied evidence; never invent client "
    "facts. Do not add a top-level document title — only this section."
)

_TEMPLATE = """Write the proposal section titled: "{section_title}".

CLIENT CONTEXT
- Client: {client}
- Industry: {industry}
- Project / solution: {project}
- Proposal family: {family}
- Tone: {tone}
- Special instructions: {special}

PATTERN GUIDANCE
{guidance}

ORIGINAL REQUEST
{prompt}

{instruction_block}

EVIDENCE FROM PRIOR PROPOSALS (reuse and adapt; cite nothing inline):
{evidence}

Write the section now. Start with a short "## {section_title}" is NOT needed;
the heading is added by the system. Begin directly with the body. Aim for
{length} of well-structured content.
"""


def _format_evidence(chunks: list[EvidenceChunk]) -> str:
    if not chunks:
        return (
            "(No matching evidence retrieved. Write from best practice for this "
            "family while staying generic about unverified client specifics.)"
        )
    lines = []
    for i, c in enumerate(chunks, 1):
        src = c.source_proposal or "unknown source"
        sec = f" / {c.source_section}" if c.source_section else ""
        snippet = (c.text or "").strip().replace("\n", " ")
        if len(snippet) > 700:
            snippet = snippet[:700] + "…"
        lines.append(f"[{i}] ({src}{sec})\n{snippet}")
    return "\n\n".join(lines)


async def run_section_writer(req: GenerateSectionRequest) -> SectionResult:
    # 1) Retrieve evidence (Agent 6).
    evidence = retrieve_for_section(
        section_title=req.section_title,
        keywords=req.keywords,
        context=req.context,
        proposal_family=req.proposal_family,
        top_k=req.top_k,
    )

    instruction_block = ""
    length = "400–650 words"
    if req.instruction:
        instruction_block = f"REVISION INSTRUCTION (follow precisely):\n{req.instruction}"
        if any(w in req.instruction.lower() for w in ("short", "concise", "brief")):
            length = "180–300 words"
        elif any(w in req.instruction.lower() for w in ("longer", "expand", "detail")):
            length = "650–900 words"

    llm = get_llm()
    try:
        content = await llm.chat(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _TEMPLATE.format(
                        section_title=req.section_title,
                        client=req.context.client_name or "the client",
                        industry=req.context.industry or "—",
                        project=req.context.project_type or "—",
                        family=req.proposal_family or "—",
                        tone=req.context.tone or "Formal",
                        special=req.context.special_instructions or "none",
                        guidance=req.pattern_guidance or "Follow the family's standard structure.",
                        prompt=req.prompt or "—",
                        instruction_block=instruction_block,
                        evidence=_format_evidence(evidence),
                        length=length,
                    ),
                },
            ],
            model=req.model,
            temperature=0.45,
        )
    except LLMError as exc:
        content = (
            f"_Section could not be generated: {exc}_\n\n"
            "Add `OPENROUTER_API_KEY` to `backend/.env` and regenerate."
        )

    return SectionResult(
        title=req.section_title,
        content=content.strip(),
        evidence=evidence,
        model=get_llm().resolve_model(req.model),
    )
