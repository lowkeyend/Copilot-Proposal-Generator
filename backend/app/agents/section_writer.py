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


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _normalize_whitespace(text: str) -> str:
    return " ".join((text or "").split())


def _clean_phrase(text: str) -> str:
    cleaned = _normalize_whitespace(text)
    cleaned = cleaned.replace("Ã¢â‚¬â€œ", "-").replace("Ã¢â‚¬â€", "-").replace("Ã¢â‚¬â„¢", "'")
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s+-\s+", " - ", cleaned)
    cleaned = re.sub(r"\b[iI]\s+ts\b", "its", cleaned)
    cleaned = re.sub(r"\btemenosÃ¢â‚¬â„¢\b", "Temenos'", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" -")


def _sentence_case(text: str) -> str:
    text = _clean_phrase(text)
    if not text:
        return text
    return text[0].upper() + text[1:]


def _split_sentences(text: str) -> list[str]:
    cleaned = _clean_phrase(text)
    if not cleaned:
        return []
    parts = _SENTENCE_SPLIT.split(cleaned)
    return [part for part in (_clean_phrase(p) for p in parts) if part]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _with_article(text: str) -> str:
    value = _clean_phrase(text).lower()
    if not value:
        return value
    article = "an" if value[:1].lower() in "aeiou" else "a"
    return f"{article} {value}"


def _section_keywords(req: GenerateSectionRequest) -> list[str]:
    values = [req.section_title, req.prompt, req.instruction, req.proposal_family]
    values.extend(req.keywords or [])
    text = " ".join(v for v in values if v)
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


def _section_keywords_from_text(text: str) -> list[str]:
    cleaned = _clean_phrase(text or "")
    if not cleaned:
        return []
    return [t for t in re.findall(r"[a-z0-9]+", cleaned.lower()) if len(t) > 2]

def _extract_fact_sentence(sentence: str, section_keywords: list[str]) -> str | None:
    sentence = _clean_phrase(sentence)
    if not sentence:
        return None

    lowered = sentence.lower()
    if lowered.startswith(("from ", "the retrieved evidence", "this evidence", "source material")):
        return None
    if lowered.startswith(("no direct evidence", "the resulting section", "in practical terms")):
        return None
    if any(
        term in lowered
        for term in ("proposal narrative", "board-ready", "grounded only in retrieved evidence")
    ):
        return None

    sentence = re.sub(
        r"^(and\s+|but\s+|or\s+|so\s+|then\s+|finally,\s+|furthermore,\s+|moreover,\s+)",
        "",
        sentence,
        flags=re.IGNORECASE,
    )
    sentence = re.sub(
        r"\bwill be phased or in a big[- ]bang\b",
        "can be delivered in either a phased or big-bang model",
        sentence,
        flags=re.IGNORECASE,
    )
    sentence = re.sub(r"\bpre[- ]packaged tools\b", "pre-packaged tools", sentence, flags=re.IGNORECASE)
    return sentence[0].upper() + sentence[1:] if sentence else sentence


def _extract_support_points(
    chunk: EvidenceChunk, section_keywords: list[str], limit: int = 2
) -> list[str]:
    text = _clean_phrase(chunk.text or "")
    if not text:
        return []
    sentences = _split_sentences(text)
    points: list[str] = []
    for sentence in sentences:
        fact = _extract_fact_sentence(sentence, section_keywords)
        if fact:
            points.append(fact.rstrip(".") + ".")
        if len(points) >= limit:
            break
    if not points and text:
        fact = _extract_fact_sentence(text[:260], section_keywords)
        if fact:
            points.append(fact.rstrip(".") + ".")
    return _dedupe_preserve_order(points)


def _evidence_briefs(
    chunks: list[EvidenceChunk], section_keywords: list[str]
) -> list[tuple[str, str, list[str]]]:
    briefs: list[tuple[str, str, list[str]]] = []
    seen: set[str] = set()
    for chunk in chunks:
        text_key = re.sub(r"[^a-z0-9]+", " ", _clean_phrase(chunk.text or "").lower()).strip()
        if not text_key or text_key in seen:
            continue
        seen.add(text_key)
        label = chunk.summary or chunk.source_section or chunk.source_proposal or "Retrieved evidence"
        source = chunk.source_proposal or "unknown source"
        points = _extract_support_points(chunk, section_keywords)
        if points:
            briefs.append((label, source, points))
    return briefs[:6]


