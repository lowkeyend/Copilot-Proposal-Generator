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
    product = req.context.canonical_product or "the proposed solution"
    family = req.proposal_family or "the proposal family"
    tone = req.context.tone or "Formal"

    lead = (
        f"### {req.section_title}\n\n"
        f"{client} requires a section that aligns the proposed solution with its "
        f"{project.lower()} objectives, the selected {product} solution, the {family} approach, and the "
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
            f"\n\nFor Temenos-specific proposals, the section should consistently "
            f"reference {product}, its modular banking scope, cloud-native "
            "positioning, and the delivery benefits documented in the retrieved "
            "evidence."
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
- Current client profile: {client_profile}
- Implementation context: {implementation_context}
- Canonical product name: {canonical_product}
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
- Treat retrieved chunks as reusable proposal evidence, not as facts about the
  current client when they conflict with CLIENT CONTEXT.
- The CLIENT CONTEXT is the ground truth for client type, product name, and
  implementation context.
- Use the client name exactly as "{client}" throughout.
- Use the canonical product name "{canonical_product}" consistently. Do not
  alternate between product names unless the evidence clearly distinguishes
  multiple products.
- If current client profile is not greenfield, do not call the client a
  greenfield bank, brand-new bank, new market entrant, or rapid-market-entry
  institution even if a retrieved source chunk says that about another client.
- For established-bank modernization/migration, explicitly connect migration
  planning with data protection, security controls, governance, validation, and
  cutover assurance when evidence supports those topics.
- If PRINCE2, Scrum, agile, governance, steering committee, PMO, or delivery
  model terms appear in evidence, keep those references coherent across delivery
  and governance language.
- Use "cloud-native architecture with deployment flexibility" when discussing
  cloud positioning unless the evidence explicitly requires another distinction.

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
    while lines and re.match(r"^\s{0,3}#{1,3}\s+", lines[0]):
        lines = lines[1:]
        while lines and not lines[0].strip():
            lines = lines[1:]
    return "\n".join(lines).strip()


def _canonical_client_name(value: str) -> str:
    cleaned = " ".join((value or "").split())
    lowered = cleaned.lower()
    if lowered.startswith("bank ") and lowered.endswith(" bank"):
        middle = cleaned[5:-5].strip()
        if middle:
            return f"Bank {middle}"
    if lowered in {"alfalah", "alfalah bank", "alfalahbank", "bank alfalah bank", "alfalah bank limited"}:
        return "Bank Alfalah"
    return cleaned


def _is_established_context(req: GenerateSectionRequest) -> bool:
    context_text = " ".join(
        [
            req.context.client_profile or "",
            req.context.implementation_context or "",
            req.context.project_type or "",
            req.prompt or "",
        ]
    ).lower()
    if req.context.client_profile == "greenfield":
        return False
    return "greenfield" not in context_text or "established" in context_text or "migration" in context_text


def _apply_context_guardrails(content: str, req: GenerateSectionRequest) -> str:
    result = content.strip()
    client = _canonical_client_name(req.context.client_name or "")
    if client:
        result = re.sub(re.escape(client), client, result, flags=re.IGNORECASE)
        if client == "Bank Alfalah":
            for pattern in (
                r"\bBank\s+Alfalah\s+Bank\b",
                r"\bAlFalah\s+Bank\b",
                r"\bAlfalah\s+Bank\b",
                r"\balfalah\s+bank\b",
                r"(?<!\bBank\s)\balfalah\b",
            ):
                result = re.sub(pattern, client, result, flags=re.IGNORECASE)

    product = (req.context.canonical_product or "").strip()
    if product:
        for alias in (
            r"\bTemenos\s+Core\s+Banking\b",
            r"\bTemenos\s+Banking\s+Platform\b",
            r"\bTemenos\s+core\s+banking\s+platform\b",
        ):
            result = re.sub(alias, product, result, flags=re.IGNORECASE)

    if _is_established_context(req):
        replacements = {
            r"\bgreenfield\s+bank\b": "established bank",
            r"\bgreenfield\s+environment\b": "modernization environment",
            r"\bgreenfield\s+implementation\b": "modernization implementation",
            r"\bgreenfield\b": "modernization",
            r"\bbrand[- ]new\s+bank\b": "existing banking institution",
            r"\bnew\s+digital\s+bank\b": "existing digital banking operation",
            r"\bnew\s+bank\b": "existing bank",
            r"\brapid\s+market\s+entry\b": "controlled modernization and migration",
            r"\bmarket-entry\s+launch\b": "modernization launch",
            r"\bMVP\s+launch\b": "phased rollout",
        }
        for pattern, replacement in replacements.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    result = re.sub(
        r"\bcloud-native\s+and\s+cloud-agnostic\b",
        "cloud-native architecture with deployment flexibility",
        result,
        flags=re.IGNORECASE,
    )
    result = re.sub(
        r"\bcloud-agnostic\s+and\s+cloud-native\b",
        "cloud-native architecture with deployment flexibility",
        result,
        flags=re.IGNORECASE,
    )
    return result.strip()


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
                        client_profile=req.context.client_profile or "established",
                        implementation_context=req.context.implementation_context
                        or "Modernization / migration for an existing institution",
                        canonical_product=req.context.canonical_product
                        or "Temenos Transact",
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

    content = _apply_context_guardrails(content, req)
    return SectionResult(
        title=req.section_title,
        content=_strip_leading_heading(content, req.section_title),
        evidence=evidence,
        model=get_llm().resolve_model(req.model),
        )