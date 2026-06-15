"""Agent 2 — Proposal Classifier.

Determines the proposal *family* using two signals:
  1. The natural-language request + extracted context (LLM reasoning).
  2. Knowledge-base signals — which families actually exist in the corpus,
     surfaced from the discovered pattern registry. We bias the model toward
     known families so generation can later reuse learned patterns.
"""

from __future__ import annotations

from app.models.schemas import ClientContext
from app.services.llm_service import LLMError, get_llm
from app.agents.pattern_discovery import known_families

_SYSTEM = (
    "You classify business proposals into a single high-level family/category. "
    "Respond with STRICT JSON only."
)

_TEMPLATE = """Classify the proposal request into ONE family.

Known families discovered in the proposal knowledge base (prefer these when a
reasonable match exists, otherwise propose a concise new family name):
{families}

Return JSON:
{{
  "proposal_family": "",
  "confidence": 0.0,
  "rationale": ""
}}

Examples of families: Temenos, Core Banking, ERP, Managed Services,
Digital Transformation, Cybersecurity, Cloud Migration.

REQUEST:
\"\"\"{prompt}\"\"\"

CONTEXT:
client_name: {client}
industry: {industry}
project_type: {project}
"""


async def run_classifier_agent(
    prompt: str, context: ClientContext, model: str | None = None
) -> tuple[str, float, str]:
    families = known_families()
    families_str = ", ".join(families) if families else "(none discovered yet)"
    llm = get_llm()
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": _TEMPLATE.format(
                        families=families_str,
                        prompt=prompt,
                        client=context.client_name or "?",
                        industry=context.industry or "?",
                        project=context.project_type or "?",
                    ),
                },
            ],
            model=model,
        )
        family = str(data.get("proposal_family", "")).strip() or _fallback(
            context
        )
        confidence = float(data.get("confidence", 0.0) or 0.0)
        rationale = str(data.get("rationale", "")).strip()
        return family, confidence, rationale
    except (LLMError, ValueError):
        return _fallback(context), 0.3, "Heuristic fallback (LLM unavailable)."


def _fallback(context: ClientContext) -> str:
    text = f"{context.project_type} {context.industry}".lower()
    rules = {
        "Temenos": ["temenos", "transact", "t24"],
        "Core Banking": ["core banking", "finacle", "flexcube"],
        "Cloud Migration": ["cloud", "migration", "aws", "azure", "gcp"],
        "Cybersecurity": ["security", "cyber", "soc", "siem"],
        "ERP": ["erp", "sap", "oracle ebs", "dynamics"],
        "Managed Services": ["managed service", "support", "maintenance"],
        "Digital Transformation": ["digital", "transformation", "modernis"],
    }
    for family, needles in rules.items():
        if any(n in text for n in needles):
            return family
    return context.project_type or "General"