def _proposalize_fact(text: str) -> str:
    lowered = _clean_phrase(text).lower()
    if not lowered:
        return ""
    if "executive sponsorship" in lowered and "governance" in lowered and "partner model" in lowered:
        return (
            "Delivery will be anchored by executive sponsorship, a strong governance structure, "
            "and a proven partner model that brings experience, capacity, and accelerators."
        )
    if "learning suite" in lowered or "change management" in lowered:
        return (
            "Temenos learning resources will support change management during and after the initial "
            "renovation phase."
        )
    if "migration" in lowered and ("phased" in lowered or "big-bang" in lowered or "big bang" in lowered):
        return (
            "The migration will be executed in controlled phases, with the final cutover model "
            "selected to match the agreed scope and risk profile."
        )
    if "pre-packaged tools" in lowered:
        return (
            "Temenos pre-packaged tools will be used to accelerate delivery and reduce manual effort "
            "during migration."
        )
    if "full phased migration" in lowered:
        return "The delivery model will use phased migration to manage scope and cutover risk."
    if "co-existence" in lowered:
        return "Co-existence will be used where legacy run-off or staged migration is required."
    if "strong governance" in lowered:
        return "A strong governance framework will control scope, risk, decisions, and delivery cadence."
    return _sentence_case(text)


def _local_section_content(req: GenerateSectionRequest, evidence: list[EvidenceChunk], length: str) -> str:
    client = req.context.client_name or "the client"
    industry = req.context.industry or "the industry"
    project = req.context.project_type or req.proposal_family or "the engagement"
    product = req.context.canonical_product or "the proposed solution"
    family = req.proposal_family or "the proposal family"
    tone = req.context.tone or "Formal"
    intake = _intake_summary(req.context)
    project_phrase = _with_article(project)
    title = req.section_title.lower()
    keywords = _section_keywords(req)
    briefs = _evidence_briefs(evidence, keywords)

    if any(term in title for term in ("introduction", "executive summary", "overview")):
        lead = (
            f"### {req.section_title}\n\n"
            f"{client} is seeking {project_phrase} proposal that aligns the selected "
            f"{product} solution with the business, delivery, and governance realities "
            f"of {industry.lower()}. The proposal positions the change as a controlled "
            f"transformation program, with the operating model, delivery governance, and "
            f"implementation path aligned to the selected methodology and delivery model."
        )
    elif any(term in title for term in ("solution", "approach", "strategy")):
        lead = (
            f"### {req.section_title}\n\n"
            f"The proposed {product} solution is structured as a coherent response to "
            f"{client}'s {project.lower()} objectives. It combines executive sponsorship, "
            f"strong governance, a proven partner model, and staged delivery so the target "
            f"operating model can be achieved without disrupting business continuity."
        )
    else:
        lead = (
            f"### {req.section_title}\n\n"
            f"{client} requires a focused {req.section_title.lower()} section that is aligned "
            f"to the selected {product} solution, the {family} delivery pattern, and the "
            f"operating realities of {industry.lower()}."
        )

    paragraphs: list[str] = [lead]

    fact_lines: list[str] = []
    for _label, _source, points in briefs[:4]:
        fact_lines.extend(points[:2])
    fact_lines = _dedupe_preserve_order([_proposalize_fact(p) for p in fact_lines if p])

    if fact_lines:
        if any(term in title for term in ("introduction", "executive summary", "overview")):
            paragraphs.append(
                "The proposal is anchored by executive sponsorship, strong governance, and a "
                "clear partner model so the transition can be controlled from mobilization through "
                "cutover. " + " ".join(fact_lines[:2])
            )
            paragraphs.append(
                "Change management is supported through Temenos learning resources, while the "
                "migration strategy remains phase-aware and governed by the selected rollout model. "
                + " ".join(fact_lines[2:4])
            )
        elif any(term in title for term in ("solution", "approach", "strategy")):
            paragraphs.append(
                "The delivery approach combines phased migration, governance checkpoints, and "
                "solution-specific preparation so the target state is reached without introducing "
                "uncontrolled risk. " + " ".join(fact_lines[:2])
            )
            paragraphs.append(
                "Implementation activities are sequenced around validation, change readiness, and "
                "controlled cutover, with the selected Temenos tools and partner support used to "
                "stabilise the move into live operation. " + " ".join(fact_lines[2:4])
            )
        else:
            paragraphs.append(
                "The section is grounded in the retrieved corpus and keeps the delivery narrative "
                "aligned to the client context. " + " ".join(fact_lines[:3])
            )
    else:
        paragraphs.append(
            "The section remains grounded in the confirmed client context and delivery model, "
            "with assumptions kept explicit wherever the knowledge base is silent."
        )

    if req.instruction:
        paragraphs.append(
            f"Revision request incorporated: {req.instruction.strip()}."
        )

    return "\n\n".join(paragraphs)
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
    "proposal corpus. Do not mention source document names, chunk IDs, the "
    "words 'source material', or any evidence labels in the final section "
    "body. Write the section as if it were authored directly for the client."
)

