from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.agents.retrieval_agent import retrieve_for_section
from app.models.schemas import (
    AdaptSectionRequest,
    AdaptSectionResponse,
    AdaptationChange,
    ProposalBrief,
    SectionResult,
    TemplateBlock,
)
from app.services.llm_service import LLMError, get_llm

_COMMENTARY_MARKERS = (
    "user safety:",
    "the section should",
    "the final wording should",
    "questionnaire context",
    "this section",
    "the proposal should",
    "we need to write",
    "must not mention",
    "evidence includes",
    "we can derive",
    "let's craft",
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

_PATCH_TRIGGER_WORDS = (
    "rewrite",
    "rephrase",
    "expand",
    "shorter",
    "longer",
    "write a new",
    "draft a new",
    "completely rewrite",
)

_SCOPE_SHIFT_PHRASES = (
    "add ",
    "include ",
    "introduce ",
    "implement ",
    "implementation of",
    "module",
    "treasury",
    "forex",
    "fx",
)

_SECTION_FORBIDDEN_PHRASES = {
    "scope": (
        "stakeholder alignment",
        "project governance",
        "governance",
        "project plan",
        "communication protocols",
        "data migration",
        "post-deployment stabilization",
        "post-deployment support",
        "post go-live",
        "go-live preparation",
        "user training",
        "user enablement",
        "regulatory compliance",
        "streamlined",
    ),
    "solution": (
        "stakeholder alignment",
        "project governance",
        "governance",
        "project plan",
        "data migration",
        "fully automated",
        "streamlined",
        "regulatory compliance",
    ),
    "executive_summary": (
        "stakeholder alignment",
        "project governance",
        "governance",
        "project plan",
        "data migration",
        "fully automated",
        "streamlined",
        "transformation",
        "optimization",
    ),
}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _effective_versions(req: AdaptSectionRequest) -> tuple[str, str]:
    combined = f"{req.prompt or ''}\n{req.instruction or ''}"
    match = re.search(
        r"\b(?:change|upgrade|update|move)\s+(?:the\s+upgrade\s+)?from\s+(R\d+[A-Za-z0-9._-]*)\s+to\s+(R\d+[A-Za-z0-9._-]*)\b",
        combined,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean(match.group(1)), _clean(match.group(2))
    return _clean(req.context.intake.current_version), _clean(req.context.intake.target_version)


def _prompt_requests_upgrade_wording(req: AdaptSectionRequest) -> bool:
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}").lower()
    if not combined:
        return bool(_clean(req.context.intake.current_version) and _clean(req.context.intake.target_version))
    negative_upgrade_patterns = (
        r"\bdo not frame (?:this|it) as (?:a |an )?technical upgrade\b",
        r"\bnot (?:a |an )?technical upgrade\b",
        r"\bwithout upgrade wording\b",
        r"\bdo not use upgrade wording\b",
        r"\bnot an upgrade\b",
        r"\bno upgrade\b",
    )
    if any(re.search(pattern, combined, flags=re.IGNORECASE) for pattern in negative_upgrade_patterns):
        return False
    explicit_upgrade = any(
        phrase in combined
        for phrase in (
            "technical upgrade",
            "upgrade from",
            "upgrade path",
            "r20 to",
            "r21 to",
            "r22 to",
            "r23 to",
            "r24 to",
            "r25 to",
            "r26 to",
            "current version",
            "target version",
            "like-for-like upgrade",
        )
    )
    requested_modules = _extract_requested_modules(req)
    module_only = bool(requested_modules) and not explicit_upgrade
    return not module_only


def _apply_version_guardrail(text: str, req: AdaptSectionRequest) -> str:
    if not _prompt_requests_upgrade_wording(req):
        return text
    current_version, target_version = _effective_versions(req)
    if not current_version or not target_version or current_version == target_version:
        return text
    updated = text
    updated = re.sub(
        r"\bfrom\s+release\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b",
        f"from release {current_version} to {target_version}",
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        r"\bfrom\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b",
        f"from {current_version} to {target_version}",
        updated,
        flags=re.IGNORECASE,
    )
    updated = re.sub(
        r"\bTemenos\s+Transact\s+R\d+[A-Za-z0-9._-]*(?:\s+TAFJ)?\s+to\s+R\d+[A-Za-z0-9._-]*(?:\s+TAFJ)?\b",
        lambda m: re.sub(
            r"R\d+[A-Za-z0-9._-]*",
            current_version,
            re.sub(r"to\s+R\d+[A-Za-z0-9._-]*", f"to {target_version}", m.group(0), count=1, flags=re.IGNORECASE),
            count=1,
            flags=re.IGNORECASE,
        ),
        updated,
        flags=re.IGNORECASE,
    )
    return updated


def _normalized_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _support_terms(text: str) -> set[str]:
    tokens = set(_normalized_words(text))
    return {token for token in tokens if len(token) >= 4}


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


def _all_disallowed_client_names(req: AdaptSectionRequest, evidence_lines: list[str] | None = None) -> list[str]:
    client_name = _clean(req.context.client_name)
    sources = [req.reference_content]
    sources.extend(block.text for block in (getattr(req, "reference_blocks", None) or []) if block.text)
    if evidence_lines:
        sources.extend(evidence_lines)
    names: list[str] = []
    for source in sources:
        for candidate in _reference_client_candidates(source):
            if candidate not in names:
                names.append(candidate)
    return [name for name in names if client_name and name.lower() != client_name.lower()]


def _apply_client_name_guardrail(
    text: str,
    req: AdaptSectionRequest,
    evidence_lines: list[str] | None = None,
) -> str:
    client_name = _clean(req.context.client_name)
    if not client_name:
        return text.strip()
    guarded = text
    for candidate in _all_disallowed_client_names(req, evidence_lines):
        if candidate.lower() == client_name.lower():
            continue
        guarded = re.sub(re.escape(candidate), client_name, guarded, flags=re.IGNORECASE)
    guarded = re.sub(r"\bthe bank\b", client_name, guarded, flags=re.IGNORECASE) if client_name.lower().startswith("bank ") else guarded
    return guarded.strip()


def _prepare_reference_content(req: AdaptSectionRequest) -> str:
    base = _apply_client_name_guardrail(req.reference_content, req)
    return _apply_version_guardrail(base, req)


def _line_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _patch_heading_versions(line: str, req: AdaptSectionRequest) -> str:
    return _apply_version_guardrail(line, req)


def _apply_evidence_line_overrides(content: str, req: AdaptSectionRequest, evidence_lines: list[str]) -> str:
    if not evidence_lines:
        return content
    lines = content.splitlines()
    heading_index = { _clean(line).lstrip("# ").strip().lower(): idx for idx, line in enumerate(lines) if line.strip().startswith("#") }
    grouped: dict[str, list[str]] = {}
    for item in evidence_lines:
        match = re.match(r"\[(.*?)\]\s+(.*)$", item)
        if not match:
            continue
        heading = _clean(match.group(1)).lower()
        fact = _clean(match.group(2))
        if not heading or not fact:
            continue
        grouped.setdefault(heading, []).append(fact)

    for heading, idx in heading_index.items():
        candidates = grouped.get(heading, [])
        if not candidates:
            continue
        insert_at = idx + 1
        while insert_at < len(lines) and lines[insert_at].strip().startswith("#"):
            insert_at += 1
        existing_block: list[str] = []
        cursor = idx + 1
        while cursor < len(lines) and not lines[cursor].strip().startswith("#"):
            if lines[cursor].strip():
                existing_block.append(_clean(lines[cursor]).lstrip("- ").strip())
            cursor += 1
        if not existing_block:
            continue
        replacement_block: list[str] = []
        for original in existing_block:
            best = max(candidates, key=lambda fact: _line_similarity(original, fact))
            replacement_block.append(best if _line_similarity(original, best) >= 0.45 else original)
        block_start = idx + 1
        block_end = block_start
        while block_end < len(lines) and not lines[block_end].strip().startswith("#"):
            block_end += 1
        lines[block_start:block_end] = replacement_block + [""]
    return "\n".join(lines).strip()


def _should_use_patch_only(req: AdaptSectionRequest) -> bool:
    combined = f"{req.prompt or ''} {req.instruction or ''}".lower()
    if not combined.strip():
        return True
    if "preserve the reference structure" in combined or "preserve the reference structure and wording style" in combined:
        return True
    return not any(word in combined for word in _PATCH_TRIGGER_WORDS)


def _needs_semantic_block_patch(req: AdaptSectionRequest) -> bool:
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}")
    if not combined:
        return False
    generic_markers = (
        "preserve the reference structure",
        "preserve the reference structure and wording style",
        "keep company profile unchanged",
        "replace all reference client names",
    )
    stripped = combined.lower()
    return any(marker in stripped for marker in generic_markers) or len(stripped.split()) >= 12


