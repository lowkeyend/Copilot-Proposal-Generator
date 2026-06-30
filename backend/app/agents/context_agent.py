"""Agent 1 — Client Context Agent.

Turns a free-text request into structured client context. Form-field hints
from Page 1 (client name / industry / project type) take priority over the
model's inference so the user's explicit input is never overridden.
"""

from __future__ import annotations

from typing import Optional

from app.models.schemas import ClientContext, GenerateContextRequest, IntakeProfile
from app.services.llm_service import LLMError, get_llm

_SYSTEM = (
    "You are a proposal intake analyst. Extract structured client context "
    "from a sales/bid request. Respond with STRICT JSON only, no prose."
)

_TEMPLATE = """Extract the following fields from the request below.

Return JSON exactly in this shape:
{{
  "client_name": "",
  "industry": "",
  "project_type": "",
  "client_profile": "established|greenfield|unknown",
  "implementation_context": "",
  "canonical_product": "",
  "selected_documents": [],
  "project_mode": "implementation|upgrade|unknown",
  "tone": "",
  "special_instructions": ""
}}

Rules:
- client_name: the organisation the proposal is for.
- industry: their sector (e.g. Banking, Insurance, Government).
- project_type: the work/solution (e.g. Temenos implementation, Cloud migration).
- client_profile: use "greenfield" only if the request explicitly says a new bank,
  greenfield bank, new licence, startup bank, or market launch. Use "established"
  for an existing institution, migration, upgrade, modernization, replacement, or
  implementation for a named operating bank. Otherwise use "unknown".
- project_mode: use "upgrade" when the request is about replacing/upgrading an
  existing Temenos or banking platform. Use "implementation" when it is a new
  implementation or launch. Otherwise use "unknown".
- implementation_context: describe the current-client situation, e.g.
  "Modernization / migration for an existing institution" or "Greenfield launch".
- canonical_product: the exact product/platform name to use consistently. For
  Temenos core banking proposals, default to "Temenos Transact" unless the user
  explicitly names a different Temenos product.
- tone: writing tone requested (default "Formal" if unspecified).
- special_instructions: any emphasis, constraints, or must-haves mentioned.
- Use empty string if genuinely unknown. Do not invent a client name.

REQUEST:
\"\"\"{prompt}\"\"\"
"""


async def run_context_agent(req: GenerateContextRequest) -> ClientContext:
    llm = get_llm()
    try:
        data = await llm.chat_json(
            [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": _TEMPLATE.format(prompt=req.prompt)},
            ],
            model=req.model,
        )
    except LLMError:
        data = {}

    ctx = ClientContext(
        client_name=_normalise_client_name(_clean(data.get("client_name"))),
        industry=_clean(data.get("industry")),
        project_type=_clean(data.get("project_type")),
        client_profile=_clean_profile(data.get("client_profile")),
        implementation_context=_clean(data.get("implementation_context"))
        or "Modernization / migration for an existing institution",
        canonical_product=_clean(data.get("canonical_product")) or "Temenos Transact",
        selected_documents=_clean_list(req.selected_documents),
        intake=_intake_from_req(req, data),
        tone=_clean(data.get("tone")) or "Formal",
        special_instructions=_clean(data.get("special_instructions")),
    )

    # Explicit form hints win.
    if req.client_name:
        ctx.client_name = _normalise_client_name(req.client_name)
    if req.industry:
        ctx.industry = req.industry
    if req.project_type:
        ctx.project_type = req.project_type
    if req.client_profile:
        ctx.client_profile = req.client_profile
    if req.implementation_context:
        ctx.implementation_context = req.implementation_context
    if req.canonical_product:
        ctx.canonical_product = req.canonical_product
    if req.selected_documents:
        ctx.selected_documents = _clean_list(req.selected_documents)
    if req.project_mode:
        ctx.intake.project_mode = req.project_mode
    if req.intake:
        ctx.intake = req.intake
    if not ctx.canonical_product and "temenos" in (ctx.project_type or "").lower():
        ctx.canonical_product = "Temenos Transact"
    return ctx


def _clean(value: Optional[str]) -> str:
    if not value:
        return ""
    return str(value).strip()


def _clean_profile(value: Optional[str]) -> str:
    lowered = _clean(value).lower()
    if lowered in {"established", "greenfield", "unknown"}:
        return lowered
    return "established"


def _normalise_client_name(value: str) -> str:
    cleaned = " ".join((value or "").split())
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if lowered.startswith("bank ") and lowered.endswith(" bank"):
        middle = cleaned[5:-5].strip()
        if middle:
            return f"Bank {middle}"
    if lowered in {"alfalah", "alfalah bank", "alfalahbank", "bank alfalah bank"}:
        return "Bank Alfalah"
    if lowered == "alfalah bank limited":
        return "Bank Alfalah"
    return cleaned


def _clean_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = " ".join(str(value).split()).strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(item)
    return cleaned


def _intake_from_req(req: GenerateContextRequest, data: dict) -> IntakeProfile:
    intake = req.intake or IntakeProfile()
    project_mode = _clean(data.get("project_mode"))
    if project_mode in {"implementation", "upgrade", "unknown"}:
        intake.project_mode = project_mode
    elif req.project_mode:
        intake.project_mode = req.project_mode
    return intake
