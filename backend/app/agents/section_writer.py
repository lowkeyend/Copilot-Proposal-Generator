"""Agent 7 - Section Writer Agent.

Generates the proposal ONE section at a time (never the whole document at
once). Each call receives the client context, the section name, retrieved
evidence chunks, the proposal family, and pattern guidance, and produces
professional, grounded section content. Supports targeted regeneration via a
free-form `instruction` (e.g. "make it shorter", "rewrite the timeline").
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from docx import Document
from app.agents.retrieval_agent import retrieve_for_section
from app.config import ROOT_DIR, get_settings
from app.models.schemas import (
    EvidenceChunk,
    GenerateSectionRequest,
    SectionResult,
)
from app.services.llm_service import LLMError, get_llm


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_GROUNDING_IGNORE_TERMS = {
    "will",
    "shall",
    "would",
    "could",
    "should",
    "from",
    "with",
    "that",
    "this",
    "these",
    "those",
    "their",
    "there",
    "into",
    "through",
    "during",
    "over",
    "under",
    "about",
    "after",
    "before",
    "technical",
    "project",
    "scope",
    "solution",
    "proposed",
    "client",
    "delivery",
    "support",
    "phase",
    "phased",
    "upgrade",
    "core",
    "bank",
    "banking",
    "temenos",
    "transact",
}
_CONSULTING_PHRASES = (
    "improved performance",
    "enhanced architecture",
    "stronger security controls",
    "new product capabilities",
    "future readiness",
    "business value",
    "strategic transformation",
    "accelerated realization",
    "operating model",
    "target state",
)
_MODULE_SCOPE_HEADING_SCHEMA = [
    "Implementation Scope",
    "Functional Coverage",
    "Configuration & Processing",
    "Interfaces & Controls",
    "Testing & Handover",
]
_UNSUPPORTED_MODULE_SCOPE_PHRASES = (
    "deployment support",
    "cutover planning",
    "go-live execution",
    "go live execution",
    "production environment",
    "production deployment",
    "deployment documentation",
    "rollback planning",
    "hypercare",
    "post go-live support",
    "stabilization",
)
_REFERENCE_SECTION_SCHEMAS: dict[str, dict[str, object]] = {
    "scope of work": {
        "subheadings": [
            "Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ",
            "Environment Readiness Assessment",
            "Upgrade Analysis",
            "Core Technical Upgrade",
            "Customization & Interface Retrofit",
            "Testing",
            "Deployment & Go-Live",
            "Post Go-Live Support",
        ],
        "minimum_matches": 4,
    },
    "proposed solution": {
        "subheadings": [
            "Target Solution Principles",
            "Upgrade Approach",
            "Environment Assessment",
            "Upgrade Execution",
            "Customization Retrofit",
            "Testing & Validation",
            "Cutover & Stabilization",
        ],
        "minimum_matches": 4,
    },
    "upgrade methodology": {
        "subheadings": [
            "General Upgrade Activities",
            "Stage 1: Project Initiation",
            "Review of SOW",
            "Runbook Template",
            "Hardware Sizing",
            "Analysis Utility Setup",
            "Stage 2: Project Planning",
            "Stage 3: Upgrade Analysis",
            "Data Integrity Health Check",
            "Identify local jobs and CORE Batches",
            "Stage 4: Technical Upgrade",
            "Perform Core Upgrade",
            "GL Reconciliation",
            "Stage 5: Unit testing in integrated environment before delivery to client",
            "Stage 6: Upgrade Training",
            "Pre-UAT Training",
            "Stage 7: System Integration Testing",
            "Stage 8: User Acceptance Testing",
            "Stage 9: Mock Upgrade and Dress Rehearsals",
            "Stage 10: Pre-GO LIVE",
            "Stage 11: GO LIVE",
            "Stage 12: Post GO LIVE Support",
            "Planning and Control",
        ],
        "minimum_matches": 6,
    },
    "project governance": {
        "subheadings": [
            "Communication Plan",
            "Quality Management",
            "Change Management",
            "Project Issue Escalation Management",
            "Review Board",
            "Steering Committee",
            "Governance Model",
        ],
        "minimum_matches": 4,
    },
}
_REFERENCE_SECTION_LAYOUTS: dict[str, list[tuple[int, str]]] = {
    "introduction": [
        (2, "Proprietary Notice"),
        (2, "Validity Period"),
        (2, "Contact Details"),
    ],
    "scope of work": [
        (2, "Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ"),
        (3, "Environment Readiness Assessment"),
        (3, "Upgrade Analysis"),
        (3, "Core Technical Upgrade"),
        (3, "Customization & Interface Retrofit"),
        (3, "Testing"),
        (3, "Deployment & Go-Live"),
        (3, "Post Go-Live Support"),
    ],
    "proposed solution": [
        (2, "Target Solution Principles"),
        (3, "Target Solution Principles"),
        (3, "Upgrade Approach"),
        (4, "Environment Assessment"),
        (4, "Upgrade Execution"),
        (4, "Customization Retrofit"),
        (4, "Testing & Validation"),
        (4, "Cutover & Stabilization"),
    ],
    "upgrade methodology": [
        (2, "General Upgrade Activities"),
        (3, "Stage 1: Project Initiation"),
        (4, "Review of SOW"),
        (4, "Runbook Template"),
        (4, "Run Book template standardization for client."),
        (4, "Hardware Sizing"),
        (4, "Analysis Utility Setup"),
        (3, "Stage 2: Project Planning"),
        (3, "Stage 3: Upgrade Analysis"),
        (4, "Data Integrity Health Check"),
        (4, "Identify local jobs and CORE Batches"),
        (3, "Stage 4: Technical Upgrade"),
        (4, "Perform technology upgrades as per analysis identification."),
        (4, "Perform Core Upgrade"),
        (4, "Post upgrade verification for successful and complete Upgrade"),
        (4, "GL Reconciliation"),
        (3, "Stage 5: Unit testing in integrated environment before delivery to client"),
        (4, "Unit Testing of functionality"),
        (4, "Unit Testing of interfaces"),
        (4, "Unit Testing of Gpacks"),
        (3, "Stage 6: Upgrade Training"),
        (4, "Pre-UAT Training"),
        (4, "Technical and admin Training advance level"),
        (4, "Functional Training covering new features"),
        (3, "Stage 7: System Integration Testing"),
        (3, "Stage 8: User Acceptance Testing"),
        (3, "Stage 9: Mock Upgrade and Dress Rehearsals"),
        (3, "Stage 10: Pre-GO LIVE"),
        (3, "Stage 11: GO LIVE"),
        (3, "Stage 12: Post GO LIVE Support"),
        (2, "Planning and Control"),
    ],
    "project timeline": [
        (3, "Core Banking Upgrade R19 to R26"),
    ],
    "project governance": [
        (2, "Communication Plan"),
        (2, "Quality Management"),
        (2, "Change Management"),
        (2, "Project Issue Escalation Management"),
        (3, "Review Board"),
        (3, "Steering Committee"),
        (2, "Governance Model"),
    ],
}


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


def _support_terms(text: str) -> set[str]:
    return {
        term
        for term in _section_keywords_from_text(text)
        if term not in _GROUNDING_IGNORE_TERMS
    }


def _section_style_guide(req: GenerateSectionRequest) -> str:
    title = (req.section_title or "").strip().lower()
    if title == "scope of work":
        if _is_module_scope_request(req):
            return (
                "- Write as a contractual module-implementation scope section, not as an upgrade scope and not as product marketing.\n"
                "- Use a clear lead paragraph followed by concise subheadings for implementation scope, functional coverage, configuration, interfaces, controls, and testing where supported.\n"
                "- State only in-scope implementation activities and supported deliverables.\n"
                "- Do not introduce deployment, cutover, rollback, hypercare, post-go-live support, or production-readiness activities unless those exact items are explicitly supported by the evidence facts.\n"
                "- Do not reuse upgrade-specific headings such as Environment Readiness Assessment, Upgrade Analysis, Core Technical Upgrade, Deployment & Go-Live, or Post Go-Live Support.\n"
                "- Prefer precise operational wording over broad capability summaries."
            )
        return (
            "- Write in a contractual implementation style, not a consulting style.\n"
            "- Preserve the source section structure where supported, including specific workstream headings and activity lists.\n"
            "- Do not regroup the scope into invented milestone buckets unless those exact buckets appear in the evidence.\n"
            "- State the work packages, activities, boundaries, deliverables, testing scope, deployment scope, and out-of-scope items only where supported.\n"
            "- Prefer procedural and activity-based wording such as assessment, installation, retrofit, validation, reconciliation, testing, cutover, and post-go-live support.\n"
            "- Do not add business benefits, strategic outcomes, governance commentary, or generalized platform advantages."
        )
    if title in {"proposed solution", "solution"}:
        return (
            "- Describe the technical solution and upgrade approach in operational terms.\n"
            "- Preserve source terms such as like-for-like upgrade, retrofit, GPACK, COB validation, Data Integrity Health Check, runbook, interfaces, and reconciliation whenever the evidence supports them.\n"
            "- Do not rewrite the section as a product marketing narrative or introduce unstated benefits."
        )
    if title in {"upgrade methodology", "methodology"}:
        return (
            "- Write as a stage-by-stage implementation procedure.\n"
            "- Preserve named activities, utilities, reviews, validations, and testing stages from the evidence.\n"
            "- Do not summarize away operational artifacts into generic methodology language."
        )
    if title in {"project governance", "governance"}:
        return (
            "- Restrict the content to governance, communication, quality management, escalation, committees, and control mechanisms supported by evidence.\n"
            "- Do not add solution scope, benefits, or implementation tasks unless the evidence explicitly places them in governance."
        )
    if title in {"executive summary", "introduction"}:
        return (
            "- Keep the summary factual and proposal-like.\n"
            "- State what the engagement covers, current-to-target release context, and the implementation approach only where supported.\n"
            "- Do not promise benefits, improvements, or capabilities that are not explicitly stated in the evidence."
        )
    return (
        "- Match the source document genre: operational, implementation-focused, and procedural.\n"
        "- Prefer concrete activities, artifacts, controls, and responsibilities over generalized interpretation."
    )


def _section_boundary_rules(req: GenerateSectionRequest) -> str:
    title = (req.section_title or "").strip().lower()
    if title == "scope of work":
        if _is_module_scope_request(req):
            return (
                "- Exclude upgrade-release wording, release-to-release uplift statements, environment readiness, rollback, deployment support, go-live execution, production deployment, hypercare, and generic deliverable lists unless explicitly supported by the evidence facts.\n"
                "- Exclude governance bodies, executive sponsorship, communication plans, PMO language, operating-model language, and strategic-value commentary.\n"
                "- Exclude inferred benefits such as improved performance, stronger controls, enhanced architecture, audit readiness, or risk reduction unless those exact outcomes appear in the evidence facts."
            )
        return (
            "- Exclude governance bodies, executive sponsorship, communication plans, PMO language, and strategic-value commentary unless explicitly present in scope evidence.\n"
            "- Exclude inferred benefits such as improved performance, enhanced architecture, stronger security, and new capabilities unless those exact benefits appear in the evidence."
        )
    if title in {"proposed solution", "solution"}:
        return (
            "- Exclude company profile content, awards, staffing scale, and generic value statements.\n"
            "- Keep focus on technical principles, environments, retrofit approach, validation, and cutover mechanics."
        )
    if title in {"upgrade methodology", "methodology"}:
        return (
            "- Exclude governance narrative and benefits language.\n"
            "- Focus on stages, activities, checkpoints, testing, reviews, and transition tasks."
        )
    return "- Exclude content that belongs to other sections unless the evidence explicitly places it here."


def _reference_section_schema(req: GenerateSectionRequest) -> str:
    if (req.section_title or "").strip().lower() == "scope of work" and _is_module_scope_request(req):
        return (
            "For module implementation scope sections, use this structure where the evidence supports it:\n- "
            + "\n- ".join(_MODULE_SCOPE_HEADING_SCHEMA)
        )
    schema = _REFERENCE_SECTION_SCHEMAS.get((req.section_title or "").strip().lower())
    if not schema:
        return "No fixed reference subheading schema is enforced for this section."
    subheadings = schema.get("subheadings", [])
    if not subheadings:
        return "No fixed reference subheading schema is enforced for this section."
    return (
        "Mirror the reference proposal section structure where the evidence supports it. "
        "Use these subheadings in the same spirit and sequence, omitting only those with no support:\n- "
        + "\n- ".join(str(item) for item in subheadings)
    )

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


def _evidence_facts(chunks: list[EvidenceChunk], section_keywords: list[str]) -> list[str]:
    facts: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        points = _extract_support_points(chunk, section_keywords, limit=3)
        for point in points:
            key = re.sub(r"[^a-z0-9]+", " ", point.lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            facts.append(point)
            if len(facts) >= 18:
                return facts
    return facts


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


def _normalize_heading_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _split_compound_items(text: str) -> list[str]:
    cleaned = _clean_phrase(text)
    if not cleaned:
        return []
    parts = _split_sentences(cleaned)
    if len(parts) > 1:
        return _dedupe_preserve_order([part.rstrip(".") + "." for part in parts if part])
    compound = re.split(r"(?<=[a-z\)])\s+(?=[A-Z][A-Za-z0-9&/-]{2,})", cleaned)
    items = [_clean_phrase(item).rstrip(".") + "." for item in compound if len(_clean_phrase(item).split()) >= 2]
    return _dedupe_preserve_order(items or [cleaned.rstrip(".") + "."])


def _matches_reference_heading(chunk: EvidenceChunk, heading: str) -> bool:
    normalized_heading = _normalize_heading_key(heading)
    normalized_section = _normalize_heading_key(chunk.source_section or "")
    normalized_summary = _normalize_heading_key(chunk.summary or "")
    if not normalized_heading:
        return False
    return any(
        value and (normalized_heading in value or value in normalized_heading)
        for value in (normalized_section, normalized_summary)
    )


def _reference_heading_chunks(evidence: list[EvidenceChunk], heading: str) -> list[EvidenceChunk]:
    return [chunk for chunk in evidence if _matches_reference_heading(chunk, heading)]


def _compile_heading_block(level: int, heading: str, chunks: list[EvidenceChunk]) -> str:
    if not chunks:
        return ""
    prefix = "#" * max(2, min(level, 4))
    lines = [f"{prefix} {heading}"]
    seen: set[str] = set()
    for chunk in chunks:
        for item in _split_compound_items(chunk.text or ""):
            key = re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            lines.append(f"- {item.rstrip('.')}")
    return "\n".join(lines)


def _candidate_document_paths(name: str) -> list[Path]:
    cleaned = (name or "").strip()
    if not cleaned:
        return []
    settings = get_settings()
    candidates = [
        ROOT_DIR / "data" / cleaned,
        ROOT_DIR.parent / "data" / cleaned,
        settings.templates_path / cleaned,
        settings.templates_path / "master_proposal_template.docx",
    ]
    seen: set[str] = set()
    output: list[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        output.append(path)
    return output


def _is_heading_style(style_name: str) -> bool:
    lowered = (style_name or "").strip().lower()
    return lowered.startswith("heading") or lowered.startswith("cn head")


@lru_cache(maxsize=32)
def _load_document_heading_map(path_str: str) -> dict[str, list[str]]:
    path = Path(path_str)
    doc = Document(str(path))
    sections: dict[str, list[str]] = {}
    current_heading = ""
    for paragraph in doc.paragraphs:
        text = _clean_phrase(paragraph.text or "")
        if not text:
            continue
        style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
        if _is_heading_style(style_name):
            current_heading = text
            sections.setdefault(current_heading, [])
            continue
        if current_heading:
            sections.setdefault(current_heading, []).append(text)
    return sections


def _local_document_heading_map(req: GenerateSectionRequest) -> dict[str, list[str]]:
    names = [name for name in getattr(req.context, "selected_documents", []) or [] if name]
    for name in names:
        for path in _candidate_document_paths(name):
            if path.exists() and path.suffix.lower() == ".docx":
                return _load_document_heading_map(str(path.resolve()))
    template = get_settings().proposal_template_path
    if template.exists():
        return _load_document_heading_map(str(template.resolve()))
    return {}


def _reference_summary_paragraph(req: GenerateSectionRequest, evidence: list[EvidenceChunk]) -> str:
    heading_map = _local_document_heading_map(req)
    local_lines = heading_map.get("Executive Summary", [])
    if local_lines:
        paragraphs = [
            re.sub(r"Alkuraimi(?: Islamic)? Bank", req.context.client_name or "the client", line, flags=re.IGNORECASE)
            for line in local_lines
        ]
        return "\n\n".join(paragraphs)
    facts = _evidence_facts(evidence, _section_keywords(req))
    if not facts:
        return ""
    client = req.context.client_name or "the client"
    paragraphs: list[str] = []
    lead_facts = " ".join(facts[:2])
    if lead_facts:
        paragraphs.append(re.sub(r"Alkuraimi Bank", client, lead_facts, flags=re.IGNORECASE))
    if len(facts) > 2:
        paragraphs.append(re.sub(r"Alkuraimi Bank", client, " ".join(facts[2:5]), flags=re.IGNORECASE))
    if len(facts) > 5:
        paragraphs.append(re.sub(r"Alkuraimi Bank", client, " ".join(facts[5:8]), flags=re.IGNORECASE))
    return "\n\n".join(_dedupe_preserve_order([_clean_phrase(p) for p in paragraphs if p]))


def _compile_reference_layout(req: GenerateSectionRequest, evidence: list[EvidenceChunk]) -> str:
    title = (req.section_title or "").strip().lower()
    layout = _REFERENCE_SECTION_LAYOUTS.get(title)
    heading_map = _local_document_heading_map(req)
    if title == "executive summary":
        return _reference_summary_paragraph(req, evidence)
    if title == "assumptions":
        local_lines = heading_map.get("Assumptions", [])
        if local_lines:
            return "\n".join(f"- {re.sub(r'Alkuraimi(?: Islamic)? Bank', req.context.client_name or 'the client', line, flags=re.IGNORECASE).rstrip('.')}" for line in local_lines)
        chunks = _reference_heading_chunks(evidence, "Assumptions") or evidence
        lines = []
        seen: set[str] = set()
        for chunk in chunks:
            for item in _split_compound_items(chunk.text or ""):
                key = re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                lines.append(f"- {item.rstrip('.')}")
        return "\n".join(lines)
    if not layout:
        return ""

    blocks: list[str] = []
    for level, heading in layout:
        local_lines = heading_map.get(heading, [])
        if local_lines:
            prefix = "#" * max(2, min(level, 4))
            lines = [f"{prefix} {heading}"]
            for line in local_lines:
                rendered = re.sub(
                    r"Alkuraimi(?: Islamic)? Bank",
                    req.context.client_name or "the client",
                    line,
                    flags=re.IGNORECASE,
                )
                if level <= 2:
                    suffix = "" if rendered.rstrip().endswith(":") else "."
                    lines.append(rendered.rstrip(".") + suffix)
                else:
                    lines.append(f"- {rendered.rstrip('.')}")
            blocks.append("\n".join(lines))
            continue
        heading_chunks = _reference_heading_chunks(evidence, heading)
        if not heading_chunks and heading == "Core Upgrade: Temenos Transact R19 TAFJ to R26 TAFJ":
            heading_chunks = _reference_heading_chunks(evidence, "Core Upgrade")
        block = _compile_heading_block(level, heading, heading_chunks)
        if block:
            blocks.append(block)
    return "\n\n".join(blocks).strip()


def _should_use_reference_compiler(req: GenerateSectionRequest) -> bool:
    title = (req.section_title or "").strip().lower()
    return (
        (req.proposal_family or "").strip().lower() == "temenos"
        and "upgrade" in (req.context.project_type or "").lower()
        and title in set(_REFERENCE_SECTION_LAYOUTS) | {"executive summary", "assumptions"}
    )


def _reference_compiler_available(req: GenerateSectionRequest) -> bool:
    if not _should_use_reference_compiler(req):
        return False
    heading_map = _local_document_heading_map(req)
    if heading_map:
        return True
    return bool(get_settings().proposal_template_path.exists())


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


def _static_company_profile(req: GenerateSectionRequest) -> str:
    client = req.context.client_name or "the client"
    return (
        f"### {req.section_title}\n\n"
        "Systems Limited is a globally recognized technology company with more than "
        "49 years of industry experience, specializing in digital transformation for "
        "the Banking and Financial Services industry. The company has established a "
        "strong reputation as a trusted partner to financial institutions worldwide "
        "through its work on complex core banking modernization programs, including "
        "Temenos Transact upgrades, migrations, and large-scale transformation "
        "initiatives.\n\n"
        "With a global delivery footprint, deep banking domain capability, and a "
        "disciplined delivery model, Systems Limited combines TIM-led execution with "
        "proprietary accelerators, a centralized library of pro-forma documents and "
        "processes, and a governance framework designed to maintain quality, "
        "consistency, and reusability across projects. This delivery approach is "
        "complemented by experience across assessment, retrofit, testing, cutover, "
        "training, and stabilization workstreams.\n\n"
        "The organisation collaborates with leading technology partners and supports "
        "banks through flexible delivery models, structured change management, and "
        "post-go-live support. Its scale, methodology, and Temenos experience provide "
        f"a strong foundation for supporting {client} through a controlled and "
        "submission-ready transformation program."
    )
_SYSTEM = (
    "You are a senior proposal writer for enterprise banking transformation bids. "
    "Write only final client-ready proposal prose. Do not explain your reasoning. "
    "Do not describe what the section should do. Do not mention evidence, chunks, "
    "retrieval, source documents, questionnaire context, or instructions. Use only "
    "the explicitly provided evidence facts and client context. If a claim is not "
    "directly supported, omit it. Do not use general banking or Temenos knowledge "
    "to fill gaps. Every sentence must be grounded in the evidence facts block or "
    "the client context. If you cannot support a sentence, do not write it. Use "
    "formal submission-ready language, preserve implementation specificity from "
    "the corpus, and write as if the text will be sent directly to the client."
)

_REPAIR_SYSTEM = (
    "You are an expert proposal editor. Rewrite flawed draft text into final "
    "client-ready proposal prose. Remove commentary, instructional language, "
    "evidence references, source references, unsupported claims, and duplicated "
    "phrases. Preserve only supported content from the evidence and client context. "
    "Return only the final section body."
)

_TEMPLATE = """Write the proposal section titled "{section_title}".

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

