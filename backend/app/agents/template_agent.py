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
from app.agents.pattern_discovery import load_registry, pattern_for_family
from app.services.storage_service import get_storage


def run_template_agent(req: SuggestTemplateRequest) -> SuggestTemplateResponse:
    discovered = load_registry()
    user_templates = get_storage().load_templates()
    catalogue = user_templates + discovered

    primary = pattern_for_family(req.proposal_family)

    # Prefer a user template for the family if one exists.
    user_match = next(
        (t for t in user_templates if t.proposal_family.lower() == req.proposal_family.lower()),
        None,
    )
    suggested = user_match or primary or (catalogue[0] if catalogue else _empty(req.proposal_family))

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