def _is_major_scope_shift(req: AdaptSectionRequest) -> bool:
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}").lower()
    if not combined:
        return False
    if any(
        re.search(pattern, combined, flags=re.IGNORECASE)
        for pattern in (
            r"\bdo not frame (?:this|it) as (?:a |an )?technical upgrade\b",
            r"\bnot (?:a |an )?technical upgrade\b",
            r"\bdo not use upgrade wording\b",
            r"\bwithout upgrade wording\b",
        )
    ):
        return True
    if _extract_requested_modules(req) and not _prompt_requests_upgrade_wording(req):
        return True
    reference = _clean(req.reference_content).lower()
    if "upgrade" in reference and any(phrase in combined for phrase in _SCOPE_SHIFT_PHRASES):
        if "upgrade" not in combined and "like-for-like" not in combined:
            return True
    return False


def _reference_is_placeholder(req: AdaptSectionRequest) -> bool:
    text = _clean(req.reference_content).lower()
    if not text:
        return True
    placeholder_markers = (
        "legacy summary text",
        "legacy scope text",
        "legacy solution text",
        "legacy text",
    )
    if any(marker in text for marker in placeholder_markers):
        return True
    return len(text.split()) < 20


def _allow_heading_edit(req: AdaptSectionRequest, heading_text: str) -> bool:
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}").lower()
    target = _clean(heading_text).lower()
    if not combined or not target:
        return False
    if target in combined and any(
        phrase in combined
        for phrase in ("rename heading", "change heading", "rename section", "change section title", "rename subheading", "change subheading")
    ):
        return True
    if any(phrase in combined for phrase in ("rename one heading", "change one heading only", "rename only this heading")):
        return target in combined
    return False


def _extract_heading_renames(req: AdaptSectionRequest) -> dict[str, str]:
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}")
    renames: dict[str, str] = {}
    patterns = [
        r'rename\s+heading\s+"([^"]+)"\s+to\s+"([^"]+)"',
        r"rename\s+heading\s+'([^']+)'\s+to\s+'([^']+)'",
        r'rename\s+subheading\s+"([^"]+)"\s+to\s+"([^"]+)"',
        r"rename\s+subheading\s+'([^']+)'\s+to\s+'([^']+)'",
        r'change\s+heading\s+"([^"]+)"\s+to\s+"([^"]+)"',
        r"change\s+heading\s+'([^']+)'\s+to\s+'([^']+)'",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, combined, flags=re.IGNORECASE):
            renames[_clean(match.group(1)).lower()] = _clean(match.group(2))
    return renames