EVIDENCE FACTS (the only facts you may use):
{evidence_facts}

QUALITY CONTROLS
- Detail profile: {detail_level}
- Evidence-only mode: {require_evidence}
- Official Temenos website evidence included: {include_temenos}
- Section style requirements:
{section_style}
- Section boundary rules:
{section_boundaries}
- Reference section schema:
{reference_schema}
- The EVIDENCE FACTS block is the only source of truth for section claims.
- Do not use the raw evidence excerpts to invent new claims; distill them only
  into the facts shown above.
- Treat retrieved chunks as supporting context only; do not infer beyond the
  explicit facts above.
- The CLIENT CONTEXT is the ground truth for client type, product name, and
  implementation context.
- Use the client name exactly as "{client}" throughout.
- Use the canonical product name "{canonical_product}" consistently.
- If the client is not greenfield, do not use greenfield wording unless the
  evidence facts explicitly support it.
- If a claim cannot be supported by the evidence facts above, omit it.
- Prefer concrete wording over generic vendor language.
- Do not add background, market commentary, or industry claims unless the
  evidence facts explicitly support them.
- Do not mention source document names, chunk IDs, or source commentary in
  the final section.

Return the answer using exactly this format:
<section>
final section body only
</section>

The heading is added by the system, so do not include the section title inside
the section body. Match a formal proposal style:
- open with a crisp, substantive lead paragraph that sounds like a proposal section, not commentary;
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
- avoid generic marketing language, benefits language, and vague claims;
- do not rewrite procedural source material into advisory or consulting prose.
- when writing a module-implementation scope section, use bold markdown subheadings and grouped bullets instead of one dense paragraph.
- do not emit HTML or XML tags such as ul, li, p, div, or span.