_TEMPLATE = """Write the proposal section titled: "{section_title}".

CLIENT CONTEXT
- Client: {client}
- Industry: {industry}
- Project / solution: {project}
- Current client profile: {client_profile}
- Implementation context: {implementation_context}
- Canonical product name: {canonical_product}
- Questionnaire summary: {intake_summary}
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
- Prefer TIM wording and phase-based rollout language when the questionnaire
  indicates TIM, MVP, phased launch, or go-live milestones.
- Synthesize evidence into prose; do not restate the chunks.
- Do not mention source document names, chunk IDs, or source commentary in
  the final section.

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

    section_keywords: list[str] = []
    for chunk in chunks:
        section_keywords.extend(_section_keywords_from_text(chunk.summary or ""))
        section_keywords.extend(_section_keywords_from_text(chunk.source_section or ""))
        section_keywords.extend(_section_keywords_from_text(chunk.text or ""))

    lines = []
    seen: set[str] = set()
    for i, c in enumerate(chunks[:6], 1):
        key = re.sub(r"[^a-z0-9]+", " ", _clean_phrase(c.text or "").lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        src = c.source_proposal or "unknown source"
        sec = f" / {c.source_section}" if c.source_section else ""
        header = _clean_phrase(c.summary or sec.strip(" /") or src)
        points = _extract_support_points(c, section_keywords, limit=2)
        if not points:
            continue
        lines.append(f"[{i}] {header} ({src}{sec}; {c.source_type})\n- " + "\n- ".join(points))
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
    section_keywords: list[str] = []
    for chunk in evidence:
        section_keywords.extend(_section_keywords_from_text(chunk.summary or ""))
        section_keywords.extend(_section_keywords_from_text(chunk.source_section or ""))
        section_keywords.extend(_section_keywords_from_text(chunk.text or ""))
    briefs = _evidence_briefs(evidence, section_keywords)
    if not briefs:
        return ""

    lines = [
        "\n\n### Evidence-Grounded Delivery Detail\n",
        "The following delivery points are carried forward from the retrieved corpus and translated into proposal language.",
    ]
    added = 0
    for label, _source, points in briefs:
        if added >= needed_words:
            break
        bullet = " ".join(points[:2])
        lines.append(f"\n\n- {label}: {bullet}")
        added += len(bullet.split())
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


def _intake_summary(context) -> str:
    intake = getattr(context, "intake", None)
    if not intake:
        return ""
    parts: list[str] = []
    if intake.launch_segments:
        parts.append(f"segments: {', '.join(intake.launch_segments)}")
    if intake.phase_1_products:
        parts.append(f"phase 1 products: {', '.join(intake.phase_1_products)}")
    if intake.phase_2_products:
        parts.append(f"phase 2 products: {', '.join(intake.phase_2_products)}")
    if intake.regulatory_interfaces_phase_1:
        parts.append(f"phase 1 interfaces: {', '.join(intake.regulatory_interfaces_phase_1)}")
    if intake.regulatory_interfaces_phase_2:
        parts.append(f"phase 2 interfaces: {', '.join(intake.regulatory_interfaces_phase_2)}")
    if intake.channels_phase_1:
        parts.append(f"phase 1 channels: {', '.join(intake.channels_phase_1)}")
    if intake.channels_phase_2:
        parts.append(f"phase 2 channels: {', '.join(intake.channels_phase_2)}")
    if intake.middleware_platform:
        parts.append(f"middleware: {intake.middleware_platform}")
    if intake.reporting_platform:
        parts.append(f"reporting: {intake.reporting_platform}")
    if intake.database_platform:
        parts.append(f"database: {intake.database_platform}")
    if intake.hosting_model:
        parts.append(f"hosting: {intake.hosting_model}")
    if intake.container_platform:
        parts.append(f"container: {intake.container_platform}")
    if intake.data_warehouse_platform:
        parts.append(f"warehouse: {intake.data_warehouse_platform}")
    if intake.implementation_methodology:
        parts.append(f"methodology: {intake.implementation_methodology}")
    if intake.delivery_model:
        parts.append(f"delivery: {intake.delivery_model}")
    if intake.launch_plan:
        parts.append(f"launch plan: {intake.launch_plan}")
    if intake.questionnaire_notes:
        parts.append(f"notes: {intake.questionnaire_notes}")
    return "; ".join(parts)


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


def _remove_meta_language(content: str) -> str:
    lines = content.splitlines()
    filtered: list[str] = []
    skip_patterns = (
        "questionnaire context:",
        "the section should",
        "the final wording should",
        "no direct evidence was retrieved",
        "the retrieved evidence supports",
    )
    for line in lines:
        lowered = line.strip().lower()
        if any(lowered.startswith(pattern) for pattern in skip_patterns):
            continue
        filtered.append(line)
    text = "\n".join(filtered)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _rewrite_common_echoes(content: str) -> str:
    replacements = [
        (
            r"\b\d+\s+\d+\s+Temenos Implementation Methodology\s+",
            "",
        ),
        (
            r"Temenos Implementation Methodology \(TIM\) is a process[- ]driven implementation approach, with each step in the implementation clearly identified\.",
            "TIM provides a process-driven implementation framework with clearly identified steps from initiation through closure.",
        ),
        (
            r"Temenos through its learning suite will support the change management during and after the initial renovation phase\.",
            "Temenos learning resources will support change management before go-live and through hypercare.",
        ),
        (
            r"Finally, the migration will be phased or in a big[- ]bang, and secured by the experience of Temenos, its Partner networks as well as Temenos pre-packaged tools\.",
            "The migration will be executed in phased stages, supported by Temenos experience, partner capability, and pre-packaged tools.",
        ),
        (
            r"The transformation shall also be supported by a strong Executive Sponsorship promoting and supporting the simplification and adopt principles, a Strong Governance and, a rich and proven Partner Model bringing experience, capacity and additional accelerators\.",
            "Delivery will be anchored by executive sponsorship, a strong governance structure, and a proven partner model that brings experience, capacity, and accelerators.",
        ),
        (
            r"The implementation of all the new proposed Temenos solutions in this proposal will be managed by SYS\.",
            "The implementation of the proposed Temenos solutions will be managed through a structured delivery governance model.",
        ),
    ]
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content, flags=re.IGNORECASE)
    content = re.sub(r"(?m)^\s*\d+\s+\d+\s+", "", content)
    return content


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
                        industry=req.context.industry or "-",
                        project=req.context.project_type or "-",
                        client_profile=req.context.client_profile or "established",
                        implementation_context=req.context.implementation_context
                        or "Modernization / migration for an existing institution",
                        canonical_product=req.context.canonical_product
                        or "Temenos Transact",
                        intake_summary=_intake_summary(req.context) or "none provided",
                        family=req.proposal_family or "-",
                        tone=req.context.tone or "Formal",
                        special=req.context.special_instructions or "none",
                        guidance=req.pattern_guidance
                        or "Follow the family's standard structure.",
                        prompt=req.prompt or "-",
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
    content = _rewrite_common_echoes(content)
    content = _remove_meta_language(content)
    return SectionResult(
        title=req.section_title,
        content=_strip_leading_heading(content, req.section_title),
        evidence=evidence,
        model=get_llm().resolve_model(req.model),
        )