def _extract_requested_modules(req: AdaptSectionRequest) -> list[str]:
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}")
    modules: list[str] = []
    patterns = [
        r"\badd\s+(?:new\s+)?([A-Za-z][A-Za-z0-9&/ +_-]{1,40}?)\s+module\b",
        r"\binclude\s+(?:new\s+)?([A-Za-z][A-Za-z0-9&/ +_-]{1,40}?)\s+module\b",
        r"\bintroduce\s+(?:new\s+)?([A-Za-z][A-Za-z0-9&/ +_-]{1,40}?)\s+module\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, combined, flags=re.IGNORECASE):
            label = _clean(re.sub(r"^(the|a|an)\s+", "", match.group(1), flags=re.IGNORECASE))
            if label:
                modules.append(f"{label} module")
    return list(dict.fromkeys(modules))


def _evidence_supports_phrase(phrase: str, evidence_lines: list[str]) -> bool:
    target = _clean(phrase).lower()
    if not target:
        return False
    return any(target in _clean(line).lower() for line in evidence_lines)


def _apply_prompt_directives_to_block(
    req: AdaptSectionRequest,
    block: TemplateBlock,
    evidence_lines: list[str],
) -> TemplateBlock:
    next_block = block.model_copy(deep=True)
    renames = _extract_heading_renames(req)
    requested_modules = [
        module for module in _extract_requested_modules(req)
        if _evidence_supports_phrase(module, evidence_lines) or _evidence_supports_phrase(module.replace(" module", ""), evidence_lines)
    ]
    if next_block.kind == "heading":
        renamed = renames.get(_clean(next_block.text).lower())
        if renamed:
            next_block.text = renamed
            if next_block.heading_level <= 1:
                next_block.section_title = renamed
        if requested_modules and not _prompt_requests_upgrade_wording(req):
            if re.search(r"\bcore upgrade\b", next_block.text, flags=re.IGNORECASE):
                next_block.text = re.sub(
                    r"\bCore Upgrade\b.*$",
                    f"{requested_modules[0].replace(' module', '').title()} Module Scope",
                    next_block.text,
                    flags=re.IGNORECASE,
                )
        return next_block

    if not requested_modules:
        return next_block

    module_phrase = requested_modules[0]
    lower_title = _clean(req.section_title).lower()
    if next_block.kind == "paragraph":
        text = next_block.text or ""
        if _clean(text).lower() == "the scope includes:":
            return next_block
        if module_phrase.lower() not in text.lower():
            if "executive summary" in lower_title:
                text = re.sub(r"\bfrom\s+release\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\bfrom\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\bfrom the current release to the latest agreed Temenos release\b", "", text, flags=re.IGNORECASE)
                text = re.sub(
                    r"\blike-for-like technical upgrade\b",
                    f"delivery of the {module_phrase}",
                    text,
                    count=1,
                    flags=re.IGNORECASE,
                )
                if module_phrase.lower() not in text.lower():
                    text = f"{text.rstrip('.')} with the addition of the {module_phrase}."
            elif "scope of work" in lower_title:
                text = re.sub(r"\bfrom\s+release\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\bfrom\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\bfrom the current release to the latest agreed Temenos release\b", "", text, flags=re.IGNORECASE)
                text = re.sub(
                    r"\blike-for-like technical upgrade\b",
                    f"implementation of the {module_phrase}",
                    text,
                    count=1,
                    flags=re.IGNORECASE,
                )
                if module_phrase.lower() not in text.lower():
                    text = f"{text.rstrip('.')} including the {module_phrase}."
            elif "solution" in lower_title:
                text = re.sub(r"\bfrom\s+release\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\bfrom\s+[A-Za-z0-9._-]+\s+to\s+[A-Za-z0-9._-]+\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\bfrom the current release to the latest agreed Temenos release\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\blike-for-like technical upgrade\b", f"solution delivery for the {module_phrase}", text, count=1, flags=re.IGNORECASE)
                text = f"{text.rstrip('.')} The proposed solution includes the {module_phrase}."
            if not _prompt_requests_upgrade_wording(req):
                text = re.sub(r"\bR\d+[A-Za-z0-9._-]*(?:\s+TAFJ)?\s+to\s+R\d+[A-Za-z0-9._-]*(?:\s+TAFJ)?\b", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\ba implementation\b", "the implementation", text, flags=re.IGNORECASE)
                text = re.sub(r"\bof QIB's\b", "for QIB's", text, flags=re.IGNORECASE)
                text = re.sub(r"\s{2,}", " ", text).strip(" .,:;")
                text = text + "." if text else text
            next_block.text = text
    elif next_block.kind == "list":
        items = next_block.items or [next_block.text] if next_block.text else []
        if items and not any(module_phrase.lower() in item.lower() for item in items):
            items = [*items, f"Include the {module_phrase} within the applicable scope and configuration."]
            next_block.items = items
            next_block.text = "\n".join(items)
    return next_block


def _blocks_equal(a: list[TemplateBlock], b: list[TemplateBlock]) -> bool:
    if len(a) != len(b):
        return False
    for left, right in zip(a, b):
        if left.kind != right.kind:
            return False
        if _clean(left.text) != _clean(right.text):
            return False
        if [_clean(item) for item in (left.items or [])] != [_clean(item) for item in (right.items or [])]:
            return False
        if [[_clean(cell) for cell in row] for row in (left.table_rows or [])] != [[_clean(cell) for cell in row] for row in (right.table_rows or [])]:
            return False
    return True


def _deterministic_patch(req: AdaptSectionRequest, evidence_lines: list[str]) -> str:
    content = _prepare_reference_content(req)
    lines = content.splitlines()
    patched: list[str] = []
    for line in lines:
        updated = _patch_heading_versions(line, req) if line.strip().startswith("#") else line
        patched.append(updated)
    return _apply_evidence_line_overrides("\n".join(patched), req, evidence_lines)


def _patch_reference_blocks(req: AdaptSectionRequest, evidence_lines: list[str]) -> list[TemplateBlock]:
    if not req.reference_blocks:
        return []
    patched_blocks: list[TemplateBlock] = []
    for block in req.reference_blocks:
        next_block = block.model_copy(deep=True)
        if next_block.kind == "heading":
            next_block.text = _apply_version_guardrail(
                _apply_client_name_guardrail(next_block.text or "", req, evidence_lines),
                req,
            )
            if block.heading_level <= 1:
                next_block.section_title = next_block.text
        elif next_block.kind == "paragraph":
            next_block.text = _apply_version_guardrail(
                _apply_client_name_guardrail(next_block.text or "", req, evidence_lines),
                req,
            )
        elif next_block.kind == "list":
            next_block.items = [
                _apply_version_guardrail(_apply_client_name_guardrail(item, req, evidence_lines), req)
                for item in (next_block.items or [next_block.text] if next_block.text else [])
            ]
            next_block.text = "\n".join(next_block.items)
        elif next_block.kind == "table" and next_block.table_rows:
            next_block.table_rows = [
                [_apply_version_guardrail(_apply_client_name_guardrail(cell, req, evidence_lines), req) for cell in row]
                for row in next_block.table_rows
            ]
        elif next_block.kind == "image" and next_block.image is not None:
            next_block.image = next_block.image.model_copy(
                update={
                    "caption": _apply_client_name_guardrail(next_block.image.caption or "", req, evidence_lines),
                    "section": _apply_client_name_guardrail(next_block.image.section or "", req, evidence_lines),
                }
            )
        next_block = _apply_prompt_directives_to_block(req, next_block, evidence_lines)
        patched_blocks.append(next_block)
    return patched_blocks


def _content_from_blocks(blocks: list[TemplateBlock]) -> str:
    lines: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            prefix = "#" * max(block.heading_level or 1, 1)
            lines.extend([f"{prefix} {block.text}".rstrip(), ""])
        elif block.kind == "paragraph":
            lines.extend([block.text.strip(), ""])
        elif block.kind == "list":
            items = block.items or [line.strip() for line in (block.text or "").splitlines() if line.strip()]
            lines.extend([f"- {item}".rstrip() for item in items])
            lines.append("")
        elif block.kind == "table":
            for row in block.table_rows or []:
                lines.append(f"| {' | '.join((cell or '').strip() for cell in row)} |")
            if block.table_rows:
                lines.append("")
    return "\n".join(lines).strip()


async def _semantic_patch_blocks(
    req: AdaptSectionRequest,
    brief: ProposalBrief,
    evidence_lines: list[str],
    blocks: list[TemplateBlock],
) -> list[TemplateBlock]:
    editable_blocks = [
        {
            "block_id": block.block_id,
            "kind": block.kind,
            "heading_level": block.heading_level,
            "text": block.text,
            "items": block.items,
            "table_rows": block.table_rows,
            "editable": block.editable,
            "adaptation_hint": block.adaptation_hint,
        }
        for block in blocks
        if (
            (block.kind in {"paragraph", "list", "table"} and block.editable)
            or (block.kind == "heading" and _allow_heading_edit(req, block.text or ""))
        )
    ]
    if not editable_blocks:
        return blocks

    prompt = f"""
Return strict JSON only with this shape:
{{
  "patches": [
    {{
      "block_id": "string",
      "text": "string",
      "items": ["string"],
      "table_rows": [["string"]]
    }}
  ]
}}

You are conservatively adapting a proposal section while preserving the original template style and structure.

SECTION TITLE
{req.section_title}

MASTER PROMPT
{req.prompt or "(none)"}

SECTION INSTRUCTION
{req.instruction or "(none)"}

CLIENT FACTS
{chr(10).join(f"- {item}" for item in _context_facts(req)) or "- none"}

CHANGE PLAN
{chr(10).join(f"- {item}" for item in brief.must_change[:12]) or "- Apply only prompt-required changes."}

RETRIEVED SUPPORTING FACTS
{chr(10).join(f"- {item}" for item in evidence_lines[:18]) or "- none"}

EDITABLE BLOCKS
{editable_blocks}

Rules:
- Preserve the same structure, order, and professional proposal style.
- Do not rewrite headings or add/remove blocks.
- Only rename a heading if the prompt explicitly asks for that exact heading to change.
- Update only the editable block contents.
- Apply the master prompt materially, not cosmetically.
- Use only supported facts from the retrieved evidence or explicit client context.
- Keep wording concise, proposal-grade, and structurally aligned to the template.
- If a block should remain unchanged, return its original content.
"""
    data = await get_llm().chat_json(
        [
            {"role": "system", "content": "You return strict JSON patches for proposal blocks only."},
            {"role": "user", "content": prompt},
        ],
        model=req.model,
        temperature=0.1,
        max_tokens=2200,
    )
    patches = data.get("patches", []) if isinstance(data, dict) else []
    by_id = {str(item.get("block_id", "")).strip(): item for item in patches if str(item.get("block_id", "")).strip()}
    patched_blocks: list[TemplateBlock] = []
    for block in blocks:
        patch = by_id.get(block.block_id)
        if not patch:
            patched_blocks.append(block)
            continue
        next_block = block.model_copy(deep=True)
        if next_block.kind == "heading":
            next_text = str(patch.get("text", next_block.text or "")).strip() or next_block.text
            next_block.text = _apply_version_guardrail(
                _apply_client_name_guardrail(next_text, req, evidence_lines),
                req,
            )
            if next_block.heading_level <= 1:
                next_block.section_title = next_block.text
        elif next_block.kind == "paragraph":
            next_block.text = _apply_version_guardrail(
                _apply_client_name_guardrail(str(patch.get("text", next_block.text or "")), req, evidence_lines),
                req,
            )
        elif next_block.kind == "list":
            raw_items = patch.get("items")
            if not isinstance(raw_items, list) or not raw_items:
                raw_items = [patch.get("text", next_block.text or "")]
            next_block.items = [
                _apply_version_guardrail(_apply_client_name_guardrail(str(item), req, evidence_lines), req)
                for item in raw_items
                if str(item).strip()
            ]
            next_block.text = "\n".join(next_block.items)
        elif next_block.kind == "table":
            rows = patch.get("table_rows")
            if isinstance(rows, list) and rows:
                next_block.table_rows = [
                    [
                        _apply_version_guardrail(_apply_client_name_guardrail(str(cell), req, evidence_lines), req)
                        for cell in row
                    ]
                    for row in rows
                    if isinstance(row, list)
                ]
        patched_blocks.append(next_block)
    return patched_blocks


def _blocks_from_content(req: AdaptSectionRequest, content: str) -> list[TemplateBlock]:
    blocks: list[TemplateBlock] = []
    lines = [line.rstrip() for line in (content or "").splitlines()]
    order = 0
    buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal order, buffer
        text = "\n".join(line.strip() for line in buffer if line.strip()).strip()
        if not text:
            buffer = []
            return
        kind = "list" if all(re.match(r"^[-*]\s+", item.strip()) for item in buffer if item.strip()) else "paragraph"
        items = [re.sub(r"^[-*]\s+", "", item.strip()) for item in buffer if item.strip()] if kind == "list" else []
        blocks.append(
            TemplateBlock(
                kind=kind,
                section_title=req.section_title,
                text=text,
                items=items,
                order=order,
            )
        )
        order += 1
        buffer = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("#"):
            flush_paragraph()
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append(
                TemplateBlock(
                    kind="heading",
                    section_title=req.section_title,
                    heading_level=max(level, 1),
                    text=stripped.lstrip("#").strip(),
                    order=order,
                    editable=False,
                )
            )
            order += 1
            continue
        buffer.append(stripped)
    flush_paragraph()
    return blocks


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


def _evidence_snapshot(evidence_lines: list[str], limit: int = 18) -> str:
    return chr(10).join(f"- {item}" for item in evidence_lines[:limit]) or "- none"


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text or "") if part.strip()]


