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
