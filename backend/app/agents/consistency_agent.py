"""Agent 8 — Consistency Reviewer Agent.

Runs after generation across the full set of sections and reports issues:
client-name consistency, project-name consistency, terminology drift, tone
consistency, and cross-section coherence. Combines cheap deterministic checks
(fast, always available) with an optional LLM pass for nuanced issues.
"""

from __future__ import annotations

import re
from collections import Counter

from app.models.schemas import (
    ReviewIssue,
    ReviewProposalRequest,
    ReviewProposalResponse,
)
from app.services.llm_service import LLMError, get_llm

_SYSTEM = (
    "You are a proposal quality reviewer. Identify concrete consistency and "
    "coherence problems across proposal sections. Respond with STRICT JSON only."
)

_TEMPLATE = """Review these proposal sections for the client "{client}" (project: {project}).

Check for: client-name consistency, project/product naming consistency,
terminology drift, tone consistency ({tone}), and cross-section coherence
(contradictions, repetition, gaps).

Current client profile: {client_profile}
Implementation context: {implementation_context}
Canonical product name: {canonical_product}

Return JSON:
{{
  "issues": [
    {{ "severity": "info|warning|error", "category": "", "message": "", "section_title": "" }}
  ],
  "summary": ""
}}

SECTIONS:
{sections}
"""


def _deterministic_checks(req: ReviewProposalRequest) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    client = req.context.client_name.strip()
    full_text = "\n".join(s.content for s in req.sections)
    full_lower = full_text.lower()

    if client:
        # Detect alternate capitalisations / near-variants of the client name.
        variants = Counter(
            re.findall(re.escape(client), full_text, flags=re.IGNORECASE)
        )
        exact = full_text.count(client)
        total = sum(variants.values())
        if total and exact < total:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="Client name",
                    message=f"'{client}' appears with inconsistent capitalisation across sections.",
                )
            )
        missing = [s.title for s in req.sections if client.lower() not in s.content.lower()]
        if missing and len(missing) < len(req.sections):
            issues.append(
                ReviewIssue(
                    severity="info",
                    category="Client name",
                    message=f"Client not referenced in: {', '.join(missing[:5])}.",
                )
            )

    if req.context.client_profile != "greenfield":
        greenfield_terms = [
            "greenfield bank",
            "greenfield environment",
            "greenfield implementation",
            "brand-new bank",
            "brand new bank",
            "new market entrant",
            "rapid market entry",
            "mvp launch",
        ]
        for term in greenfield_terms:
            if term in full_lower:
                issues.append(
                    ReviewIssue(
                        severity="error",
                        category="Context mismatch",
                        message=(
                            f"Found '{term}' even though the current client profile is "
                            f"'{req.context.client_profile}'. Do not transfer greenfield facts from corpus chunks."
                        ),
                    )
                )
                break

    canonical_product = (req.context.canonical_product or "").strip()
    if canonical_product:
        product_aliases = [
            "Temenos Banking Platform",
            "Temenos Core Banking",
            "Temenos core banking platform",
        ]
        used_aliases = [
            alias for alias in product_aliases if alias.lower() in full_lower and alias != canonical_product
        ]
        if used_aliases:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="Product naming",
                    message=(
                        f"Use canonical product name '{canonical_product}' consistently; "
                        f"found alternate naming: {', '.join(used_aliases)}."
                    ),
                )
            )

    if "cloud-native" in full_lower and "cloud-agnostic" in full_lower:
        issues.append(
            ReviewIssue(
                severity="info",
                category="Terminology drift",
                message=(
                    "Both 'cloud-native' and 'cloud-agnostic' appear. Prefer "
                    "'cloud-native architecture with deployment flexibility' unless the distinction is intentional."
                ),
            )
        )

    if "prince2" in full_lower and "scrum" in full_lower:
        delivery_mentions = [
            s.title
            for s in req.sections
            if re.search(r"implementation|delivery", s.title, flags=re.IGNORECASE)
            and re.search(r"prince2|scrum", s.content, flags=re.IGNORECASE)
        ]
        governance_mentions = [
            s.title
            for s in req.sections
            if re.search(r"governance|project management", s.title, flags=re.IGNORECASE)
            and re.search(r"prince2|scrum", s.content, flags=re.IGNORECASE)
        ]
        if delivery_mentions and not governance_mentions:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="Cross-section coherence",
                    message="Delivery references PRINCE2/Scrum but governance sections do not explicitly align to those frameworks.",
                    section_title=", ".join(delivery_mentions[:3]),
                )
            )

    if "migration" in full_lower and re.search(r"security|compliance|data protection", full_lower):
        migration_sections = [
            s for s in req.sections if re.search(r"migration", s.title, flags=re.IGNORECASE)
        ]
        for section in migration_sections:
            if not re.search(r"security|compliance|data protection|encryption|access control", section.content, flags=re.IGNORECASE):
                issues.append(
                    ReviewIssue(
                        severity="warning",
                        category="Cross-section coherence",
                        message=(
                            "Migration section should explicitly link data migration with security, "
                            "data protection, validation, and cutover controls."
                        ),
                        section_title=section.title,
                    )
                )

    # Empty / stub sections.
    for s in req.sections:
        if len(s.content.strip()) < 120:
            issues.append(
                ReviewIssue(
                    severity="warning",
                    category="Coverage",
                    message="Section content looks too short / possibly a stub.",
                    section_title=s.title,
                )
            )
    return issues


async def run_consistency_agent(
    req: ReviewProposalRequest,
) -> ReviewProposalResponse:
    issues = _deterministic_checks(req)
    summary = ""

    sections_blob = "\n\n".join(
        f"### {s.title}\n{s.content[:1500]}" for s in req.sections
    )
    llm = get_llm()
    if llm.available and req.sections:
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": _SYSTEM},
                    {
                        "role": "user",
                        "content": _TEMPLATE.format(
                            client=req.context.client_name or "?",
                            project=req.context.project_type or "?",
                            client_profile=req.context.client_profile or "established",
                            implementation_context=req.context.implementation_context
                            or "Modernization / migration for an existing institution",
                            canonical_product=req.context.canonical_product
                            or "Temenos Transact",
                            tone=req.context.tone or "Formal",
                            sections=sections_blob,
                        ),
                    },
                ],
                model=req.model,
            )
            for it in data.get("issues", []):
                issues.append(
                    ReviewIssue(
                        severity=str(it.get("severity", "warning")),
                        category=str(it.get("category", "General")),
                        message=str(it.get("message", "")).strip(),
                        section_title=str(it.get("section_title", "")).strip(),
                    )
                )
            summary = str(data.get("summary", "")).strip()
        except (LLMError, ValueError):
            pass

    if not summary:
        summary = (
            f"{len(issues)} issue(s) found."
            if issues
            else "No consistency issues detected."
        )
    return ReviewProposalResponse(issues=issues, summary=summary)