def _section_kind(section_title: str) -> str:
    title = _clean(section_title).lower()
    if "scope" in title:
        return "scope"
    if "solution" in title:
        return "solution"
    if "executive summary" in title or "introduction" in title:
        return "executive_summary"
    return "generic"


def _section_max_tokens(section_title: str) -> int:
    kind = _section_kind(section_title)
    if kind == "executive_summary":
        return 750
    if kind == "solution":
        return 1100
    if kind == "scope":
        return 1300
    return 1000


def _filtered_context_facts(req: AdaptSectionRequest, evidence_lines: list[str]) -> list[str]:
    intake = req.context.intake
    facts = [
        f"Client name: {req.context.client_name}" if req.context.client_name else "",
        f"Client profile: {req.context.client_profile}" if req.context.client_profile else "",
        f"Project mode: {intake.project_mode}" if intake.project_mode else "",
        f"Upgrade type: {intake.upgrade_type}" if intake.upgrade_type else "",
        f"Current system: {intake.current_system}" if intake.current_system else "",
        f"Current version: {intake.current_version}" if intake.current_version and _prompt_requests_upgrade_wording(req) else "",
        f"Target version: {intake.target_version}" if intake.target_version and _prompt_requests_upgrade_wording(req) else "",
        f"Selected documents: {', '.join(req.context.selected_documents)}" if req.context.selected_documents else "",
    ]
    combined = _clean(f"{req.prompt or ''} {req.instruction or ''}").lower()
    evidence_text = " ".join(evidence_lines).lower()
    allow_delivery = any(token in combined for token in ("tim", "methodology", "mvp", "phased", "big bang", "delivery model")) or any(
        token in evidence_text for token in (" tim ", "methodology", "mvp", "phased", "big bang")
    )
    if allow_delivery:
        facts.extend(
            [
                f"Delivery model: {intake.delivery_model}" if intake.delivery_model else "",
                f"Implementation methodology: {intake.implementation_methodology}" if intake.implementation_methodology else "",
            ]
        )
    return [item for item in facts if item]


