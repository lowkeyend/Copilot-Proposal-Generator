"""Agent 7 - Section Writer Agent.

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


def _local_section_content(req: GenerateSectionRequest, evidence: list[EvidenceChunk], length: str) -> str:
    client = req.context.client_name or "the client"
    industry = req.context.industry or "the industry"
    project = req.context.project_type or req.proposal_family or "the engagement"
    family = req.proposal_family or "the proposal family"
    tone = req.context.tone or "Formal"

    lead = (
        f"### {req.section_title}\n\n"
        f"{client} requires a section that aligns the proposed solution with its "
        f"{project.lower()} objectives, the selected {family} approach, and the "
        f"operating realities of {industry.lower()}. This section is written in "
        f"a {tone.lower()} tone and is grounded only in retrieved evidence and "
        f"official product context."
    )

    if req.instruction:
        lead += f" The current revision instruction is: {req.instruction.strip()}."

    if evidence:
        evidence_intro = (
            "\n\nThe retrieved evidence supports the following proposal framing:"
        )
    else:
        evidence_intro = (
            "\n\nNo direct evidence was retrieved for this section, so the "
            "section is phrased conservatively and limited to the request context."
        )

    paragraphs: list[str] = [lead, evidence_intro]
    for i, chunk in enumerate(evidence[:8], 1):
        src = chunk.source_proposal or "an internal source"
        sec = f" / {chunk.source_section}" if chunk.source_section else ""
        if not chunk.text:
            continue

        snippet = " ".join(chunk.text.split())
        if len(snippet) > 260:
            snippet = snippet[:260].rsplit(" ", 1)[0] + "..."

        paragraphs.append(
            f"\n\n{i}. From {src}{sec}, the source material reinforces that "
            f"{snippet.lower()} "
            f"This evidence supports a proposal narrative that should remain "
            f"concrete, implementation-oriented, and cautious about any claim "
            f"not directly visible in the knowledge base."
        )

    paragraphs.append(
        "\n\nIn practical terms, this means the proposal should describe how the "
        "solution will be delivered, governed, validated, and handed over, "
        "without drifting into unsupported claims. Where the evidence shows "
        "specific modules, operating models, deployment approaches, or delivery "
        "phases, those should be carried forward explicitly. Where the evidence "
        "is silent, the text should state the assumption as a proposal "
        "recommendation rather than a fact."
    )

    if evidence:
        paragraphs.append(
            "\n\nThe resulting section should read as a substantive, board-ready "
            "proposal passage: detailed enough to match a real bid document, but "
            "still disciplined enough to avoid hallucination."
        )

    if "Temenos" in (req.proposal_family or "") or "Temenos" in project:
        paragraphs.append(
            "\n\nFor Temenos-specific proposals, the section should consistently "
            "reference the platform, its modular banking scope, cloud-native "
            "positioning, and the delivery benefits documented in the official "
            "Temenos summaries and proposal corpus."
        )

    return "".join(paragraphs)

_SYSTEM = (
    "You are a senior bid writer producing polished, client-ready proposal "
    "sections for enterprise technology engagements. Write in concise, "
    "formal proposal prose with a consulting-bid tone. Use clean Markdown "
    "(short paragraphs, bullets, and pipe tables where useful), but avoid "
    "generic filler, self-referential language, and phrases like 'here's' or "
    "'this proposal outlines'. Ground every claim in the supplied evidence; "
    "do not use outside knowledge, memory, or ungrounded estimates. If a fact "
    "is not supported by the evidence, omit it or phrase it as a proposal "
    "recommendation rather than a claim. Do not add a top-level document title "
    "- only this section."
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

Write the section now. The heading is added by the system, so begin directly
with the body. Match a formal proposal style:
- open with a crisp, substantive lead paragraph;
- use section-specific subheadings only when they add clarity;
- include at least one practical detail, phase, deliverable, or risk
  implication where relevant;
- avoid generic marketing language and vague claims.

Aim for {length} of well-structured content. Do not condense the material;
preserve the richness and detail expected in a real proposal.
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
            snippet = snippet[:700] + "..."
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
    length = "850-1200 words"
    if req.instruction:
        instruction_block = f"REVISION INSTRUCTION (follow precisely):\n{req.instruction}"
        if any(w in req.instruction.lower() for w in ("short", "concise", "brief")):
            length = "180-300 words"
        elif any(w in req.instruction.lower() for w in ("longer", "expand", "detail")):
            length = "900-1300 words"
    else:
        length = "850-1200 words"

    llm = get_llm()
    try:
        if not llm.available:
            raise LLMError("OPENROUTER_API_KEY is not set.")
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
                        guidance=req.pattern_guidance
                        or "Follow the family's standard structure.",
                        prompt=req.prompt or "—",
                        instruction_block=instruction_block,
                        evidence=_format_evidence(evidence),
                        length=length,
                    ),
                },
            ],
            model=req.model,
            temperature=0.15,
        )
    except LLMError as exc:
        content = _local_section_content(req, evidence, length)

    return SectionResult(
        title=req.section_title,
        content=content.strip(),
        evidence=evidence,
        model=get_llm().resolve_model(req.model),
    )
