from __future__ import annotations

import re

from app.agents.retrieval_agent import retrieve_for_section
from app.models.schemas import (
    AdaptSectionRequest,
    AdaptSectionResponse,
    AdaptationChange,
    ProposalBrief,
    SectionResult,
)
from app.services.llm_service import LLMError, get_llm

_COMMENTARY_MARKERS = (
    "the section should",
    "the final wording should",
    "questionnaire context",
    "this section",
    "the proposal should",
)

_MARKETING_PHRASES = (
    "improved performance",
    "enhanced architecture",
    "stronger security controls",
    "new product capabilities",
    "best practice",
    "industry leading",
)

_KNOWN_REFERENCE_CLIENTS = (
    "Alkuraimi Bank",
    "Alkuraimi Islamic Bank",
    "Al Kuraimi Bank",
    "Bank White",
    "Bank of Dubai",
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _reference_client_candidates(text: str) -> list[str]:
    found: list[str] = []
    corpus = text or ""
    for name in _KNOWN_REFERENCE_CLIENTS:
        if re.search(re.escape(name), corpus, flags=re.IGNORECASE):
            found.append(name)
    for match in re.findall(r"\b([A-Z][A-Za-z&.\-']+(?:\s+[A-Z][A-Za-z&.\-']+){0,4}\s+Bank)\b", corpus):
        candidate = _clean(match)
        if len(candidate.split()) >= 2 and candidate not in found:
            found.append(candidate)
    return found


def _apply_client_name_guardrail(text: str, req: AdaptSectionRequest) -> str:
    client_name = _clean(req.context.client_name)
    if not client_name:
        return text.strip()
    guarded = text
    for candidate in _reference_client_candidates(req.reference_content):
        if candidate.lower() == client_name.lower():
            continue
        guarded = re.sub(re.escape(candidate), client_name, guarded, flags=re.IGNORECASE)
    guarded = re.sub(r"\bthe bank\b", client_name, guarded, flags=re.IGNORECASE) if client_name.lower().startswith("bank ") else guarded
    return guarded.strip()


def _markdown_headings(text: str) -> list[str]:
    found = re.findall(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*$", text or "")
    if found:
        return [_clean(item) for item in found if _clean(item)]
    return []


def _reference_structure(text: str) -> str:
    headings = _markdown_headings(text)
    if headings:
        return "\n".join(f"- {item}" for item in headings)
    bullets = re.findall(r"(?m)^\s*[-*]\s+(.+?)\s*$", text or "")
    if bullets:
        return "\n".join(f"- {item}" for item in bullets[:8])
    return "- Preserve the original paragraph structure."


def _context_facts(req: AdaptSectionRequest) -> list[str]:
    intake = req.context.intake
    facts = [
        f"Client name: {req.context.client_name}" if req.context.client_name else "",
        f"Client profile: {req.context.client_profile}" if req.context.client_profile else "",
        f"Project mode: {intake.project_mode}" if intake.project_mode else "",
        f"Upgrade type: {intake.upgrade_type}" if intake.upgrade_type else "",
        f"Current system: {intake.current_system}" if intake.current_system else "",
        f"Current version: {intake.current_version}" if intake.current_version else "",
        f"Target version: {intake.target_version}" if intake.target_version else "",
        f"Delivery model: {intake.delivery_model}" if intake.delivery_model else "",
        f"Implementation methodology: {intake.implementation_methodology}" if intake.implementation_methodology else "",
        f"Selected documents: {', '.join(req.context.selected_documents)}" if req.context.selected_documents else "",
    ]
    return [item for item in facts if item]


async def _build_brief(req: AdaptSectionRequest, evidence_lines: list[str]) -> ProposalBrief:
    llm = get_llm()
    prompt = f"""
Return JSON with keys:
- summary: short string
- must_change: array of strings
- must_preserve: array of strings
- forbidden_claims: array of strings
- prompt_directives: array of strings

You are preparing a conservative edit plan for a proposal section adaptation.
Reference section title: {req.section_title}
User prompt: {req.prompt or "(none)"}
Section-specific instruction: {req.instruction or "(none)"}

CLIENT FACTS
{chr(10).join(f"- {item}" for item in _context_facts(req)) or "- none"}

REFERENCE SECTION
{req.reference_content[:4000]}

RETRIEVED FACTS
{chr(10).join(f"- {line}" for line in evidence_lines[:16]) or "- none"}

Rules:
- Focus on what must change from the reference to fit the target client.
- Preserve the contractual and operational tone of the reference.
- Do not suggest unsupported benefits or marketing claims.
- If the reference contains static legal or company profile content, preserve it.
"""
    data = await llm.chat_json(
        [
            {"role": "system", "content": "You produce strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        model=req.model,
        temperature=0.1,
        max_tokens=800,
    )
    return ProposalBrief.model_validate(data)


def _validate_output(text: str, req: AdaptSectionRequest, brief: ProposalBrief) -> list[str]:
    cleaned = _clean(text)
    lowered = cleaned.lower()
    notes: list[str] = []
    if not cleaned:
        raise LLMError("Adaptation returned empty content.")
    if any(lowered.startswith(marker) for marker in _COMMENTARY_MARKERS):
        raise LLMError("Section adaptation returned commentary instead of proposal content.")
    if len(cleaned.split()) < 120:
        notes.append("output is shorter than the reference-style target")
    reference_headings = req.reference_headings or _markdown_headings(req.reference_content)
    if reference_headings:
        present = sum(1 for heading in reference_headings if heading.lower() in lowered)
        if present < max(1, len(reference_headings) // 2):
            notes.append("output preserved fewer reference subheadings than expected")
    reference_corpus = f"{req.reference_content}\n" + "\n".join(brief.must_change) + "\n".join(brief.must_preserve)
    reference_lower = reference_corpus.lower()
    for phrase in list(_MARKETING_PHRASES) + list(brief.forbidden_claims):
        needle = (phrase or "").strip().lower()
        if needle and needle in lowered and needle not in reference_lower:
            raise LLMError(f"unsupported claim introduced: {phrase}")
    client_name = _clean(req.context.client_name)
    if client_name and client_name.lower() not in lowered:
        notes.append("client name not present in adapted output")
    return notes


def _needs_retry(content: str, req: AdaptSectionRequest) -> bool:
    cleaned = _clean(content)
    if not cleaned:
        return True
    client_name = _clean(req.context.client_name)
    if client_name and client_name.lower() not in cleaned.lower():
        return True
    if req.prompt or req.instruction:
        ref_words = _normalized_words(req.reference_content)
        out_words = _normalized_words(cleaned)
        if ref_words and out_words:
            overlap = sum(1 for a, b in zip(ref_words, out_words) if a == b)
            similarity = overlap / max(min(len(ref_words), len(out_words)), 1)
            if similarity > 0.82:
                return True
    return False


async def _retry_adaptation(
    req: AdaptSectionRequest,
    brief: ProposalBrief,
    evidence_lines: list[str],
    initial_content: str,
) -> str:
    llm = get_llm()
    client_name = _clean(req.context.client_name) or "the target client"
    retry_prompt = f"""
Revise the section below because the first adaptation did not sufficiently apply the master prompt.

You must:
- explicitly incorporate the client name "{client_name}" naturally in the section;
- apply the user prompt and section instruction materially, not cosmetically;
- keep the reference structure and professional proposal tone;
- avoid commentary and unsupported claims;
- make real edits where the prompt requires edits.

MASTER PROMPT
{req.prompt or "(none)"}

SECTION INSTRUCTION
{req.instruction or "(none)"}

CHANGE PLAN
{chr(10).join(f"- {item}" for item in brief.must_change[:10]) or "- Apply the requested client/context changes."}

CLIENT FACTS
{chr(10).join(f"- {item}" for item in _context_facts(req)) or "- none"}

RETRIEVED SUPPORTING FACTS
{chr(10).join(f"- {item}" for item in evidence_lines[:18])}

REFERENCE SECTION
{req.reference_content}

FIRST ADAPTATION THAT MUST BE IMPROVED
{initial_content}

Return final proposal content only.
"""
    return await llm.chat(
        [
            {"role": "system", "content": "You revise proposal sections and must apply the master prompt precisely."},
            {"role": "user", "content": retry_prompt},
        ],
        model=req.model,
        temperature=0.12,
        max_tokens=2200,
    )


async def adapt_section(req: AdaptSectionRequest) -> AdaptSectionResponse:
    llm = get_llm()
    if not llm.available:
        raise LLMError("LLM generation is unavailable. Configure a valid API key in Settings.")

    evidence = retrieve_for_section(
        section_title=req.section_title,
        keywords=_markdown_headings(req.reference_content) or req.reference_headings or [],
        context=req.context,
        proposal_family=req.proposal_family,
        top_k=req.top_k,
        include_temenos_official=req.include_temenos_official,
        use_hybrid_retrieval=req.use_hybrid_retrieval,
    )
    if req.require_evidence and not evidence:
        raise LLMError("No evidence retrieved for the selected section and selected documents.")

    evidence_lines = []
    for chunk in evidence[:10]:
        label = _clean(chunk.source_section or chunk.summary or "Evidence")
        fact = _clean(chunk.text)
        if fact:
            evidence_lines.append(f"[{label}] {fact[:420]}")

    brief = await _build_brief(req, evidence_lines)
    structure = _reference_structure(req.reference_content)
    plan = [AdaptationChange(kind="preserve", detail=item) for item in brief.must_preserve[:6]]
    plan.extend(AdaptationChange(kind="replace", detail=item) for item in brief.must_change[:8])

    prompt = f"""
Adapt the reference proposal section into final client-ready proposal content.

SECTION TITLE
{req.section_title}

CLIENT FACTS
{chr(10).join(f"- {item}" for item in _context_facts(req)) or "- none"}

USER PROMPT
{req.prompt or "(none)"}

SECTION INSTRUCTION
{req.instruction or "(none)"}

REFERENCE SECTION TO ADAPT
{req.reference_content}

REFERENCE STRUCTURE TO PRESERVE
{structure}

CHANGE PLAN
{chr(10).join(f"- {item.detail}" for item in brief.must_change[:10]) or "- Apply only explicit client/version/scope changes."}

MUST PRESERVE
{chr(10).join(f"- {item}" for item in brief.must_preserve[:10]) or "- Preserve the operational tone and structure of the reference."}

FORBIDDEN CLAIMS
{chr(10).join(f"- {item}" for item in (brief.forbidden_claims or list(_MARKETING_PHRASES)))}

RETRIEVED SUPPORTING FACTS
{chr(10).join(f"- {item}" for item in evidence_lines[:18])}

Rules:
- Perform a conservative adaptation of the reference; do not rewrite it into consulting prose.
- Keep the reference section structure, subheadings, bullet style, and operational tone wherever possible.
- Only add, remove, or change statements that are required by the client facts, retrieved facts, or the user instruction.
- If a claim is not explicitly supported by the retrieved facts or already present in the reference, omit it.
- Do not mention evidence, source documents, chunk names, or reasoning.
- Do not output XML or HTML tags.
- Return final proposal content only.
"""
    content = await llm.chat(
        [
            {"role": "system", "content": "You produce submission-ready proposal sections by conservatively adapting a reference section."},
            {"role": "user", "content": prompt},
        ],
        model=req.model,
        temperature=0.15,
        max_tokens=2200,
    )
    if _needs_retry(content, req):
        content = await _retry_adaptation(req, brief, evidence_lines, content)
    content = _apply_client_name_guardrail(content, req)
    notes = _validate_output(content, req, brief)
    section = SectionResult(
        title=req.section_title,
        content=content.strip(),
        evidence=evidence,
        locked=False,
        model=llm.resolve_model(req.model),
    )
    return AdaptSectionResponse(
        section=section,
        brief=brief,
        change_plan=plan,
        validation_notes=notes,
    )