def _grounding_context_terms_for_adaptation(req: AdaptSectionRequest) -> set[str]:
    context_parts = [
        req.context.client_name or "",
        req.context.industry or "",
        req.context.canonical_product or "",
        req.context.client_profile or "",
    ]
    return _support_terms(" ".join(context_parts))


def _grounding_evidence_terms_for_adaptation(evidence_lines: list[str]) -> set[str]:
    terms: set[str] = set()
    for line in evidence_lines:
        terms.update(_support_terms(line))
    return terms


def _evidence_supports_term(term: str, evidence_lines: list[str]) -> bool:
    needle = _clean(term).lower()
    return any(needle in _clean(line).lower() for line in evidence_lines)


def _prune_unsupported_adaptation_sentences(
    content: str,
    req: AdaptSectionRequest,
    evidence_lines: list[str],
) -> str:
    evidence_terms = _grounding_evidence_terms_for_adaptation(evidence_lines)
    context_terms = _grounding_context_terms_for_adaptation(req)
    forbidden = _SECTION_FORBIDDEN_PHRASES.get(_section_kind(req.section_title), ())
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", content or "") if part.strip()]
    kept_paragraphs: list[str] = []
    for paragraph in paragraphs:
        units: list[str]
        if paragraph.lstrip().startswith(("#", "-", "*")):
            units = [line.strip() for line in paragraph.splitlines() if line.strip()]
        else:
            units = _split_sentences(paragraph)
        kept_units: list[str] = []
        for sentence in units:
            low = sentence.lower()
            if any(phrase in low and not _evidence_supports_term(phrase, evidence_lines) for phrase in forbidden):
                continue
            sentence_terms = _support_terms(sentence)
            evidence_overlap = len(sentence_terms & evidence_terms)
            context_overlap = len(sentence_terms & context_terms)
            if len(sentence_terms) < 4 or evidence_overlap + context_overlap >= 2:
                kept_units.append(sentence)
        if kept_units:
            kept_paragraphs.append("\n".join(kept_units) if paragraph.lstrip().startswith(("#", "-", "*")) else " ".join(kept_units))
    return "\n\n".join(kept_paragraphs).strip()


