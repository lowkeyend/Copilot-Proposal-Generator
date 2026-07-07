"""Agent 4 — Template Suggestion Agent.

Given the prompt, client context and detected family, suggest the best-fit
discovered pattern as the starting template, plus a few alternatives. The
user can accept or modify it in the UI. This agent does not call the LLM —
it reasons over the learned registry so suggestions stay grounded in the
actual corpus. (User-created templates are merged in from storage.)
"""

from __future__ import annotations

from app.models.schemas import (
    ClientContext,
    ProposalTemplate,
    SuggestTemplateRequest,
    SuggestTemplateResponse,
)
from app.agents.pattern_discovery import (
    load_registry,
    pattern_for_family,
    technical_upgrade_template,
)
from app.services.storage_service import get_storage


def run_template_agent(req: SuggestTemplateRequest) -> SuggestTemplateResponse:
    discovered = load_registry()
    user_templates = get_storage().load_templates()
    catalogue = user_templates + discovered

    primary = pattern_for_family(req.proposal_family)
    contextual = _contextual_match(req.context, catalogue)
    canonical_upgrade = _canonical_upgrade(req.context)

    # Prefer a user template for the family if one exists, then a contextual
    # match that mirrors the intake, then the learned family pattern.
    user_match = next(
        (t for t in user_templates if t.proposal_family.lower() == req.proposal_family.lower()),
        None,
    )
    suggested = (
        user_match
        or canonical_upgrade
        or contextual
        or primary
        or (catalogue[0] if catalogue else _empty(req.proposal_family))
    )

    alternatives = [
        t for t in catalogue if t.id != suggested.id
    ][:4]

    return SuggestTemplateResponse(suggested=suggested, alternatives=alternatives)


def _empty(family: str) -> ProposalTemplate:
    return ProposalTemplate(
        name=f"{family or 'General'} — blank",
        proposal_family=family or "General",
        origin="user",
        sections=[],
    )


def _contextual_match(context: ClientContext, catalogue: list[ProposalTemplate]) -> ProposalTemplate | None:
    project_mode = (context.intake.project_mode or "implementation").lower()
    upgrade_type = (context.intake.upgrade_type or "unknown").lower()
    profile = (context.client_profile or "established").lower()
    tokens = " ".join(
        [
            context.client_name or "",
            context.industry or "",
            context.project_type or "",
            context.implementation_context or "",
            context.special_instructions or "",
        ]
    ).lower()

    scored: list[tuple[int, ProposalTemplate]] = []
    for template in catalogue:
        haystack = " ".join(
            [template.name, template.proposal_family, " ".join(section.title for section in template.sections)]
        ).lower()
        score = 0
        if "upgrade" in haystack and project_mode == "upgrade":
            score += 4
        if any(term in haystack for term in ("modernization", "migration", "technical")) and project_mode == "upgrade":
            score += 2
        if "greenfield" in haystack and profile == "greenfield":
            score += 4
        if any(term in haystack for term in ("implementation", "launch", "mvp")) and project_mode == "implementation":
            score += 2
        if "technical" in haystack and upgrade_type == "technical":
            score += 3
        if "functional" in haystack and upgrade_type == "functional":
            score += 3
        if "non-functional" in haystack and upgrade_type == "non-functional":
            score += 3
        if "tim" in tokens and "tim" in haystack:
            score += 2
        scored.append((score, template))

    scored.sort(key=lambda item: item[0], reverse=True)
    best = scored[0][1] if scored and scored[0][0] > 0 else None
    if best is None:
        return None
    return best


def _canonical_upgrade(context: ClientContext) -> ProposalTemplate | None:
    project_mode = (context.intake.project_mode or "implementation").lower()
    upgrade_type = (context.intake.upgrade_type or "unknown").lower()
    if project_mode == "upgrade" and upgrade_type == "technical":
        return technical_upgrade_template()
    return None