Target {length} of well-structured content. Treat the lower bound as the
minimum acceptable depth unless the retrieved evidence is genuinely sparse.
Do not condense the material.
"""


def _format_evidence(chunks: list[EvidenceChunk]) -> str:
    if not chunks:
        return "(No matching evidence retrieved.)"

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
        header = _clean_phrase(c.summary or c.source_section or f"Evidence {i}")
        points = _extract_support_points(c, section_keywords, limit=2)
        if not points:
            continue
        lines.append(f"[EVIDENCE {i}] {header}\n- " + "\n- ".join(points))
    return "\n\n".join(lines)


def _format_evidence_facts(chunks: list[EvidenceChunk], req: GenerateSectionRequest) -> str:
    facts = _evidence_facts(chunks, _section_keywords(req))
    if not facts:
        return "(No explicit supporting facts found.)"
    lines: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        header = _clean_phrase(chunk.source_section or chunk.summary or "Evidence")
        for fact in _extract_support_points(chunk, _section_keywords(req), limit=4):
            key = re.sub(r"[^a-z0-9]+", " ", f"{header} {fact}".lower()).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            lines.append(f"- [{header}] {fact}")
            if len(lines) >= 24:
                return "\n".join(lines)
    return "\n".join(lines or [f"- {fact}" for fact in facts])

def _length_for(req: GenerateSectionRequest) -> str:
    if req.instruction:
        lowered = req.instruction.lower()
        if any(w in lowered for w in ("short", "concise", "brief")):
            return "350-650 words"
        if any(w in lowered for w in ("longer", "expand", "detail")):
            return "900-1300 words"
    if req.detail_level == "balanced":
        return "450-700 words"
    if req.detail_level == "exhaustive":
        return "1000-1400 words"
    return "700-1000 words"


def _minimum_words(req: GenerateSectionRequest) -> int:
    if req.instruction and any(
        w in req.instruction.lower() for w in ("short", "concise", "brief")
    ):
        return 240
    if req.detail_level == "balanced":
        return 320
    if req.detail_level == "exhaustive":
        return 700
    return 450


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


def _requested_modules(req: GenerateSectionRequest) -> list[str]:
    text = " ".join(filter(None, [req.prompt or "", req.instruction or "", req.section_title or ""]))
    matches = re.findall(
        r"\b(?:add|include|implement|introduce)\s+(?:the\s+|a\s+|an\s+)?([A-Za-z][A-Za-z0-9&/ +_-]{1,40}?)\s+module\b",
        text,
        flags=re.IGNORECASE,
    )
    modules: list[str] = []
    for match in matches:
        label = _clean_phrase(re.sub(r"^(the|a|an)\s+", "", match, flags=re.IGNORECASE))
        if label:
            modules.append(f"{label} module")
    return _dedupe_preserve_order(modules)


def _prompt_requests_upgrade(req: GenerateSectionRequest) -> bool:
    combined = _clean_phrase(" ".join(filter(None, [req.prompt or "", req.instruction or ""]))).lower()
    if not combined:
        intake = getattr(req.context, "intake", None)
        return bool(getattr(intake, "current_version", "") and getattr(intake, "target_version", ""))
    negative_patterns = (
        r"\bdo not frame (?:this|it) as (?:a |an )?technical upgrade\b",
        r"\bnot (?:a |an )?technical upgrade\b",
        r"\bdo not use upgrade wording\b",
        r"\bwithout upgrade wording\b",
        r"\bnot an upgrade\b",
    )
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in negative_patterns):
        return False
    explicit_upgrade = any(
        phrase in combined
        for phrase in (
            "technical upgrade",
            "upgrade from",
            "like-for-like upgrade",
            "current version",
            "target version",
            "r20 to",
            "r21 to",
            "r22 to",
            "r23 to",
            "r24 to",
            "r25 to",
            "r26 to",
        )
    )
    return explicit_upgrade


def _is_module_scope_request(req: GenerateSectionRequest) -> bool:
    title = (req.section_title or "").strip().lower()
    if title != "scope of work":
        return False
    modules = _requested_modules(req)
    return bool(modules) and not _prompt_requests_upgrade(req)


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
            r"\d+\s+\d+\s+Temenos Implementation Methodology\s+",
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
    content = re.sub(r"\d[\d\s]*Temenos\s+Implementation\s+Methodology\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"Temenos\s+Implementation\s+Methodology\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"(?m)^\s*\d+\s+\d+\s+", "", content)
    return content


def _remove_source_echoes(content: str) -> str:
    sentences = _split_sentences(content)
    kept: list[str] = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(
            term in lowered
            for term in (
                "documented procedure",
                "process step should be completed",
                "should be completed",
                "questionnaire context",
                "retrieved evidence",
                "source document",
                "source material",
                "chunk",
                "best practice",
                "final wording should",
                "write the section",
                "proposal section",
                "edit",
                "review",
                "appendix",
                "evidence labels",
                "selected sections are mentioned further below",
            )
        ):
            continue
        cleaned = re.sub(r"\b\d+(?:\.\d+){1,}\b", "", _clean_phrase(sentence))
        cleaned = _clean_phrase(cleaned)
        if len(cleaned.split()) < 4:
            continue
        kept.append(cleaned.rstrip(".") + ".")
    if kept:
        return " ".join(_dedupe_preserve_order(kept))
    return content


def _looks_like_commentary(content: str) -> bool:
    text = _clean_phrase(content).lower()
    if not text:
        return True
    signals = (
        "questionnaire context:",
        "the section should",
        "the final wording should",
        "should read like",
        "write the section now",
        "content was written from best practice",
        "retrieved evidence for this section",
        "evidence was retrieved for this section",
        "this means the retrieval step",
        "source commentary",
        "source material",
        "evidence labels",
        "the retrieved evidence supports",
        "revision request incorporated",
        "edit",
    )
    score = sum(1 for signal in signals if signal in text)
    if score >= 2:
        return True
    if text.startswith(("questionnaire context:", "the section should", "the final wording should")):
        return True
    return False


def _extract_section_block(text: str) -> str:
    match = re.search(r"<section>(.*?)</section>", text, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def _clean_model_output(text: str, section_title: str) -> str:
    cleaned = _extract_section_block(text)
    cleaned = re.sub(r"```(?:markdown|md|text)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "").strip()
    cleaned = cleaned.replace("<section>", "").replace("</section>", "")
    cleaned = re.sub(r"(?is)<li\b[^>]*>\s*", "\n- ", cleaned)
    cleaned = re.sub(r"(?is)</li\s*>", "\n", cleaned)
    cleaned = re.sub(r"(?is)<br\s*/?>", "\n", cleaned)
    cleaned = re.sub(r"(?is)</?(?:ul|ol)\b[^>]*>", "\n", cleaned)
    cleaned = re.sub(r"</?(?:title|paragraph|h1|h2|h3|body|html|xml|div|span|p|ul|ol|li|br)\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\{\{[^}]+\}\}", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*traceback \(most recent call last\):\s*$", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*file \".*?\", line \d+.*$", "", cleaned)
    cleaned = re.sub(r"(?im)^\s*.*site-packages.*$", "", cleaned)
    cleaned = _strip_leading_heading(cleaned, section_title)
    lines = cleaned.splitlines()
    if lines:
        first = _clean_phrase(lines[0]).lower().rstrip(":")
        title = _clean_phrase(section_title).lower().rstrip(":")
        if first == title:
            lines = lines[1:]
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"(?m)(The scope includes:)\s*-\s*", r"\1\n\n- ", cleaned)
    cleaned = re.sub(r"\s+-\s+", "\n- ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _validation_issues(
    content: str, req: GenerateSectionRequest, evidence: list[EvidenceChunk]
) -> list[str]:
    issues: list[str] = []
    text = _clean_phrase(content)
    lowered = text.lower()
    if not text:
        issues.append("output is empty")
        return issues
    if _looks_like_commentary(text):
        issues.append("output contains commentary or instruction-style language")
    if "<section>" in lowered or "</section>" in lowered:
        issues.append("output contains raw section tags")
    if re.search(r"</?(?:title|paragraph|h1|h2|h3|body|html|xml|div|span|p|ul|ol|li|br)\b", lowered):
        issues.append("output contains leaked markup tags")
    if "traceback (most recent call last)" in lowered:
        issues.append("output contains traceback text")
    forbidden_terms = (
        "source document",
        "source material",
        "retrieved evidence",
        "questionnaire context",
        "chunk ",
        "the section should",
        "the final wording should",
        "write the section",
        "word toc field",
        "open in word and refresh fields",
    )
    if any(term in lowered for term in forbidden_terms):
        issues.append("output mentions evidence or prompt mechanics")
    evidence_text = " ".join(
        _clean_phrase(
            " ".join(
                [
                    chunk.text or "",
                    chunk.summary or "",
                    chunk.source_section or "",
                ]
            )
        ).lower()
        for chunk in evidence
    )
    for phrase in _CONSULTING_PHRASES:
        if phrase in lowered and phrase not in evidence_text:
            issues.append(f"output introduces unsupported consulting-style claim: {phrase}")
    if evidence:
        evidence_terms = _grounding_evidence_terms(req, evidence)
        context_terms = _grounding_context_terms(req)
        content_terms = _support_terms(text)
        if content_terms and len(content_terms & evidence_terms) == 0:
            issues.append("output has weak lexical grounding against retrieved evidence")
        sentences = _split_sentences(text)
        unsupported_sentences = 0
        for sentence in sentences:
            sentence_terms = _support_terms(sentence)
            evidence_overlap = len(sentence_terms & evidence_terms)
            context_overlap = len(sentence_terms & context_terms)
            if len(sentence_terms) >= 4 and evidence_overlap + context_overlap < 2:
                unsupported_sentences += 1
        if unsupported_sentences >= 3:
            issues.append(
                f"output contains {unsupported_sentences} sentence(s) with weak evidence grounding"
            )
    if req.context.client_profile != "greenfield" and "greenfield" in lowered:
        issues.append("output applies greenfield language to a non-greenfield client context")
    canonical_product = _clean_phrase(req.context.canonical_product or "")
    if canonical_product:
        aliases = (
            "temenos core banking",
            "temenos banking platform",
        )
        if any(alias in lowered for alias in aliases) and canonical_product.lower() not in lowered:
            issues.append("output uses inconsistent product naming")
    if (req.section_title or "").strip().lower() == "scope of work":
        forbidden = (
            "executive sponsorship",
            "steering committee",
            "communication plan",
            "governance model",
            "operating model",
            "strategic transformation",
        )
        for phrase in forbidden:
            if phrase in lowered and phrase not in evidence_text:
                issues.append(f"scope section contains cross-section leakage: {phrase}")
        if _is_module_scope_request(req):
            for phrase in _UNSUPPORTED_MODULE_SCOPE_PHRASES:
                if phrase in lowered and phrase not in evidence_text:
                    issues.append(f"scope section contains unsupported module-implementation leakage: {phrase}")
    schema = _REFERENCE_SECTION_SCHEMAS.get((req.section_title or "").strip().lower())
    if (req.section_title or "").strip().lower() == "scope of work" and _is_module_scope_request(req):
        schema = {"subheadings": _MODULE_SCOPE_HEADING_SCHEMA, "minimum_matches": 2}
    if schema:
        subheadings = [str(item) for item in schema.get("subheadings", [])]
        minimum_matches = int(schema.get("minimum_matches", 0) or 0)
        if len(subheadings) >= 4:
            minimum_matches = min(minimum_matches, 3)
        heading_matches = sum(1 for heading in subheadings if heading.lower() in lowered)
        if minimum_matches and heading_matches < minimum_matches:
            issues.append(
                f"output does not follow the reference section structure closely enough ({heading_matches}/{minimum_matches} headings found)"
            )
    return issues


def _should_expand(content: str, req: GenerateSectionRequest) -> bool:
    return len(_clean_phrase(content).split()) < _minimum_words(req)


def _grounding_context_terms(req: GenerateSectionRequest) -> set[str]:
    context_parts = [
        req.context.client_name or "",
        req.context.industry or "",
        req.context.canonical_product or "",
    ]
    return _support_terms(" ".join(context_parts))


def _grounding_evidence_terms(
    req: GenerateSectionRequest, evidence: list[EvidenceChunk]
) -> set[str]:
    terms: set[str] = set()
    for fact in _evidence_facts(evidence, _section_keywords(req)):
        terms.update(_support_terms(fact))
    for chunk in evidence:
        terms.update(_support_terms(chunk.summary or ""))
        terms.update(_support_terms(chunk.source_section or ""))
        terms.update(_support_terms((chunk.text or "")[:400]))
    return terms


def _prune_unsupported_sentences(
    content: str, req: GenerateSectionRequest, evidence: list[EvidenceChunk]
) -> str:
    evidence_terms = _grounding_evidence_terms(req, evidence)
    context_terms = _grounding_context_terms(req)
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", content or "") if part.strip()]
    kept_paragraphs: list[str] = []
    for paragraph in paragraphs:
        units = [line.strip() for line in paragraph.splitlines() if line.strip()] if paragraph.lstrip().startswith(("#", "-", "*")) else _split_sentences(paragraph)
        kept_sentences: list[str] = []
        for sentence in units:
            if _is_module_scope_request(req):
                low = sentence.lower()
                if any(phrase in low and phrase not in " ".join((_clean_phrase(chunk.text or "").lower() for chunk in evidence)) for phrase in _UNSUPPORTED_MODULE_SCOPE_PHRASES):
                    continue
            sentence_terms = _support_terms(sentence)
            evidence_overlap = len(sentence_terms & evidence_terms)
            context_overlap = len(sentence_terms & context_terms)
            if len(sentence_terms) < 4 or evidence_overlap + context_overlap >= 2:
                kept_sentences.append(sentence)
        if kept_sentences:
            kept_paragraphs.append("\n".join(kept_sentences) if paragraph.lstrip().startswith(("#", "-", "*")) else " ".join(kept_sentences))
    return "\n\n".join(kept_paragraphs).strip()


async def _generate_via_llm(
    llm,
    req: GenerateSectionRequest,
    evidence: list[EvidenceChunk],
    length: str,
    instruction_block: str,
) -> str:
    return await llm.chat(
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
                    canonical_product=req.context.canonical_product or "Temenos Transact",
                    intake_summary=_intake_summary(req.context) or "none provided",
                    family=req.proposal_family or "-",
                    tone=req.context.tone or "Formal",
                    special=req.context.special_instructions or "none",
                    guidance=req.pattern_guidance or "Follow the family's standard structure.",
                    prompt=req.prompt or "-",
                    instruction_block=instruction_block,
                    evidence=_format_evidence(evidence),
                    evidence_facts=_format_evidence_facts(evidence, req),
                    detail_level=req.detail_level,
                    require_evidence="enabled" if req.require_evidence else "disabled",
                    include_temenos="yes" if req.include_temenos_official else "no",
                    section_style=_section_style_guide(req),
                    section_boundaries=_section_boundary_rules(req),
                    reference_schema=_reference_section_schema(req),
                    length=length,
                ),
            },
        ],
        model=req.model,
        temperature=0.0,
        max_tokens=1800,
    )


async def _repair_via_llm(
    llm,
    req: GenerateSectionRequest,
    evidence: list[EvidenceChunk],
    draft: str,
    issues: list[str],
) -> str:
    issue_list = "\n".join(f"- {issue}" for issue in issues)
    return await llm.chat(
        [
            {"role": "system", "content": _REPAIR_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"SECTION TITLE: {req.section_title}\n"
                    f"CLIENT: {req.context.client_name or 'the client'}\n"
                    f"CANONICAL PRODUCT: {req.context.canonical_product or 'Temenos Transact'}\n"
                    f"CLIENT PROFILE: {req.context.client_profile or 'established'}\n\n"
                    "EVIDENCE FACTS (the only facts you may use)\n"
                    f"{_format_evidence_facts(evidence, req)}\n\n"
                    "SECTION STYLE REQUIREMENTS\n"
                    f"{_section_style_guide(req)}\n\n"
                    "SECTION BOUNDARY RULES\n"
                    f"{_section_boundary_rules(req)}\n\n"
                    "REFERENCE SECTION SCHEMA\n"
                    f"{_reference_section_schema(req)}\n\n"
                    "DRAFT TO REWRITE\n"
                    f"{draft}\n\n"
                    "PROBLEMS TO FIX\n"
                    f"{issue_list}\n\n"
                    "Return only the corrected final section body inside <section> tags.\n"
                    "Do not introduce any new facts, examples, products, dates, or claims.\n"
                    "If this is a module-implementation scope section, return a lead paragraph followed by bold markdown subheadings and grouped bullets."
                ),
            },
        ],
        model=req.model,
        temperature=0.05,
        max_tokens=1800,
    )


async def _expand_via_llm(
    llm,
    req: GenerateSectionRequest,
    evidence: list[EvidenceChunk],
    draft: str,
) -> str:
    return await llm.chat(
        [
            {"role": "system", "content": _REPAIR_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Expand the following draft for the section '{req.section_title}' into a fuller, "
                    "submission-ready proposal section. Keep the same factual grounding, but add more "
                    "implementation depth, phase logic, governance detail, validation approach, risk "
                    "controls, deliverables, and acceptance framing only where the evidence facts support them.\n\n"
                    "Do not add commentary, source references, or reasoning. Return only the final "
                    "section body inside <section> tags.\n\n"
                    "SECTION STYLE REQUIREMENTS\n"
                    f"{_section_style_guide(req)}\n\n"
                    "REFERENCE SECTION SCHEMA\n"
                    f"{_reference_section_schema(req)}\n\n"
                    "EVIDENCE FACTS (the only facts you may use)\n"
                    f"{_format_evidence_facts(evidence, req)}\n\n"
                    f"DRAFT\n{draft}"
                ),
            },
        ],
        model=req.model,
        temperature=0.05,
        max_tokens=1800,
    )


async def run_section_writer(req: GenerateSectionRequest) -> SectionResult:
    title = req.section_title.lower()
    if any(term in title for term in ("company profile", "client profile", "about systems limited")):
        return SectionResult(
            title=req.section_title,
            content=_static_company_profile(req),
            evidence=[],
            model=get_llm().resolve_model(req.model),
        )

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

    if _reference_compiler_available(req):
        compiled = _compile_reference_layout(req, evidence)
        if compiled:
            compiled = _remove_meta_language(compiled)
            compiled = _apply_context_guardrails(compiled, req)
            return SectionResult(
                title=req.section_title,
                content=_strip_leading_heading(compiled, req.section_title),
                evidence=evidence,
                model=get_llm().resolve_model(req.model),
            )

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
    if not llm.available:
        raise LLMError("OpenRouter is not configured. Section generation requires a working API key.")

    raw_content = await _generate_via_llm(
        llm=llm,
        req=req,
        evidence=evidence,
        length=length,
        instruction_block=instruction_block,
    )
    content = _clean_model_output(raw_content, req.section_title)
    content = _apply_context_guardrails(content, req)
    issues = _validation_issues(content, req, evidence)

    if not issues and _should_expand(content, req):
        raw_content = await _expand_via_llm(
            llm=llm,
            req=req,
            evidence=evidence,
            draft=content or raw_content,
        )
        content = _clean_model_output(raw_content, req.section_title)
        content = _apply_context_guardrails(content, req)
        issues = _validation_issues(content, req, evidence)

    attempts = 0
    while issues and attempts < 2:
        raw_content = await _repair_via_llm(
            llm=llm,
            req=req,
            evidence=evidence,
            draft=content or raw_content,
            issues=issues,
        )
        content = _clean_model_output(raw_content, req.section_title)
        content = _apply_context_guardrails(content, req)
        issues = _validation_issues(content, req, evidence)
        attempts += 1

    grounding_only = issues and all(
        "weak evidence grounding" in issue or "weak lexical grounding" in issue
        for issue in issues
    )
    if grounding_only:
        content = _prune_unsupported_sentences(content, req, evidence)
        content = _apply_context_guardrails(content, req)
        issues = _validation_issues(content, req, evidence)

    if issues:
        raise LLMError(
            "Section generation returned non-proposal output after validation: "
            + "; ".join(issues)
        )

    final_content = _strip_leading_heading(content, req.section_title)
    return SectionResult(
        title=req.section_title,
        content=final_content,
        evidence=evidence,
        model=get_llm().resolve_model(req.model),
    )