def _normalize_section_format(text: str) -> str:
    formatted = text.replace(" **", "\n\n**")
    formatted = re.sub(r"\s+-\s+\*\*", r"\n- **", formatted)
    formatted = re.sub(r"\.\s+(\d+\.\s+\*\*)", r".\n\n\1", formatted)
    formatted = re.sub(r"\s+([*-])\s+", r"\n\1 ", formatted)
    formatted = re.sub(r"(?<!\n)(\d+\.)\s+\*\*", r"\n\1 **", formatted)
    formatted = re.sub(r"\*\*Implementation activities\*\*\s*(\d+\.)", r"**Implementation activities**\n\n\1", formatted)
    formatted = re.sub(r"\n{3,}", "\n\n", formatted)
    return formatted.strip()


async def _extract_structured_facts(
    req: AdaptSectionRequest,
    evidence_lines: list[str],
) -> list[str]:
    if not evidence_lines:
        return []
    prompt = f"""
Return strict JSON only in this shape:
{{
  "facts": ["string"]
}}

Extract only concrete proposal facts relevant to this section.

SECTION TITLE
{req.section_title}

MASTER PROMPT
{req.prompt or "(none)"}

SECTION INSTRUCTION
{req.instruction or "(none)"}

CLIENT FACTS
{chr(10).join(f"- {item}" for item in _filtered_context_facts(req, evidence_lines)) or "- none"}

RAW EVIDENCE
{_evidence_snapshot(evidence_lines, 20)}

Rules:
- Extract only facts explicitly supported by the raw evidence.
- Prefer versions, modules, environments, interfaces, controls, activities, testing items, deliverables, reports, and counts.
- Do not include inferred benefits, generic governance, sales language, or unsupported delivery claims.
- Keep each fact short and specific.
- Return at most 16 facts.
"""
    try:
        data = await get_llm().chat_json(
            [
                {"role": "system", "content": "You extract grounded proposal facts only."},
                {"role": "user", "content": prompt},
            ],
            model=req.model,
            temperature=0.0,
            max_tokens=700,
        )
        facts = data.get("facts", []) if isinstance(data, dict) else []
        cleaned: list[str] = []
        for item in facts:
            text = _clean(str(item))
            if text and text not in cleaned:
                cleaned.append(text)
        return cleaned[:16]
    except Exception:
        return []


def _section_contract(req: AdaptSectionRequest) -> str:
    kind = _section_kind(req.section_title)
    if kind == "scope":
        return """
- Write a contractual scope section.
- Focus on implementation activities, work packages, deliverables, controls, interfaces, testing scope, and deployment support.
- Do not add business benefits, transformation claims, or sales language.
- Do not add methodology, governance, phases, or timeline wording unless the prompt explicitly asks for it or the evidence directly supports it.
- Use compact bullets where they improve clarity, but keep the language operational and submission-ready.
"""
    if kind == "solution":
        return """
- Write a proposed solution section.
- Focus on the target functional capability, module behavior, operating coverage, interfaces, controls, and relevant configuration shape.
- Explain what the solution will provide, not generic benefits.
- Do not drift into scope management, commercial language, or governance content unless the evidence directly supports it.
- Keep the tone factual, product-aware, and proposal-ready.
"""
    if kind == "executive_summary":
        return """
- Write an executive summary that is concise, client-specific, and grounded.
- Summarize the engagement objective, the proposed capability or change, and the delivery intent only if supported.
- Do not restate source commentary, chunk reasoning, or document analysis.
- Do not use marketing phrases or inflated value statements.
- Do not end with generic business-benefit claims such as efficiency improvement, transformation, optimization, or strengthened controls unless those exact outcomes are explicitly supported by the evidence and requested in the prompt.
- Prefer a factual summary of the capability being implemented, the operational coverage, and the implementation intent.
- Keep the prose polished and brief, with no unnecessary subheadings unless needed for clarity.
"""
    return """
- Write a grounded proposal section using only the supported evidence and explicit client context.
- Keep the tone factual and submission-ready.
- Do not introduce unsupported benefits or generic consulting language.
"""


