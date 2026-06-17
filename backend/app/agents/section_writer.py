"""Agent 7 - Section Writer Agent.

Generates the proposal ONE section at a time (never the whole document at
once). Each call receives the client context, the section name, retrieved
evidence chunks, the proposal family, and pattern guidance, and produces
professional, grounded section content. Supports targeted regeneration via a
free-form `instruction` (e.g. "make it shorter", "rewrite the timeline").
"""

from __future__ import annotations

import re

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
    "sections for enterprise technology engagements. Write in detailed, "
    "formal proposal prose with a consulting-bid tone. Use clean Markdown "
    "(short paragraphs, bullets, and pipe tables where useful), but avoid "
    "generic filler, self-referential language, and phrases like 'here's' or "
    "'this proposal outlines'. Ground every claim in the supplied evidence; "
    "do not use outside knowledge, memory, or ungrounded estimates. If a fact "
    "is not supported by the evidence, omit it or phrase it as a proposal "
    "recommendation rather than a claim. Never invent numeric values, dates, "
    "durations, percentages, service levels, staffing counts, product claims, "
    "or regulatory assertions. Do not add a top-level document title "
    "- only this section. Produce submission-ready prose that preserves the "
    "specificity, structure, and implementation detail found in the source "
    "proposal corpus."
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

QUALITY CONTROLS
- Detail profile: {detail_level}
- Evidence-only mode: {require_evidence}
- Official Temenos website evidence included: {include_temenos}

Write the section now. The heading is added by the system, so begin directly
with the body. Match a formal proposal style:
- open with a crisp, substantive lead paragraph;
- use section-specific subheadings only when they add clarity;
- include concrete phases, deliverables, assumptions, dependencies, governance
  points, risk implications, and acceptance criteria where the evidence supports them;
- preserve the source corpus level of specificity and avoid over-summarising;
- if the evidence contains lists, scopes, phases, responsibilities, or module
  names, carry them forward in proposal language;
- for substantive delivery sections, write multiple developed paragraphs and
  use bullets or tables only to add precision, not to shorten the answer;
- do not invent numeric SLAs, timelines, team sizes, commercial values, or
  percentages unless those exact details appear in the evidence;
- avoid generic marketing language and vague claims.

Target {length} of well-structured content. Treat the lower bound as the
minimum acceptable depth unless the retrieved evidence is genuinely sparse.
Do not condense the material.
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
        if len(snippet) > 1200:
            snippet = snippet[:1200] + "..."
        header = c.summary or sec.strip(" /") or src
        lines.append(f"[{i}] {header} ({src}{sec}; {c.source_type})\n{snippet}")
    return "\n\n".join(lines)


def _length_for(req: GenerateSectionRequest) -> str:
    if req.instruction:
        lowered = req.instruction.lower()
        if any(w in lowered for w in ("short", "concise", "brief")):
            return "350-650 words"
        if any(w in lowered for w in ("longer", "expand", "detail")):
            return "1200-1800 words"
    if req.detail_level == "balanced":
        return "800-1100 words"
    if req.detail_level == "exhaustive":
        return "1800-2600 words"
    return "1200-1800 words"


def _minimum_words(req: GenerateSectionRequest) -> int:
    if req.instruction and any(
        w in req.instruction.lower() for w in ("short", "concise", "brief")
    ):
        return 300
    if req.detail_level == "balanced":
        return 750
    if req.detail_level == "exhaustive":
        return 1400
    return 1000


def _evidence_enrichment(evidence: list[EvidenceChunk], needed_words: int) -> str:
    if needed_words <= 0:
        return ""
    lines = [
        "\n\n### Evidence-Grounded Delivery Detail\n\n"
        "The following delivery considerations are drawn from the retrieved proposal corpus and should be treated as part of the section scope."
    ]
    added = 0
    for chunk in evidence:
        if added >= needed_words:
            break
        text = " ".join((chunk.text or "").split())
        if not text:
            continue
        if len(text) > 420:
            text = text[:420].rsplit(" ", 1)[0] + "."
        source = chunk.summary or chunk.source_section or chunk.source_proposal or "Retrieved corpus evidence"
        lines.append(
            f"\n\n**{source}.** The proposal should account for {text[0].lower() + text[1:] if text else text} "
            "This should be reflected as an actionable delivery consideration, with ownership, validation, and governance addressed during execution."
        )
        added += len(lines[-1].split())
    return "".join(lines)


def _strip_leading_heading(content: str, section_title: str) -> str:
    lines = content.strip().splitlines()
    while lines and re.match(r"^\s{0,3}#{1,2}\s+", lines[0]):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


async def run_section_writer(req: GenerateSectionRequest) -> SectionResult:
    # 1) Retrieve evidence (Agent 6).
    evidence = retrieve_for_section(
        section_title=req.section_title,
        keywords=req.keywords,
        context=req.context,
        proposal_family=req.proposal_family,
        top_k=req.top_k,
        include_temenos_official=req.include_temenos_official,
        use_hybrid_retrieval=req.use_hybrid_retrieval,
    )

    instruction_block = ""
    length = _length_for(req)
    if req.instruction:
        instruction_block = f"REVISION INSTRUCTION (follow precisely):\n{req.instruction}"

    if req.require_evidence and not evidence:
        return SectionResult(
            title=req.section_title,
            content=(
                "No proposal-corpus evidence was retrieved for this section. "
                "Generation is paused because evidence-only mode is enabled."
            ),
            evidence=[],
            model=get_llm().resolve_model(req.model),
        )

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
                        detail_level=req.detail_level,
                        require_evidence="enabled" if req.require_evidence else "disabled",
                        include_temenos="yes" if req.include_temenos_official else "no",
                        length=length,
                    ),
                },
            ],
            model=req.model,
            temperature=0.08,
            max_tokens=7000,
        )
        if evidence and len(content.split()) < _minimum_words(req):
            content = await llm.chat(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            "Expand the draft below into a fuller, submission-ready "
                            f"proposal section of at least {_minimum_words(req)} words. "
                            "Keep the same section scope and do not introduce facts "
                            "that are not supported by the evidence.\n\n"
                            f"EVIDENCE:\n{_format_evidence(evidence)}\n\n"
                            f"DRAFT:\n{content}"
                        ),
                    },
                ],
                model=req.model,
                temperature=0.08,
                max_tokens=7000,
            )
        if evidence and len(content.split()) < _minimum_words(req):
            content = (
                content.rstrip()
                + _evidence_enrichment(
                    evidence,
                    needed_words=_minimum_words(req) - len(content.split()),
                )
            )
    except LLMError as exc:
        content = _local_section_content(req, evidence, length)

    return SectionResult(
        title=req.section_title,
        content=_strip_leading_heading(content, req.section_title),
        evidence=evidence,
        model=get_llm().resolve_model(req.model),
    )