def _strip_redundant_section_title(text: str, section_title: str) -> str:
    lines = [line.rstrip() for line in (text or "").splitlines()]
    while lines:
        first = _clean(re.sub(r"[*_#`]+", "", lines[0])).lower().rstrip(":")
        target = _clean(section_title).lower().rstrip(":")
        if first == target:
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines = lines[1:]
            continue
        break
    return "\n".join(lines).strip()


async def _grounded_scope_rewrite(
    req: AdaptSectionRequest,
    brief: ProposalBrief,
    evidence_lines: list[str],
) -> str:
    context_facts = _filtered_context_facts(req, evidence_lines)
    structured_facts = await _extract_structured_facts(req, evidence_lines)
    prompt = f"""
Write a submission-ready proposal section using only the retrieved evidence and explicit client context.

SECTION TITLE
{req.section_title}

CLIENT FACTS
{chr(10).join(f"- {item}" for item in context_facts) or "- none"}

MASTER PROMPT
{req.prompt or "(none)"}

SECTION INSTRUCTION
{req.instruction or "(none)"}

REFERENCE SECTION
{req.reference_content}

CHANGE PLAN
{chr(10).join(f"- {item}" for item in brief.must_change[:12]) or "- Apply only explicit prompt changes."}

STRUCTURED FACTS (the only facts you may use)
{chr(10).join(f"- {item}" for item in structured_facts) or "- none"}

SUPPORTED EVIDENCE
{_evidence_snapshot(evidence_lines, 24)}

Rules:
- This is a fresh grounded rewrite, not a patch.
- Use only facts that are explicitly supported in the STRUCTURED FACTS block or explicit client context.
- Do not repeat the section title at the start of the answer.
- If the prompt requests a module implementation or scope addition, do not preserve upgrade-only headings such as Environment Readiness Assessment, Core Technical Upgrade, or Post Go-Live Support unless the evidence explicitly supports them for this section.
- Do not mention release-to-release upgrade wording unless the prompt explicitly asks for an upgrade and the evidence supports it.
- Do not mechanically repeat phrases like "including the Forex module" on every line.
- Produce coherent proposal content that reads as an actual client submission, not commentary or notes.
- Write in operational proposal language, not marketing language.
- Prefer concrete implementation activities, module capabilities, interfaces, controls, testing scope, deployment activities, and delivery responsibilities over benefit statements.
- Prefer a clear lead paragraph followed by concise scope bullets or subsection bullets only where they improve clarity.
- Do not add an exclusions paragraph unless the prompt explicitly asks for exclusions.
- Do not state unsupported business benefits, transformation claims, or value claims.
- Do not mention source documents, evidence, chunk names, or reasoning.
- Do not output HTML or XML tags.
- Do not invent benefits, governance, timelines, testing cycles, or technical steps that are not directly supported.
- If a point is not present in STRUCTURED FACTS, omit it.
{_section_contract(req)}

Return final proposal content only.
"""
    return await get_llm().chat(
        [
            {"role": "system", "content": "You write grounded proposal sections from retrieved evidence only."},
            {"role": "user", "content": prompt},
        ],
        model=req.model,
        temperature=0.12,
        max_tokens=_section_max_tokens(req.section_title),
    )


async def _build_brief(req: AdaptSectionRequest, evidence_lines: list[str]) -> ProposalBrief:
    llm = get_llm()
    client_name = _clean(req.context.client_name)
    current_version = _clean(req.context.intake.current_version)
    target_version = _clean(req.context.intake.target_version)
    prompt_text = _clean(req.prompt)
    instruction_text = _clean(req.instruction)
    deterministic = ProposalBrief(
        summary=f"Adapt {req.section_title} for {client_name or 'the target client'} using the selected context and prompt.",
        must_change=[
            *( [f"Replace any reference client name with {client_name}."] if client_name else [] ),
            *( [f"Reflect the upgrade path from {current_version} to {target_version}."] if current_version and target_version else [] ),
            *( [f"Apply master prompt instructions: {prompt_text}"] if prompt_text else [] ),
            *( [f"Apply section instruction: {instruction_text}"] if instruction_text else [] ),
        ],
        must_preserve=[
            "Preserve the reference section structure and operational tone.",
            "Keep only evidence-supported statements.",
        ],
        forbidden_claims=list(_MARKETING_PHRASES),
        prompt_directives=[
            item for item in [prompt_text, instruction_text] if item
        ],
    )
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
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": "You produce strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            model=req.model,
            temperature=0.1,
            max_tokens=800,
        )
        parsed = ProposalBrief.model_validate(data)
        parsed.must_change = list(dict.fromkeys([*deterministic.must_change, *parsed.must_change]))
        parsed.must_preserve = list(dict.fromkeys([*deterministic.must_preserve, *parsed.must_preserve]))
        parsed.forbidden_claims = list(dict.fromkeys([*deterministic.forbidden_claims, *parsed.forbidden_claims]))
        parsed.prompt_directives = list(dict.fromkeys([*deterministic.prompt_directives, *parsed.prompt_directives]))
        if not parsed.summary:
            parsed.summary = deterministic.summary
        return parsed
    except Exception:
        return deterministic


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
    if reference_headings and not _is_major_scope_shift(req):
        present = sum(1 for heading in reference_headings if heading.lower() in lowered)
        if present < max(1, len(reference_headings) // 2):
            notes.append("output preserved fewer reference subheadings than expected")
    reference_corpus = f"{req.reference_content}\n" + "\n".join(brief.must_change) + "\n".join(brief.must_preserve)
    reference_lower = reference_corpus.lower()
    for phrase in list(_MARKETING_PHRASES) + list(brief.forbidden_claims):
        needle = (phrase or "").strip().lower()
        if needle and needle in lowered and needle not in reference_lower:
            notes.append(f"unsupported claim removed or retained risk: {phrase}")
    client_name = _clean(req.context.client_name)
    if client_name and client_name.lower() not in lowered:
        notes.append("client name not present in adapted output")
    leaked_names = _all_disallowed_client_names(req)
    if any(name.lower() in lowered for name in leaked_names):
        raise LLMError("adapted output still contains a reference client name")
    return notes


def _sanitize_output(text: str, req: AdaptSectionRequest, brief: ProposalBrief, evidence_lines: list[str]) -> str:
    cleaned = _strip_redundant_section_title(
        _apply_client_name_guardrail(text, req, evidence_lines),
        req.section_title,
    )
    reference_corpus = f"{req.reference_content}\n" + "\n".join(brief.must_change) + "\n".join(brief.must_preserve)
    reference_lower = reference_corpus.lower()
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        low = sentence.lower()
        blocked = False
        for phrase in list(_MARKETING_PHRASES) + list(brief.forbidden_claims):
            needle = (phrase or "").strip().lower()
            if needle and needle in low and needle not in reference_lower:
                blocked = True
                break
        if not blocked:
            kept.append(sentence)
    grounded = _clean(" ".join(kept) or cleaned)
    grounded = _prune_unsupported_adaptation_sentences(grounded, req, evidence_lines)
    return _normalize_section_format(grounded)


def _looks_like_meta_output(text: str) -> bool:
    lowered = _clean(text).lower()
    if not lowered:
        return True
    markers = (
        "user safety:",
        "we need to write",
        "must not mention",
        "must not repeat",
        "evidence includes",
        "we can derive",
        "let's craft",
        "so start directly",
        "thus we can",
        "the instruction",
        "we should",
    )
    return any(marker in lowered for marker in markers)


def _needs_retry(content: str, req: AdaptSectionRequest) -> bool:
    cleaned = _clean(content)
    if not cleaned:
        return True
    if _looks_like_meta_output(cleaned):
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
- do not return notes about what you are going to write;
- do not mention evidence, instructions, constraints, or writing decisions;
- return only the final client-ready section body.

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

    prepared_reference = _prepare_reference_content(req)

    evidence = retrieve_for_section(
        section_title=req.section_title,
        keywords=_markdown_headings(prepared_reference) or req.reference_headings or [],
        context=req.context,
        proposal_family=req.proposal_family,
        prompt=req.prompt,
        instruction=req.instruction,
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

    effective_req = req.model_copy(update={"reference_content": prepared_reference})
    brief = await _build_brief(effective_req, evidence_lines)
    structure = _reference_structure(prepared_reference)
    plan = [AdaptationChange(kind="preserve", detail=item) for item in brief.must_preserve[:6]]
    plan.extend(AdaptationChange(kind="replace", detail=item) for item in brief.must_change[:8])

    if _is_major_scope_shift(effective_req) or _reference_is_placeholder(effective_req):
        content = await _grounded_scope_rewrite(effective_req, brief, evidence_lines)
        if _looks_like_meta_output(content):
            content = await _retry_adaptation(effective_req, brief, evidence_lines, content)
        content = _sanitize_output(content, effective_req, brief, evidence_lines)
        notes = _validate_output(content, effective_req, brief)
        section = SectionResult(
            title=req.section_title,
            content=content.strip(),
            blocks=_blocks_from_content(effective_req, content),
            evidence=evidence,
            locked=False,
            model=f"{llm.resolve_model(req.model)}:grounded-rewrite",
        )
        return AdaptSectionResponse(
            section=section,
            brief=brief,
            change_plan=plan,
            validation_notes=notes,
        )

    if _should_use_patch_only(effective_req):
        blocks = _patch_reference_blocks(effective_req, evidence_lines)
        original_blocks = [block.model_copy(deep=True) for block in blocks]
        if _needs_semantic_block_patch(effective_req):
            try:
                semantic_blocks = await _semantic_patch_blocks(effective_req, brief, evidence_lines, blocks)
                if not _blocks_equal(semantic_blocks, blocks):
                    blocks = semantic_blocks
            except Exception:
                blocks = original_blocks
        content = _content_from_blocks(blocks) if blocks else _deterministic_patch(effective_req, evidence_lines)
        notes = _validate_output(content, effective_req, brief)
        section = SectionResult(
            title=req.section_title,
            content=content.strip(),
            blocks=blocks,
            evidence=evidence,
            locked=False,
            model=f"{llm.resolve_model(req.model)}:patch",
        )
        return AdaptSectionResponse(
            section=section,
            brief=brief,
            change_plan=plan,
            validation_notes=notes,
        )

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
{prepared_reference}

REFERENCE STRUCTURE TO PRESERVE
{structure}

CHANGE PLAN
{chr(10).join(f"- {item}" for item in brief.must_change[:10]) or "- Apply only explicit client/version/scope changes."}

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
    if _needs_retry(content, effective_req):
        content = await _retry_adaptation(effective_req, brief, evidence_lines, content)
    content = _sanitize_output(content, effective_req, brief, evidence_lines)
    notes = _validate_output(content, effective_req, brief)
    section = SectionResult(
        title=req.section_title,
        content=content.strip(),
        blocks=_blocks_from_content(effective_req, content),
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
